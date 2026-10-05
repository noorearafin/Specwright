"""Tests for the suite runner (runner.py).

Everything runs offline: the Playwright JSON report parser and the
TC-ID → requirement roll-up are fed a canned report string, and run_suite's
toolchain/subprocess seams are monkeypatched — no npx anywhere.
"""

from __future__ import annotations

import json
import types

import runner
from runner import aggregate_results, parse_report, run_suite


# One file suite with a nested describe block (chromium + firefox for
# TC-005), a retried-then-passed spec (TC-002), a timeout (TC-003), a skip
# (TC-004) and a spec without any TC-ID — roughly what the generated suites
# produce under `npx playwright test --reporter=json`.
CANNED_REPORT = """\
{
  "config": {"rootDir": "/proj"},
  "suites": [
    {
      "title": "req-1.spec.ts",
      "specs": [],
      "suites": [
        {
          "title": "REQ-1 Login",
          "specs": [
            {
              "title": "TC-001: valid login redirects to dashboard @functional @P0",
              "tests": [
                {"projectName": "chromium",
                 "results": [{"status": "passed", "duration": 812}]}
              ]
            },
            {
              "title": "TC-002: session survives reload @functional @P1",
              "tests": [
                {"projectName": "chromium",
                 "results": [
                   {"status": "failed", "duration": 950,
                    "error": {"message": "locator timed out"}},
                   {"status": "passed", "duration": 640}
                 ]}
              ]
            },
            {
              "title": "TC-005: lockout after 5 bad attempts @security @P0",
              "tests": [
                {"projectName": "chromium",
                 "results": [{"status": "failed", "duration": 1200,
                              "error": {"message": "expected 423, got 200"}}]},
                {"projectName": "firefox",
                 "results": [{"status": "passed", "duration": 1100}]}
              ]
            }
          ]
        }
      ]
    },
    {
      "title": "req-2.spec.ts",
      "specs": [
        {
          "title": "TC-003: rate limit returns 429 @security @P1",
          "tests": [
            {"projectName": "chromium",
             "results": [{"status": "timedOut", "duration": 30000,
                          "errors": [{"message": "Test timeout of 30000ms exceeded."}]}]}
          ]
        },
        {
          "title": "TC-004: audit log entry written @functional @P2",
          "tests": [
            {"projectName": "chromium",
             "results": [{"status": "skipped", "duration": 0}]}
          ]
        },
        {
          "title": "smoke helper without an id",
          "tests": [
            {"projectName": "chromium",
             "results": [{"status": "passed", "duration": 5}]}
          ]
        }
      ]
    }
  ],
  "stats": {"expected": 3, "unexpected": 2, "skipped": 1}
}
"""

# TC-005 runs but belongs to no case; TC-006 exists but never runs.
CASES = [
    {"id": "TC-001", "requirement_id": "REQ-1"},
    {"id": "TC-002", "requirement_id": "REQ-1"},
    {"id": "TC-003", "requirement_id": "REQ-2"},
    {"id": "TC-004", "requirement_id": "REQ-2"},
    {"id": "TC-006", "requirement_id": "REQ-3"},
]


def _parsed() -> dict:
    return parse_report(json.loads(CANNED_REPORT))


# ──────────────────────────────────────────────────────────────────────────────
# parse_report — statuses, retries, nesting, merging
# ──────────────────────────────────────────────────────────────────────────────

def test_parse_walks_nested_suites_and_maps_all_tc_ids():
    assert set(_parsed()) == {"TC-001", "TC-002", "TC-003", "TC-004", "TC-005"}


def test_parse_passed_entry():
    assert _parsed()["TC-001"] == {"status": "passed", "duration_ms": 812,
                                   "error": None}


def test_parse_retry_keeps_last_result_and_drops_error():
    # Failed once, passed on retry → flaky counts as passed, no error kept
    assert _parsed()["TC-002"] == {"status": "passed", "duration_ms": 640,
                                   "error": None}


def test_parse_timed_out_maps_to_failed_with_errors_list_message():
    entry = _parsed()["TC-003"]
    assert entry["status"] == "failed"
    assert entry["error"] == "Test timeout of 30000ms exceeded."


def test_parse_skipped_entry():
    assert _parsed()["TC-004"]["status"] == "skipped"


def test_parse_merges_projects_pessimistically():
    # chromium failed + firefox passed → failure wins, durations add up
    entry = _parsed()["TC-005"]
    assert entry["status"] == "failed"
    assert entry["duration_ms"] == 2300
    assert entry["error"] == "expected 423, got 200"


def test_parse_ignores_titles_without_tc_id():
    assert all(tc.startswith("TC-") for tc in _parsed())


def test_parse_empty_report_yields_nothing():
    assert parse_report({}) == {}
    assert parse_report({"suites": []}) == {}


# ──────────────────────────────────────────────────────────────────────────────
# aggregate_results — per-requirement roll-up via test_cases.json
# ──────────────────────────────────────────────────────────────────────────────

def test_aggregate_rolls_up_per_requirement():
    agg = aggregate_results(_parsed(), CASES)
    assert agg["REQ-1"] == {"passed": 2, "failed": 0, "skipped": 0,
                            "not_run": 0, "total": 2, "status": "passed"}
    # One failure poisons the requirement even with a skip beside it
    assert agg["REQ-2"] == {"passed": 0, "failed": 1, "skipped": 1,
                            "not_run": 0, "total": 2, "status": "failed"}


def test_aggregate_counts_never_executed_cases_as_not_run():
    agg = aggregate_results(_parsed(), CASES)
    assert agg["REQ-3"] == {"passed": 0, "failed": 0, "skipped": 0,
                            "not_run": 1, "total": 1, "status": "not_run"}


def test_aggregate_buckets_unknown_tc_ids_under_question_mark():
    agg = aggregate_results(_parsed(), CASES)
    assert agg["?"]["failed"] == 1
    assert agg["?"]["total"] == 1


def test_aggregate_without_cases_puts_everything_under_question_mark():
    agg = aggregate_results(_parsed(), None)
    assert set(agg) == {"?"}
    assert agg["?"]["total"] == 5


# ──────────────────────────────────────────────────────────────────────────────
# run_suite — graceful errors + end-to-end with a stubbed subprocess
# ──────────────────────────────────────────────────────────────────────────────

def test_run_suite_without_npx_returns_structured_error(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    outcome = run_suite(tmp_path)
    assert outcome["status"] == "error"
    assert "npx not found" in outcome["error"]
    assert not (tmp_path / "results.json").exists()


def test_run_suite_without_config_returns_structured_error(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/npx")
    outcome = run_suite(tmp_path)
    assert outcome["status"] == "error"
    assert "playwright.config" in outcome["error"]


def test_run_suite_parses_report_and_writes_results_json(tmp_path, monkeypatch):
    (tmp_path / "playwright.config.ts").write_text("export default {};")
    (tmp_path / "test_cases.json").write_text(json.dumps(CASES))
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs.get("env", {})
        return types.SimpleNamespace(returncode=1, stdout=CANNED_REPORT, stderr="")

    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    outcome = run_suite(tmp_path, base_url="http://app:3000",
                        api_url="http://app:3000/api")
    assert outcome["status"] == "completed"
    assert outcome["exit_code"] == 1
    assert outcome["results"]["TC-001"]["status"] == "passed"
    assert outcome["aggregate"]["REQ-2"]["status"] == "failed"
    assert seen["cmd"][1:4] == ["playwright", "test", "--reporter=json"]
    assert seen["env"]["BASE_URL"] == "http://app:3000"
    assert seen["env"]["API_URL"] == "http://app:3000/api"

    written = json.loads((tmp_path / "results.json").read_text())
    assert written["TC-003"]["status"] == "failed"
    assert written["_aggregate"]["REQ-3"]["not_run"] == 1


def test_run_suite_with_garbage_output_returns_structured_error(tmp_path, monkeypatch):
    (tmp_path / "playwright.config.ts").write_text("export default {};")
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda cmd, **kw: types.SimpleNamespace(
            returncode=1, stdout="", stderr="Error: Cannot find module 'playwright'"))
    outcome = run_suite(tmp_path)
    assert outcome["status"] == "error"
    assert "no JSON report" in outcome["error"]
    assert "Cannot find module" in outcome["error"]


def test_run_suite_tolerates_noise_before_the_json(tmp_path, monkeypatch):
    (tmp_path / "playwright.config.ts").write_text("export default {};")
    noisy = "npm warn deprecated something\n" + CANNED_REPORT
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout=noisy, stderr=""))
    outcome = run_suite(tmp_path)
    assert outcome["status"] == "completed"
    assert len(outcome["results"]) == 5
