"""The three pipeline stages. Stage 3 is now deterministic (no tool-use loop)
so it works with any LLM."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path

from prompts import (
    PLANNER_SYSTEM, ESTIMATOR_SYSTEM, CASE_WRITER_SYSTEM,
    POM_SYSTEM, UI_SPEC_SYSTEM, API_SPEC_SYSTEM,
)

# Rough budget per test case in tokens (JSON object with steps).
# Used to decide chunking: if total_cases × this > provider max, split per-REQ.
TOKENS_PER_CASE = 500


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Test Plan
# ──────────────────────────────────────────────────────────────────────────────
def stage1_plan(llm, requirements: str, out_dir: Path) -> str:
    print("▶ Stage 1: Writing test plan...")
    plan = llm.complete(
        system=PLANNER_SYSTEM,
        user=f"<requirements>\n{requirements}\n</requirements>\n\nWrite the test plan.",
        max_tokens=8000,
    )
    (out_dir / "test_plan.md").write_text(plan)
    print(f"  ✓ test_plan.md written ({len(plan)} chars)\n")
    return plan


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Test Cases (two-pass: estimate → generate, chunked if needed)
# ──────────────────────────────────────────────────────────────────────────────
def stage2_cases(llm, requirements: str, plan: str, out_dir: Path) -> list[dict]:
    print("▶ Stage 2: Writing test cases...")

    # Pass 1 — Estimator: LLM decides how many cases per requirement
    print("  • Pass 1/2: Estimating coverage...")
    estimate = llm.complete_json(
        system=ESTIMATOR_SYSTEM,
        user=(
            f"<requirements>\n{requirements}\n</requirements>\n\n"
            f"<test_plan>\n{plan}\n</test_plan>\n\n"
            "Return your coverage plan."
        ),
        max_tokens=2000,
    )
    per_req = estimate.get("cases_per_requirement", {})
    if not per_req:
        raise ValueError(f"Estimator returned no per-requirement counts: {estimate}")

    total = sum(per_req.values())
    print(f"  ✓ LLM plans {total} cases across {len(per_req)} requirements: "
          f"{dict(per_req)}")
    if estimate.get("reasoning"):
        print(f"  • Reasoning: {estimate['reasoning'][:200]}")

    # Pass 2 — Decide: single call or chunked?
    budget = total * TOKENS_PER_CASE
    cap = llm.max_output_tokens
    all_cases: list[dict] = []

    if budget <= cap:
        print(f"  • Pass 2/2: Generating all {total} cases in one call "
              f"(budget {budget} ≤ provider cap {cap})...")
        batch = llm.complete_json(
            system=CASE_WRITER_SYSTEM,
            user=_case_user_message(requirements, plan, per_req),
            max_tokens=cap,
        )
        all_cases = _normalize_cases(batch)
    else:
        print(f"  • Pass 2/2: Chunking per-requirement "
              f"(total budget {budget} > provider cap {cap})...")
        next_id = 1
        for i, (req_id, count) in enumerate(per_req.items(), 1):
            print(f"    [{i}/{len(per_req)}] Generating {count} cases for {req_id}...")
            req_budget = count * TOKENS_PER_CASE + 500  # padding for JSON overhead
            chunk_max = min(req_budget, cap)
            try:
                batch = llm.complete_json(
                    system=CASE_WRITER_SYSTEM,
                    user=_case_user_message(
                        requirements, plan, {req_id: count}, single_req=req_id,
                    ),
                    max_tokens=chunk_max,
                )
                chunk = _normalize_cases(batch, start_id=next_id)
                all_cases.extend(chunk)
                next_id += len(chunk)
                print(f"       ✓ got {len(chunk)} cases")
            except Exception as e:  # noqa: BLE001
                print(f"       ⚠ {req_id} failed: {e} — continuing")

            # Pause between calls (sequential-safe for free tiers)
            if i < len(per_req):
                time.sleep(1)

    # Renumber TC-IDs globally so they're unique regardless of chunking
    for idx, case in enumerate(all_cases, 1):
        case["id"] = f"TC-{idx:03d}"

    (out_dir / "test_cases.json").write_text(json.dumps(all_cases, indent=2))

    by_target = defaultdict(int)
    for c in all_cases:
        by_target[c.get("target", "?")] += 1
    print(f"  ✓ {len(all_cases)} cases written. By target: {dict(by_target)}\n")
    return all_cases


def _case_user_message(requirements: str, plan: str, per_req: dict,
                       single_req: str | None = None) -> str:
    """Build the user prompt for the case-writer pass."""
    if single_req:
        target_line = (
            f"Generate EXACTLY {per_req[single_req]} test cases for "
            f"requirement `{single_req}` only. Ignore other requirements."
        )
    else:
        breakdown = ", ".join(f"{k}={v}" for k, v in per_req.items())
        total = sum(per_req.values())
        target_line = (
            f"Generate EXACTLY {total} test cases total, distributed as: {breakdown}."
        )

    return (
        f"<requirements>\n{requirements}\n</requirements>\n\n"
        f"<test_plan>\n{plan}\n</test_plan>\n\n"
        f"{target_line}\n\n"
        "Return a JSON array only. No prose, no markdown fences."
    )


def _normalize_cases(batch, start_id: int = 1) -> list[dict]:
    """Accept either a bare list or an object wrapping one. Normalize to a list."""
    if isinstance(batch, dict):
        # Some models wrap: {"test_cases": [...]} or {"cases": [...]}
        for key in ("test_cases", "cases", "items", "data"):
            if key in batch and isinstance(batch[key], list):
                batch = batch[key]
                break
        else:
            raise ValueError(f"Expected list of cases, got object: {list(batch.keys())}")
    if not isinstance(batch, list):
        raise ValueError(f"Expected list of cases, got {type(batch).__name__}")
    return batch


# ──────────────────────────────────────────────────────────────────────────────
# Stage 3 — Automation (deterministic orchestration + LLM code gen per file)
# ──────────────────────────────────────────────────────────────────────────────
def stage3_automate(llm, cases: list[dict], project_root: Path) -> None:
    print("▶ Stage 3: Generating Playwright tests...")

    # 1. Project detection + scaffold (pure Python, no LLM)
    is_new = not (project_root / "playwright.config.ts").exists()
    if is_new:
        print("  • New project — scaffolding Playwright config...")
        _scaffold(project_root)

    # 2. Split by target
    ui_cases = [c for c in cases if c.get("target") == "ui"]
    api_cases = [c for c in cases if c.get("target") == "api"]
    print(f"  • UI cases: {len(ui_cases)}, API cases: {len(api_cases)}")

    files_written: list[str] = []

    # 3. For UI: figure out page objects, generate each
    if ui_cases:
        pages = _group_pages(ui_cases)  # {"LoginPage": [cases...], ...}
        print(f"  • Page objects needed: {list(pages.keys())}")

        for page_name, page_cases in pages.items():
            path = project_root / "tests" / "pages" / f"{page_name}.ts"
            if path.exists():
                print(f"    ↳ skip (exists): tests/pages/{page_name}.ts")
                continue
            code = llm.complete(
                system=POM_SYSTEM,
                user=_pom_user(page_name, page_cases),
                max_tokens=4000,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_clean_code(code))
            files_written.append(f"tests/pages/{page_name}.ts")
            print(f"    ✓ tests/pages/{page_name}.ts")

        # 4. UI spec files grouped by requirement
        by_req = _group_by(ui_cases, "requirement_id")
        for req_id, group in by_req.items():
            fname = _slug(req_id) + ".spec.ts"
            path = project_root / "tests" / "specs" / fname
            if path.exists():
                print(f"    ↳ skip (exists): tests/specs/{fname}")
                continue
            code = llm.complete(
                system=UI_SPEC_SYSTEM,
                user=_ui_spec_user(req_id, group),
                max_tokens=6000,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_clean_code(code))
            files_written.append(f"tests/specs/{fname}")
            print(f"    ✓ tests/specs/{fname}")

    # 5. API spec files grouped by requirement
    if api_cases:
        by_req = _group_by(api_cases, "requirement_id")
        for req_id, group in by_req.items():
            fname = _slug(req_id) + ".spec.ts"
            path = project_root / "tests" / "api" / fname
            if path.exists():
                print(f"    ↳ skip (exists): tests/api/{fname}")
                continue
            code = llm.complete(
                system=API_SPEC_SYSTEM,
                user=_api_spec_user(req_id, group),
                max_tokens=6000,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_clean_code(code))
            files_written.append(f"tests/api/{fname}")
            print(f"    ✓ tests/api/{fname}")

    # 6. Report
    _write_report(project_root, cases, files_written)
    print(f"\n  ✓ {len(files_written)} files written. See AUTOMATION_REPORT.md")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _group_pages(ui_cases: list[dict]) -> dict[str, list[dict]]:
    """Group UI cases by their `page` field. Infer from requirement_id if missing."""
    out: dict[str, list[dict]] = defaultdict(list)
    for c in ui_cases:
        name = c.get("page") or f"Req{c.get('requirement_id', 'Unknown').replace('REQ-', '')}Page"
        out[name].append(c)
    return dict(out)


def _group_by(cases: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        out[c.get(key, "UNGROUPED")].append(c)
    return dict(out)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _clean_code(code: str) -> str:
    """Strip accidental markdown fences from LLM output."""
    code = code.strip()
    fence = re.match(r"^```(?:typescript|ts)?\s*\n(.*?)\n```\s*$", code, re.DOTALL)
    if fence:
        code = fence.group(1).strip()
    return code + "\n"


def _pom_user(page_name: str, cases: list[dict]) -> str:
    return (
        f"Create a Page Object class named `{page_name}` for these cases.\n"
        f"Extract all the UI interactions you can infer.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


def _ui_spec_user(req_id: str, cases: list[dict]) -> str:
    pages = sorted({c.get("page") for c in cases if c.get("page")})
    return (
        f"Write a spec file for {req_id}.\n"
        f"Import these page objects from '../pages/': {pages}\n"
        f"Generate one test() per case. Use TC-ID in the title.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


def _api_spec_user(req_id: str, cases: list[dict]) -> str:
    return (
        f"Write an API spec file for {req_id} using Playwright's request fixture.\n"
        f"Generate one test() per case. Use TC-ID in the title.\n\n"
        f"Cases:\n{json.dumps(cases, indent=2)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Scaffold for new projects
# ──────────────────────────────────────────────────────────────────────────────
def _scaffold(root: Path) -> None:
    (root / "tests" / "pages").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "specs").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "api").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)

    pkg = root / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({
            "name": root.name, "version": "0.0.1", "private": True,
            "scripts": {
                "test": "playwright test",
                "test:ui": "playwright test tests/specs",
                "test:api": "playwright test tests/api",
            },
            "devDependencies": {
                "@playwright/test": "^1.50.0",
                "@types/node": "^20.0.0",
                "typescript": "^5.0.0",
                "dotenv": "^16.0.0",
            },
        }, indent=2))

    ts = root / "tsconfig.json"
    if not ts.exists():
        ts.write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022", "module": "commonjs", "strict": True,
                "esModuleInterop": True, "skipLibCheck": True,
            },
            "include": ["tests/**/*.ts"],
        }, indent=2))

    cfg = root / "playwright.config.ts"
    if not cfg.exists():
        cfg.write_text("""import { defineConfig, devices } from '@playwright/test';
import 'dotenv/config';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: [['html'], ['list']],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox',  use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit',   use: { ...devices['Desktop Safari'] } },
    { name: 'api', testDir: './tests/api',
      use: { baseURL: process.env.API_URL || process.env.BASE_URL } },
  ],
});
""")

    env = root / ".env.example"
    if not env.exists():
        env.write_text(
            "BASE_URL=http://localhost:3000\n"
            "API_URL=http://localhost:3000/api\n"
            "TEST_USER=test@example.com\n"
            "TEST_PASS=changeme\n"
        )


def _write_report(root: Path, cases: list[dict], files: list[str]) -> None:
    skipped = [c for c in cases if not c.get("automatable", True)]
    report = f"""# Automation Report

Generated {len(files)} files from {len(cases)} total test cases.

## Files Written ({len(files)})
{chr(10).join(f'- `{f}`' for f in files) or '_None_'}

## Skipped (non-automatable, {len(skipped)})
{chr(10).join(f'- **{c["id"]}** — {c["title"]}' for c in skipped) or '_None_'}

## Next Steps
```bash
npm install
npx playwright install
cp .env.example .env
npm test
```
"""
    (root / "AUTOMATION_REPORT.md").write_text(report)