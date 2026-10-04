"""Tests for the Requirement Traceability Matrix export (exporters.py).

Builds RTM rows from a small in-memory case list, with a stub
generation_report.json supplying a requirement that generated zero cases,
and checks the per-requirement counts, the gap rows and the CSV output.
"""

from __future__ import annotations

import csv
import json

from exporters import build_rtm_rows, export_rtm


def _case(req_id: str, tc_id: str, priority: str = "P1",
          automatable: bool = True) -> dict:
    return {
        "id": tc_id,
        "requirement_id": req_id,
        "title": f"case {tc_id}",
        "type": "functional",
        "target": "api",
        "priority": priority,
        "preconditions": [],
        "steps": [{"action": "do it", "data": None}],
        "expected": "works",
        "automatable": automatable,
    }


CASES = [
    _case("REQ-1", "TC-001", "P0"),
    _case("REQ-1", "TC-002", "P1", automatable=False),
    _case("REQ-1", "TC-003", "P2"),
    _case("REQ-2", "TC-004", "P0"),
]


def _stub_report(tmp_path, entries: dict) -> None:
    (tmp_path / "generation_report.json").write_text(json.dumps(entries))


# ──────────────────────────────────────────────────────────────────────────────
# build_rtm_rows — counts, splits and ordering
# ──────────────────────────────────────────────────────────────────────────────

def test_rows_count_priorities_and_automation_per_requirement():
    rows = build_rtm_rows(CASES)
    assert [r["requirement"] for r in rows] == ["REQ-1", "REQ-2"]

    req1 = rows[0]
    assert req1["total"] == 3
    assert (req1["p0"], req1["p1"], req1["p2"]) == (1, 1, 1)
    assert (req1["automatable"], req1["manual"]) == (2, 1)
    assert req1["case_ids"] == ["TC-001", "TC-002", "TC-003"]
    assert req1["gap"] is False

    req2 = rows[1]
    assert req2["total"] == 1
    assert (req2["p0"], req2["p1"], req2["p2"]) == (1, 0, 0)


def test_zero_case_requirement_becomes_gap_row(tmp_path):
    _stub_report(tmp_path, {
        "REQ-1": {"estimated": 3, "generated": 3, "error": None},
        "REQ-2": {"estimated": 1, "generated": 1, "error": None},
        "REQ-3": {"estimated": 4, "generated": 0, "error": "boom"},
    })
    rows = build_rtm_rows(CASES, tmp_path)
    assert [r["requirement"] for r in rows] == ["REQ-1", "REQ-2", "REQ-3"]

    gap = rows[-1]
    assert gap["gap"] is True
    assert gap["total"] == 0
    assert gap["case_ids"] == []
    # Covered requirements never read as gaps
    assert all(not r["gap"] for r in rows[:-1])


def test_no_report_means_no_gap_rows(tmp_path):
    rows = build_rtm_rows(CASES, tmp_path)
    assert [r["requirement"] for r in rows] == ["REQ-1", "REQ-2"]
    assert all(not r["gap"] for r in rows)


def test_last_run_rollup_from_results():
    results = {"TC-001": "passed", "TC-002": "passed", "TC-003": "failed"}
    rows = build_rtm_rows(CASES, results=results)
    assert rows[0]["last_run"] == "2 passed, 1 failed"
    # REQ-2's case never ran → no roll-up
    assert rows[1]["last_run"] is None


# ──────────────────────────────────────────────────────────────────────────────
# export_rtm — the CSV on disk
# ──────────────────────────────────────────────────────────────────────────────

def test_export_rtm_writes_csv_with_gap_row(tmp_path):
    _stub_report(tmp_path, {
        "REQ-3": {"estimated": 2, "generated": 0, "error": None},
    })
    path = export_rtm(CASES, tmp_path)
    assert path.name == "test_rtm.csv"

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Requirement", "Coverage", "Total Cases", "P0", "P1",
                       "P2", "Automatable", "Manual", "Case IDs"]
    by_req = {r[0]: r for r in rows[1:]}
    assert by_req["REQ-1"][1:9] == ["OK", "3", "1", "1", "1", "2", "1",
                                    "TC-001, TC-002, TC-003"]
    assert by_req["REQ-3"][1:3] == ["GAP", "0"]


def test_export_rtm_adds_last_run_column_when_results_given(tmp_path):
    path = export_rtm(CASES, tmp_path, results={"TC-004": "passed"})
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][-1] == "Last Run"
    by_req = {r[0]: r for r in rows[1:]}
    assert by_req["REQ-2"][-1] == "1 passed"
    assert by_req["REQ-1"][-1] == ""
