"""Tests for Stage-2 coverage integrity (stages.py).

Uses a stub LLM so everything runs offline: canned estimator response plus
canned (or failing) per-requirement chunks. Verifies the retry loop and
that generation_report.json counts estimated vs generated correctly.
"""

from __future__ import annotations

import json
import re

import pytest

import stages
from stages import CHUNK_RETRIES, _build_generation_report, stage2_cases


# ──────────────────────────────────────────────────────────────────────────────
# Stub LLM — no network, no SDKs
# ──────────────────────────────────────────────────────────────────────────────

def _case(req_id: str, title: str) -> dict:
    return {
        "requirement_id": req_id,
        "title": title,
        "type": "functional",
        "target": "api",
        "priority": "P1",
        "preconditions": [],
        "steps": [{"action": "do it", "data": None}],
        "expected": "works",
        "automatable": True,
    }


class StubLLM:
    """First complete_json call returns the estimate; later calls return the
    canned chunk for the requirement named in the prompt (or raise)."""

    max_output_tokens = 1000  # small cap → forces per-requirement chunking

    def __init__(self, estimate: dict, chunks: dict,
                 fail_times: dict | None = None):
        self.estimate = estimate
        self.chunks = chunks               # req_id → list of case dicts
        self.fail_times = dict(fail_times or {})  # req_id → failures to throw
        self.calls: list[str] = []         # "estimate" or req_id, in order

    def complete_json(self, system, user, max_tokens=16000, temperature=0.1):
        if not self.calls:
            self.calls.append("estimate")
            return self.estimate
        m = re.search(r"requirement `(\S+)` only", user)
        req_id = m.group(1) if m else "__batch__"
        self.calls.append(req_id)
        if self.fail_times.get(req_id, 0) > 0:
            self.fail_times[req_id] -= 1
            raise ValueError(f"synthetic failure for {req_id}")
        return self.chunks[req_id]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip the inter-call pauses and retry backoff."""
    monkeypatch.setattr(stages.time, "sleep", lambda s: None)


def _estimate(per_req: dict) -> dict:
    return {"cases_per_requirement": per_req, "reasoning": "stub"}


ALWAYS = 10 ** 6  # more failures than any retry loop will attempt


# ──────────────────────────────────────────────────────────────────────────────
# _build_generation_report — the counting logic itself
# ──────────────────────────────────────────────────────────────────────────────

def test_report_counts_generated_per_requirement():
    cases = [_case("REQ-1", "a"), _case("REQ-1", "b"), _case("REQ-2", "c")]
    report = _build_generation_report(
        {"REQ-1": 2, "REQ-2": 5, "REQ-3": 3}, cases, {"REQ-3": "boom"})
    assert report == {
        "REQ-1": {"estimated": 2, "generated": 2, "error": None},
        "REQ-2": {"estimated": 5, "generated": 1, "error": None},
        "REQ-3": {"estimated": 3, "generated": 0, "error": "boom"},
    }


def test_report_ignores_cases_for_unestimated_requirements():
    report = _build_generation_report({"REQ-1": 1}, [_case("REQ-9", "x")], {})
    assert report == {"REQ-1": {"estimated": 1, "generated": 0, "error": None}}


# ──────────────────────────────────────────────────────────────────────────────
# stage2_cases — chunked generation end to end (offline)
# ──────────────────────────────────────────────────────────────────────────────

def test_chunked_run_writes_accurate_report(tmp_path):
    llm = StubLLM(
        _estimate({"REQ-1": 2, "REQ-2": 2}),  # 4 × 500 tokens > cap → chunked
        chunks={
            "REQ-1": [_case("REQ-1", "a"), _case("REQ-1", "b")],
            "REQ-2": [_case("REQ-2", "c")],  # under-delivers: 1 of 2
        },
    )
    cases = stage2_cases(llm, "reqs", "plan", tmp_path)

    assert len(cases) == 3
    assert [c["id"] for c in cases] == ["TC-001", "TC-002", "TC-003"]
    report = json.loads((tmp_path / "generation_report.json").read_text())
    assert report == {
        "REQ-1": {"estimated": 2, "generated": 2, "error": None},
        "REQ-2": {"estimated": 2, "generated": 1, "error": None},
    }
    # test_cases.json still written as before
    assert json.loads((tmp_path / "test_cases.json").read_text()) == cases


def test_failed_chunk_is_retried_then_recorded(tmp_path):
    llm = StubLLM(
        _estimate({"REQ-1": 2, "REQ-2": 2}),
        chunks={"REQ-1": [_case("REQ-1", "a"), _case("REQ-1", "b")]},
        fail_times={"REQ-2": ALWAYS},
    )
    cases = stage2_cases(llm, "reqs", "plan", tmp_path)

    # REQ-2 got the initial attempt plus CHUNK_RETRIES extras, then gave up
    assert llm.calls.count("REQ-2") == 1 + CHUNK_RETRIES
    assert [c["requirement_id"] for c in cases] == ["REQ-1", "REQ-1"]
    report = json.loads((tmp_path / "generation_report.json").read_text())
    assert report["REQ-1"] == {"estimated": 2, "generated": 2, "error": None}
    assert report["REQ-2"]["generated"] == 0
    assert "synthetic failure" in report["REQ-2"]["error"]


def test_transient_chunk_failure_recovers_on_retry(tmp_path):
    llm = StubLLM(
        _estimate({"REQ-1": 2, "REQ-2": 2}),
        chunks={
            "REQ-1": [_case("REQ-1", "a"), _case("REQ-1", "b")],
            "REQ-2": [_case("REQ-2", "c"), _case("REQ-2", "d")],
        },
        fail_times={"REQ-2": 1},  # first attempt fails, retry succeeds
    )
    cases = stage2_cases(llm, "reqs", "plan", tmp_path)

    assert llm.calls.count("REQ-2") == 2
    assert len(cases) == 4
    report = json.loads((tmp_path / "generation_report.json").read_text())
    assert report["REQ-2"] == {"estimated": 2, "generated": 2, "error": None}


def test_single_call_path_also_writes_report(tmp_path):
    llm = StubLLM(
        _estimate({"REQ-1": 1}),  # 1 × 500 tokens ≤ cap → one batch call
        chunks={"__batch__": [_case("REQ-1", "a")]},
    )
    cases = stage2_cases(llm, "reqs", "plan", tmp_path)

    assert llm.calls == ["estimate", "__batch__"]
    assert len(cases) == 1
    report = json.loads((tmp_path / "generation_report.json").read_text())
    assert report == {"REQ-1": {"estimated": 1, "generated": 1, "error": None}}


def test_generated_cases_are_schema_validated(tmp_path):
    # A bare-string step and a missing automatable flag must come back
    # coerced, and non-dict junk in the batch must be dropped.
    sloppy = {"requirement_id": "REQ-1", "title": "sloppy",
              "steps": ["press enter"]}
    llm = StubLLM(
        _estimate({"REQ-1": 1}),
        chunks={"__batch__": [sloppy, "stray prose line"]},
    )
    cases = stage2_cases(llm, "reqs", "plan", tmp_path)

    assert len(cases) == 1
    assert cases[0]["steps"] == [{"action": "press enter", "data": None}]
    assert cases[0]["automatable"] is True
    assert cases[0]["priority"] == "P2"
