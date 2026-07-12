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

Config chooses the LLM provider (gemini, groq, ollama, anthropic) and optional
export formats. Between stages 2 and 3, a scope gate decides which cases to
automate — interactively, via --scope <preset|saved-name>, or via filter flags.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import load_config
from providers import get_provider
from stages import stage1_plan, stage2_cases, stage3_automate
from scope import (PRESETS, prompt_scope, apply_scope, resolve_scope,
                   validate_scope, describe_scope, coverage_report,
                   load_saved_scopes, save_scope)
from exporters import run_exports


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requirements", nargs="?", help="Path to .md/.txt requirements doc")
    ap.add_argument("project", nargs="?",
                    help="Path to project dir (new or existing Playwright)")
    ap.add_argument("--config", default="config.yaml", help="Path to config file")
    ap.add_argument("--skip-stage", action="append", choices=["1", "2", "3"], default=[])
    ap.add_argument("--non-interactive", action="store_true",
                    help="Skip scope gate (use everything automatable)")

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

    # Stage 1 — Test Plan
    plan_path = project_root / "test_plan.md"
    if "1" in args.skip_stage and plan_path.exists():
        plan = plan_path.read_text()
        print(f"▶ Stage 1: SKIPPED (using existing {plan_path.name})\n")
    else:
        plan = stage1_plan(llm, requirements, project_root)

    # Stage 2 — Test Cases
    cases_path = project_root / "test_cases.json"
    if "2" in args.skip_stage and cases_path.exists():
        cases = json.loads(cases_path.read_text())
        print(f"▶ Stage 2: SKIPPED (using existing {cases_path.name})\n")
    else:
        cases = stage2_cases(llm, requirements, plan, project_root)

    # Export in all configured formats
    if cfg.get("exports"):
        run_exports(cases, project_root, cfg["exports"])

    # Stage 3 — Scope gate → Automation
    if "3" in args.skip_stage:
        print("▶ Stage 3: SKIPPED")
        return

    scope = _build_scope_from_flags(args)
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
    print(f"▶ Selected {len(selected)} cases — "
          f"{len(cov['covered'])}/{cov['total_requirements']} requirements covered.")
    if cov["uncovered"]:
        print(f"  ⚠ No cases selected for: {', '.join(cov['uncovered'])}")
    if not selected:
        print("No cases matched the scope filter. Nothing to automate.")
        return

    stage3_automate(llm, selected, project_root)
    print("\n✅ Done.")


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
