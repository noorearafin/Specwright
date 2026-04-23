"""
QA Agent v2 — PRD → Test Plan → Test Cases → (scope gate) → Playwright TS suite

Usage:
    python qa_agent.py path/to/requirements.md path/to/project_dir [--config config.yaml]

Config chooses the LLM provider (gemini, groq, ollama, anthropic) and optional
export formats. Between stages 2 and 3, an interactive scope gate asks which
cases to automate (smoke / regression / security / custom / everything).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import load_config
from providers import get_provider
from stages import stage1_plan, stage2_cases, stage3_automate
from scope import prompt_scope, apply_scope
from exporters import run_exports


def main():
    """Entry point for the CLI pipeline.

    Runs three stages in order:
      1. Generate a test plan from the requirements document (IEEE 829 format).
      2. Generate detailed test cases (two-pass: estimate counts, then write cases).
      3. Ask which cases to automate (scope gate), then generate Playwright TypeScript.

    Each stage writes its output to disk so you can resume with --skip-stage if
    a stage already completed successfully.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("requirements", help="Path to .md/.txt requirements doc")
    ap.add_argument("project", help="Path to project dir (new or existing Playwright)")
    ap.add_argument("--config", default="config.yaml", help="Path to config file")
    # --skip-stage lets you re-run only the stages you need after partial failure
    ap.add_argument("--skip-stage", action="append", choices=["1", "2", "3"], default=[])
    ap.add_argument("--non-interactive", action="store_true",
                    help="Skip scope gate (use everything automatable)")
    args = ap.parse_args()

    req_path = Path(args.requirements).resolve()
    project_root = Path(args.project).resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    if not req_path.exists():
        sys.exit(f"Requirements file not found: {req_path}")

    # Load config and instantiate the chosen LLM provider
    cfg = load_config(args.config)
    llm = get_provider(cfg["llm"])
    print(f"▶ LLM provider: {cfg['llm']['provider']} / {cfg['llm'].get('model', '<default>')}\n")

    requirements = req_path.read_text()

    # ── Stage 1 — Test Plan ───────────────────────────────────────────────────
    # If a plan already exists and the user asked to skip, load it from disk
    # instead of hitting the LLM again (saves tokens and time on reruns).
    plan_path = project_root / "test_plan.md"
    if "1" in args.skip_stage and plan_path.exists():
        plan = plan_path.read_text()
        print(f"▶ Stage 1: SKIPPED (using existing {plan_path.name})\n")
    else:
        plan = stage1_plan(llm, requirements, project_root)

    # ── Stage 2 — Test Cases ──────────────────────────────────────────────────
    # Same disk-cache logic: if test_cases.json exists and stage is skipped,
    # reload it so Stage 3 still has data to work with.
    cases_path = project_root / "test_cases.json"
    if "2" in args.skip_stage and cases_path.exists():
        cases = json.loads(cases_path.read_text())
        print(f"▶ Stage 2: SKIPPED (using existing {cases_path.name})\n")
    else:
        cases = stage2_cases(llm, requirements, plan, project_root)

    # Export test cases in all configured formats (CSV, Excel, Jira, etc.)
    if cfg.get("exports"):
        run_exports(cases, project_root, cfg["exports"])

    # ── Stage 3 — Scope gate → Automation ────────────────────────────────────
    if "3" in args.skip_stage:
        print("▶ Stage 3: SKIPPED")
        return

    # Non-interactive mode skips the CLI scope-selection prompt entirely —
    # useful in CI/CD pipelines where there's no human to answer questions.
    if args.non_interactive:
        scope = {}  # empty scope = no filter, all automatable cases pass through
        print("▶ Scope: non-interactive, everything automatable\n")
    else:
        # Interactive prompt lets the user choose smoke / regression / custom filters
        scope = prompt_scope(cases)

    selected = apply_scope(cases, scope)
    if not selected:
        print("No cases matched the scope filter. Nothing to automate.")
        return

    stage3_automate(llm, selected, project_root)
    print("\n✅ Done.")


if __name__ == "__main__":
    main()
