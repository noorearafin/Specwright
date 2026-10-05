"""Offline end-to-end smoke test: Stage 1 → Stage 2 → exports → scope gate
→ Stage 3 against a tmp_path project, with a StubProvider standing in for
the LLM. No network, no SDKs, no npm — the verify gate is off (check=False)
so the test stays hermetic even on machines that have node installed.

Asserts every cross-feature artifact exists and is well-formed: test_plan.md,
test_cases.json, generation_report.json, all 7 export formats (incl.
test_rtm.csv), the regeneration manifest, the scaffolded auth fixtures and
AUTOMATION_REPORT.md.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from config import DEFAULT_CONFIG
from exporters import run_exports
from prompts import (PLANNER_SYSTEM, ESTIMATOR_SYSTEM, CASE_WRITER_SYSTEM,
                     POM_SYSTEM, UI_SPEC_SYSTEM, API_SPEC_SYSTEM)
from providers.base import LLMProvider
from scope import apply_scope
from stages import stage1_plan, stage2_cases, stage3_automate


# ──────────────────────────────────────────────────────────────────────────────
# Canned, schema-valid stage outputs
# ──────────────────────────────────────────────────────────────────────────────

PLAN_MD = "# Test Plan\n\n## Scope\n- REQ-1 login\n- REQ-2 orders API\n"

ESTIMATE = {"cases_per_requirement": {"REQ-1": 2, "REQ-2": 3},
            "reasoning": "stub estimate"}


def _case(req_id: str, title: str, target: str, *, page: str | None = None,
          automatable: bool = True) -> dict:
    case = {
        "id": "TC-000",  # renumbered by stage 2
        "requirement_id": req_id,
        "title": title,
        "type": "functional",
        "target": target,
        "priority": "P0",
        "preconditions": ["App is reachable"],
        "steps": [{"action": "open the page", "data": None},
                  {"action": "submit the form", "data": "user@example.com"}],
        "expected": "it works",
        "automatable": automatable,
    }
    if page:
        case["page"] = page
    return case


CANNED_CASES = [
    _case("REQ-1", "Login happy path", "ui", page="LoginPage"),
    _case("REQ-1", "Login wrong password", "ui", page="LoginPage"),
    _case("REQ-2", "List orders", "api"),
    _case("REQ-2", "Create order", "api"),
    _case("REQ-2", "Exploratory order review", "manual", automatable=False),
]

TS_CODE = (
    "import { test, expect } from '@playwright/test';\n\n"
    "test('TC stub', async () => {\n"
    "  expect(1).toBe(1);\n"
    "});\n"
)


class StubProvider(LLMProvider):
    """Real LLMProvider subclass: implements complete() only, so Stage 2's
    complete_json() path (fence stripping included) runs for real. Dispatches
    on which system prompt stages.py sent."""

    name = "stub"
    max_output_tokens = 8000  # 5 cases × 500 ≤ cap → single batch call

    def __init__(self):
        self.systems: list[str] = []  # system prompts seen, in call order

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.2) -> str:
        self.systems.append(system)
        if system == PLANNER_SYSTEM:
            return PLAN_MD
        if system == ESTIMATOR_SYSTEM:
            return json.dumps(ESTIMATE)
        if system == CASE_WRITER_SYSTEM:
            # Fenced on purpose — exercises _parse_json's fence stripping
            return f"```json\n{json.dumps(CANNED_CASES)}\n```"
        if system in (POM_SYSTEM, UI_SPEC_SYSTEM, API_SPEC_SYSTEM):
            return TS_CODE
        raise AssertionError(f"Unexpected system prompt: {system[:80]}")


# ──────────────────────────────────────────────────────────────────────────────
# The smoke test
# ──────────────────────────────────────────────────────────────────────────────

def test_pipeline_end_to_end_offline(tmp_path: Path):
    llm = StubProvider()
    project = tmp_path / "project"
    project.mkdir()

    # Stage 1 — plan
    plan = stage1_plan(llm, "requirements text", project)
    assert plan == PLAN_MD
    assert (project / "test_plan.md").read_text() == PLAN_MD

    # Stage 2 — cases (estimator + single batch call, schema-validated)
    cases = stage2_cases(llm, "requirements text", plan, project)
    assert [c["id"] for c in cases] == [f"TC-{i:03d}" for i in range(1, 6)]
    assert all(isinstance(s, dict) and set(s) == {"action", "data"}
               for c in cases for s in c["steps"])
    on_disk = json.loads((project / "test_cases.json").read_text())
    assert on_disk == cases
    report = json.loads((project / "generation_report.json").read_text())
    assert report == {
        "REQ-1": {"estimated": 2, "generated": 2, "error": None},
        "REQ-2": {"estimated": 3, "generated": 3, "error": None},
    }

    # Exports — same default format list the CLI uses (config.py), so a
    # format added to the defaults without an exporters handler fails here.
    run_exports(cases, project, DEFAULT_CONFIG["exports"])
    for name in ("test_cases.csv", "test_cases.xlsx", "test_cases.jira.csv",
                 "test_cases.testrail.csv", "test_cases.html",
                 "test_cases.md", "test_rtm.csv"):
        assert (project / name).stat().st_size > 0, f"{name} missing/empty"

    # RTM CSV is well-formed: header + one OK row per requirement
    with (project / "test_rtm.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert {r["Requirement"]: r["Coverage"] for r in rows} == \
        {"REQ-1": "OK", "REQ-2": "OK"}
    assert {r["Requirement"]: r["Total Cases"] for r in rows} == \
        {"REQ-1": "2", "REQ-2": "3"}

    # Scope gate — empty scope keeps everything automatable, drops the manual
    selected = apply_scope(cases, {})
    assert len(selected) == 4
    assert all(c["automatable"] for c in selected)

    # Stage 3 — check=False keeps it hermetic (no npm/tsc even if installed)
    files = stage3_automate(llm, selected, project, all_cases=cases,
                            check=False)
    assert set(files) == {
        "tests/pages/LoginPage.ts",
        "tests/specs/req-1.spec.ts",
        "tests/api/req-2.spec.ts",
    }
    for rel in files:
        assert (project / rel).read_text() == TS_CODE

    # Scaffold: config, package files and the auth fixtures
    for rel in ("playwright.config.ts", "package.json", "tsconfig.json",
                ".env.example", "tests/fixtures/auth.setup.ts",
                "tests/fixtures/test.ts"):
        assert (project / rel).is_file(), f"{rel} not scaffolded"
    pkg = json.loads((project / "package.json").read_text())
    assert "@playwright/test" in pkg["devDependencies"]

    # Regeneration manifest records every generated file with both hashes
    manifest = json.loads(
        (project / ".specwright" / "manifest.json").read_text())
    assert set(manifest) == set(files)
    assert all({"file_sha256", "cases_sha256"} <= set(entry)
               for entry in manifest.values())

    # Report: files written, the manual case skipped, no verify section
    # and no verify_report.json (the gate never ran)
    report_md = (project / "AUTOMATION_REPORT.md").read_text()
    for rel in files:
        assert f"`{rel}`" in report_md
    assert "TC-005" in report_md  # the non-automatable case under Skipped
    assert "## Verification" not in report_md
    assert not (project / "verify_report.json").exists()

    # Every system prompt the pipeline needs was exercised exactly as wired
    assert llm.systems.count(PLANNER_SYSTEM) == 1
    assert llm.systems.count(ESTIMATOR_SYSTEM) == 1
    assert llm.systems.count(CASE_WRITER_SYSTEM) == 1
    assert llm.systems.count(POM_SYSTEM) == 1      # one page object
    assert llm.systems.count(UI_SPEC_SYSTEM) == 1  # one UI requirement
    assert llm.systems.count(API_SPEC_SYSTEM) == 1  # one API requirement
