"""
QA Agent v2 — PRD → Test Plan → Test Cases → (scope gate) → Playwright TS suite

Usage:
    python qa_agent.py path/to/requirements.md path/to/project_dir [--config config.yaml]

    # Non-interactive scoping (great for CI):
    python qa_agent.py prd.md out/ --scope smoke
    python qa_agent.py prd.md out/ --scope regression --exclude-types accessibility
    python qa_agent.py prd.md out/ --priorities P0 P1 --targets api --grep login
    python qa_agent.py prd.md out/ --requirements REQ-2 REQ-3 --limit 10
    python qa_agent.py prd.md out/ --scope smoke --save-scope ci-gate
    python qa_agent.py prd.md out/ --list-scopes

    # Verify gate (compile generated code, one repair round, exit 1 on failure).
    # Defaults to on when $CI is set, off otherwise:
    python qa_agent.py prd.md out/ --scope smoke --check
    python qa_agent.py prd.md out/ --scope smoke --no-check

    # Regeneration mode (default 'changed' uses .specwright/manifest.json to
    # rewrite only files whose cases changed; 'all' overwrites everything):
    python qa_agent.py prd.md out/ --scope smoke --regen all

    # Push cases straight into Jira, upserting by specwright-<TC-ID> label
    # (config 'jira' block + JIRA_EMAIL/JIRA_TOKEN env vars):
    python qa_agent.py prd.md out/ --push-jira

    # Execute the generated suite and roll results up per requirement
    # (exit 1 when any test fails):
    python qa_agent.py prd.md out/ --scope smoke --run --base-url http://localhost:3000

Config chooses the LLM provider (gemini, groq, ollama, anthropic) and optional
export formats. Between stages 2 and 3, a scope gate decides which cases to
automate — interactively, via --scope <preset|saved-name>, or via filter flags.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from config import load_config
from providers import get_provider
from schema import validate_cases
from stages import stage1_plan, stage2_cases, stage3_automate
from scope import (PRESETS, prompt_scope, apply_scope, resolve_scope,
                   validate_scope, describe_scope, coverage_report,
                   load_saved_scopes, save_scope)
from exporters import run_exports
from runner import run_suite


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requirements", nargs="?", help="Path to .md/.txt requirements doc")
    ap.add_argument("project", nargs="?",
                    help="Path to project dir (new or existing Playwright)")
    ap.add_argument("--config", default="config.yaml", help="Path to config file")
    ap.add_argument("--skip-stage", action="append", choices=["1", "2", "3"], default=[])
    ap.add_argument("--non-interactive", action="store_true",
                    help="Skip scope gate (use everything automatable)")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 2 if any requirement generated zero cases or "
                         "the scope selects nothing (for CI gates)")
    ap.add_argument("--summary-json", metavar="PATH",
                    help="Write a machine-readable run summary (per-stage "
                         "counts, coverage, selection, exit status) to PATH")
    ap.add_argument("--check", action=argparse.BooleanOptionalAction,
                    default=None,
                    help="Verify generated code compiles (npm install, tsc, "
                         "playwright --list) with one LLM repair round; exit 1 "
                         "if files still fail. Default: on when $CI is set")
    ap.add_argument("--run", action="store_true",
                    help="Execute the generated suite (npx playwright test) "
                         "after Stage 3, print a per-requirement pass/fail "
                         "table and exit 1 on test failures")
    ap.add_argument("--base-url", metavar="URL",
                    help="BASE_URL env var for --run (UI tests)")
    ap.add_argument("--api-url", metavar="URL",
                    help="API_URL env var for --run (API tests)")
    ap.add_argument("--push-jira", action="store_true",
                    help="After exports, upsert every case into Jira as one "
                         "issue each (config 'jira' block for base_url/"
                         "project_key, credentials via JIRA_EMAIL/JIRA_TOKEN)")
    ap.add_argument("--regen", choices=["all", "changed"], default="changed",
                    help="How Stage 3 treats existing generated files: "
                         "'changed' (default) regenerates only files whose "
                         "producing cases changed since the manifest was "
                         "written (hand-edited files get a .new sibling); "
                         "'all' overwrites every selected file")

    sc = ap.add_argument_group("scope filters (any of these skips the interactive gate)")
    sc.add_argument("--scope", metavar="NAME",
                    help="Preset (smoke/regression/security/accessibility/api/ui/"
                         "everything) or a saved scope from scopes.yaml")
    sc.add_argument("--priorities", nargs="+", metavar="P", help="e.g. P0 P1")
    sc.add_argument("--types", nargs="+", metavar="T",
                    help="e.g. functional negative boundary security")
    sc.add_argument("--targets", nargs="+", metavar="T", help="e.g. ui api")
    sc.add_argument("--requirements", dest="req_filter", nargs="+", metavar="REQ",
                    help="e.g. REQ-1 REQ-3 — only cases for these requirements")
    sc.add_argument("--ids", nargs="+", metavar="TC", help="e.g. TC-001 TC-007")
    sc.add_argument("--exclude-types", nargs="+", metavar="T",
                    help="drop these types, e.g. accessibility")
    sc.add_argument("--grep", metavar="REGEX",
                    help="keyword/regex over title, steps and expected result")
    sc.add_argument("--limit", type=int, metavar="N",
                    help="cap selection at N cases, highest priority first")
    sc.add_argument("--save-scope", metavar="NAME",
                    help="save the resulting scope to scopes.yaml under this name")
    sc.add_argument("--list-scopes", action="store_true",
                    help="list presets + saved scopes and exit")
    args = ap.parse_args()

    if args.list_scopes:
        print("Built-in presets:")
        for k, v in PRESETS.items():
            print(f"  {k:<15} — {v['description']}")
        saved = load_saved_scopes()
        if saved:
            print("Saved scopes (scopes.yaml):")
            for k, v in saved.items():
                print(f"  {k:<15} — {describe_scope(v)}")
        else:
            print("No saved scopes yet (scopes.yaml not found).")
        return

    if not args.requirements or not args.project:
        ap.error("requirements and project arguments are required")

    req_path = Path(args.requirements).resolve()
    project_root = Path(args.project).resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    if not req_path.exists():
        sys.exit(f"Requirements file not found: {req_path}")

    cfg = load_config(args.config)
    llm = get_provider(cfg["llm"])
    print(f"▶ LLM provider: {cfg['llm']['provider']} / {cfg['llm'].get('model', '<default>')}\n")

    requirements = req_path.read_text()
    summary: dict = {"stages": {}}

    # Stage 1 — Test Plan
    plan_path = project_root / "test_plan.md"
    if "1" in args.skip_stage and plan_path.exists():
        plan = plan_path.read_text()
        print(f"▶ Stage 1: SKIPPED (using existing {plan_path.name})\n")
    else:
        plan = stage1_plan(llm, requirements, project_root)
    summary["stages"]["plan"] = {"chars": len(plan)}

    # Stage 2 — Test Cases
    cases_path = project_root / "test_cases.json"
    if "2" in args.skip_stage and cases_path.exists():
        # Re-validate on load: the file may have been hand-edited since it
        # was written, and exporters/Stage 3 assume schema-complete cases.
        cases = validate_cases(json.loads(cases_path.read_text()))
        print(f"▶ Stage 2: SKIPPED (using existing {cases_path.name})\n")
    else:
        cases = stage2_cases(llm, requirements, plan, project_root)
    summary["stages"]["cases"] = {
        "total": len(cases),
        "by_requirement": dict(Counter(c.get("requirement_id", "?") for c in cases)),
    }

    # Coverage integrity: did any requirement end up with zero cases?
    report_path = project_root / "generation_report.json"
    gen_report = json.loads(report_path.read_text()) if report_path.exists() else {}
    summary["generation_report"] = gen_report
    empty_reqs = sorted(r for r, e in gen_report.items() if not e.get("generated"))
    if empty_reqs:
        print(f"  ⚠ Requirements with ZERO generated cases: {', '.join(empty_reqs)}")
        if args.strict:
            print("✗ --strict: some requirements have no cases.", file=sys.stderr)
            _write_summary(args.summary_json, summary, 2)
            sys.exit(2)

    # Export in all configured formats
    if cfg.get("exports"):
        run_exports(cases, project_root, cfg["exports"])

    # Direct Jira push — upsert each case, then persist the returned keys
    if args.push_jira:
        try:
            from integrations.jira_push import push_cases, JiraPushError
        except ImportError as e:
            sys.exit(f"✗ --push-jira needs the requests package "
                     f"(pip install requests): {e}")
        try:
            result = push_cases(cases, cfg.get("jira") or {})
        except JiraPushError as e:
            print(f"✗ Jira push failed: {e}", file=sys.stderr)
            _write_summary(args.summary_json, summary, 1)
            sys.exit(1)
        cases_path.write_text(json.dumps(cases, indent=2))
        summary["jira_push"] = {"created": result["created"],
                                "updated": result["updated"]}
        print(f"▶ Jira push: {result['created']} created, "
              f"{result['updated']} updated\n")

    # Stage 3 — Scope gate → Automation
    if "3" in args.skip_stage:
        print("▶ Stage 3: SKIPPED")
        _write_summary(args.summary_json, summary, 0)
        return

    scope = _build_scope_from_flags(args)
    scope_from_cli = scope is not None or args.non_interactive
    if scope is not None:
        print(f"▶ Scope (from flags): {describe_scope(scope)}\n")
        for w in validate_scope(cases, scope):
            print(f"  ⚠ {w}")
    elif args.non_interactive:
        scope = {}  # no filter
        print("▶ Scope: non-interactive, everything automatable\n")
    else:
        scope = prompt_scope(cases)

    if args.save_scope:
        path = save_scope(args.save_scope, scope)
        print(f"▶ Scope saved as '{args.save_scope}' in {path}")

    selected = apply_scope(cases, scope)
    cov = coverage_report(cases, selected)
    summary["scope"] = describe_scope(scope)
    summary["coverage"] = cov
    summary["selected"] = {"count": len(selected),
                           "ids": [c.get("id") for c in selected]}
    print(f"▶ Selected {len(selected)} cases — "
          f"{len(cov['covered'])}/{cov['total_requirements']} requirements covered.")
    if cov["uncovered"]:
        print(f"  ⚠ No cases selected for: {', '.join(cov['uncovered'])}")
    if not selected:
        msg = "No cases matched the scope filter. Nothing to automate."
        if scope_from_cli or args.strict:
            # Unattended run (flags / --non-interactive / --strict): fail
            # loudly so a CI job with an empty selection goes red, not green.
            print(f"✗ {msg}", file=sys.stderr)
            _write_summary(args.summary_json, summary, 2)
            sys.exit(2)
        print(msg)
        _write_summary(args.summary_json, summary, 0)
        return

    # Verify gate: explicit flag wins, otherwise on in CI, off locally
    check = args.check if args.check is not None else bool(os.environ.get("CI"))
    files = stage3_automate(llm, selected, project_root, all_cases=cases,
                            check=check, regen=args.regen)
    summary["stages"]["automation"] = {"files_written": len(files), "files": files}

    if check:
        verify_path = project_root / "verify_report.json"
        verify = (json.loads(verify_path.read_text())
                  if verify_path.exists() else {"status": "skipped"})
        summary["verify"] = verify
        if verify.get("status") == "failed":
            broken = sorted(verify.get("errors", {}))
            print(f"✗ Verification failed after repair: "
                  f"{', '.join(broken) or 'see verify_report.json'}",
                  file=sys.stderr)
            _write_summary(args.summary_json, summary, 1)
            sys.exit(1)

    # Suite execution: run the tests and map results back to TC-IDs
    if args.run:
        print("\n▶ Running suite: npx playwright test --reporter=json ...")
        outcome = run_suite(project_root, base_url=args.base_url,
                            api_url=args.api_url)
        summary["run"] = {"status": outcome["status"],
                          "error": outcome["error"],
                          "exit_code": outcome["exit_code"],
                          "aggregate": outcome["aggregate"]}
        if outcome["status"] == "error":
            print(f"✗ Suite run failed: {outcome['error']}", file=sys.stderr)
            _write_summary(args.summary_json, summary, 1)
            sys.exit(1)
        _print_run_table(outcome["aggregate"])
        print(f"▶ Results written to {project_root / 'results.json'}")
        failed = sum(1 for e in outcome["results"].values()
                     if e["status"] == "failed")
        if failed:
            print(f"✗ {failed} test case(s) failed.", file=sys.stderr)
            _write_summary(args.summary_json, summary, 1)
            sys.exit(1)

    _write_summary(args.summary_json, summary, 0)
    print("\n✅ Done.")


def _print_run_table(aggregate: dict) -> None:
    """Per-requirement pass/fail table for --run."""
    if not aggregate:
        print("  (no TC-IDs found in test titles — nothing to map)")
        return
    header = (f"  {'Requirement':<14}{'Passed':>8}{'Failed':>8}"
              f"{'Skipped':>9}{'Not run':>9}  Status")
    print(header)
    print("  " + "─" * (len(header) - 2))
    for req in sorted(aggregate):
        e = aggregate[req]
        mark = {"passed": "✓ PASS", "failed": "✗ FAIL",
                "skipped": "– SKIP"}.get(e["status"], "· NOT RUN")
        print(f"  {req:<14}{e['passed']:>8}{e['failed']:>8}"
              f"{e['skipped']:>9}{e['not_run']:>9}  {mark}")


def _write_summary(path: str | None, summary: dict, exit_status: int) -> None:
    """Dump the run summary with its final exit status. No-op without
    ``--summary-json``."""
    if not path:
        return
    summary["exit_status"] = exit_status
    Path(path).write_text(json.dumps(summary, indent=2))


def _build_scope_from_flags(args) -> dict | None:
    """Assemble a scope dict from CLI flags. Returns None when no scope flag
    was given, so the caller falls back to the interactive gate. ``--scope``
    resolves a preset or saved name; the other flags refine it further."""
    flag_filters = {
        "priorities": args.priorities,
        "types": args.types,
        "targets": args.targets,
        "requirements": args.req_filter,
        "ids": args.ids,
        "exclude_types": args.exclude_types,
        "grep": args.grep,
        "limit": args.limit,
    }
    flag_filters = {k: v for k, v in flag_filters.items() if v}

    if not args.scope and not flag_filters:
        return None

    try:
        scope = resolve_scope(args.scope) if args.scope else {}
    except KeyError as e:
        sys.exit(f"✗ {e.args[0]}")
    scope.update(flag_filters)
    return scope


if __name__ == "__main__":
    main()
