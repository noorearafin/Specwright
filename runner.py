"""Suite runner — executes the generated Playwright project and maps the
outcome back to TC-IDs.

``npx playwright test --reporter=json`` runs in the project root (BASE_URL /
API_URL merged into the environment when given), the JSON report is parsed
defensively (suites nest arbitrarily; each spec carries tests[].results[]),
and every spec title is matched against ``TC-\\d+``. The mapping lands in
results.json next to the suite:

    {"TC-001": {"status": "passed", "duration_ms": 812, "error": null},
     ...,
     "_aggregate": {"REQ-1": {"passed": 2, "failed": 1, ...}}}

The per-requirement roll-up joins through test_cases.json when present.
Pure subprocess + JSON handling — no LLM calls here."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# A full suite against a slow staging target can take a while.
RUN_TIMEOUT_SECONDS = 1800

_TC_ID = re.compile(r"TC-\d+")

# Playwright result statuses → our three buckets
_STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "timedOut": "failed",
    "interrupted": "failed",
    "skipped": "skipped",
}

# Merge order when one TC-ID produced several entries (multiple projects/
# browsers, or several test() blocks): any failure wins, skipped loses.
_STATUS_RANK = {"failed": 0, "passed": 1, "skipped": 2}


def run_suite(project_root: Path, base_url: str | None = None,
              api_url: str | None = None,
              extra_args: list[str] | None = None) -> dict:
    """Run the Playwright suite in ``project_root`` and map results to TC-IDs.

    Returns ``{"status": "completed"|"error", "error": str|None,
    "exit_code": int|None, "results": {tc_id: {"status", "duration_ms",
    "error"}}, "aggregate": {requirement: roll-up}}``. On a completed run,
    results.json is written next to the suite (per-case entries plus an
    "_aggregate" key). Never raises: a missing toolchain or missing suite
    yields status "error" with the reason in "error"."""
    project_root = Path(project_root)
    outcome: dict = {"status": "error", "error": None, "exit_code": None,
                     "results": {}, "aggregate": {}}

    npx = shutil.which("npx")
    if not npx:
        outcome["error"] = "npx not found on PATH — install Node.js to run the suite"
        return outcome
    if not any(project_root.glob("playwright.config.*")):
        outcome["error"] = (f"No playwright.config.* in {project_root} — "
                            "generate the suite (Stage 3) first")
        return outcome

    env = os.environ.copy()
    if base_url:
        env["BASE_URL"] = base_url
    if api_url:
        env["API_URL"] = api_url

    cmd = [npx, "playwright", "test", "--reporter=json"] + list(extra_args or [])
    try:
        proc = subprocess.run(
            cmd, cwd=project_root, env=env, capture_output=True, text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        outcome["error"] = f"playwright test did not finish: {e}"
        return outcome
    outcome["exit_code"] = proc.returncode

    report = _extract_json(proc.stdout or "")
    if report is None:
        # Exit 1 with a report just means tests failed; no report at all
        # means the run itself broke (missing deps, bad config, ...).
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-2000:]
        outcome["error"] = ("playwright produced no JSON report"
                            + (f" — output tail:\n{tail}" if tail else ""))
        return outcome

    results = parse_report(report)
    aggregate = aggregate_results(results, _load_cases(project_root))
    outcome.update(status="completed", results=results, aggregate=aggregate)

    payload: dict = dict(results)
    payload["_aggregate"] = aggregate
    (project_root / "results.json").write_text(json.dumps(payload, indent=2))
    return outcome


def parse_report(report: dict) -> dict[str, dict]:
    """Map a Playwright JSON report to ``{tc_id: {"status", "duration_ms",
    "error"}}``.

    Suites nest arbitrarily (file → describe → ...), so specs are collected
    recursively. A test keeps its LAST result (retries: a flaky pass is a
    pass). When one TC-ID shows up in several entries, they merge
    pessimistically — any failure wins, durations add up, the first error
    message is kept. Spec titles without a TC-ID are ignored: they cannot
    be traced back to a case."""
    results: dict[str, dict] = {}
    for spec in _walk_specs(report.get("suites") or []):
        m = _TC_ID.search(spec.get("title") or "")
        if not m:
            continue
        tc_id = m.group(0)
        for test in spec.get("tests") or []:
            if not isinstance(test, dict):
                continue
            entry = _test_entry(test)
            prev = results.get(tc_id)
            results[tc_id] = entry if prev is None else _merge(prev, entry)
    return results


def aggregate_results(results: dict[str, dict],
                      cases: list[dict] | None) -> dict[str, dict]:
    """Per-requirement roll-up: ``{requirement: {"passed", "failed",
    "skipped", "not_run", "total", "status"}}``.

    ``cases`` (test_cases.json) supplies the TC → requirement join; a
    requirement's cases that never ran count as "not_run". Executed TC-IDs
    that match no known case land under "?" so they're never dropped
    silently."""
    tc_to_req = {c.get("id"): c.get("requirement_id", "?") for c in cases or []}
    rollup: dict[str, dict] = {}

    def bucket(req: str) -> dict:
        return rollup.setdefault(req, {"passed": 0, "failed": 0, "skipped": 0,
                                       "not_run": 0, "total": 0,
                                       "status": "not_run"})

    for tc_id, req in tc_to_req.items():
        b = bucket(req)
        b["total"] += 1
        b[results[tc_id]["status"] if tc_id in results else "not_run"] += 1
    for tc_id, entry in results.items():
        if tc_id in tc_to_req:
            continue
        b = bucket("?")
        b["total"] += 1
        b[entry["status"]] += 1

    for b in rollup.values():
        if b["failed"]:
            b["status"] = "failed"
        elif b["passed"]:
            b["status"] = "passed"
        elif b["skipped"]:
            b["status"] = "skipped"
    return rollup


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _walk_specs(suites: list):
    """Yield every spec dict from an arbitrarily nested suite tree."""
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        for spec in suite.get("specs") or []:
            if isinstance(spec, dict):
                yield spec
        yield from _walk_specs(suite.get("suites") or [])


def _test_entry(test: dict) -> dict:
    """One {status, duration_ms, error} entry from a test's result list.
    The last result decides the status (retries), its duration is kept,
    and the error message only survives on a failure."""
    runs = [r for r in test.get("results") or [] if isinstance(r, dict)]
    if not runs:
        return {"status": "skipped", "duration_ms": 0, "error": None}
    last = runs[-1]
    status = _STATUS_MAP.get(last.get("status"), "failed")
    return {
        "status": status,
        "duration_ms": int(last.get("duration") or 0),
        "error": _error_message(last) if status == "failed" else None,
    }


def _merge(a: dict, b: dict) -> dict:
    """Combine two entries for the same TC-ID (see parse_report)."""
    return {
        "status": min(a["status"], b["status"], key=_STATUS_RANK.__getitem__),
        "duration_ms": a["duration_ms"] + b["duration_ms"],
        "error": a["error"] or b["error"],
    }


def _error_message(result: dict) -> str | None:
    """First error message on a result — 'error' object or 'errors' list."""
    err = result.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    for e in result.get("errors") or []:
        if isinstance(e, dict) and e.get("message"):
            return str(e["message"])
    return None


def _extract_json(output: str) -> dict | None:
    """The JSON reporter owns stdout, but wrappers sometimes prepend noise
    (npm banners, warnings). Parse the whole output first, then retry from
    the first '{'."""
    candidates = [output]
    brace = output.find("{")
    if brace > 0:
        candidates.append(output[brace:])
    for text in candidates:
        if not text.strip():
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _load_cases(project_root: Path) -> list[dict]:
    """test_cases.json when present and valid, else []."""
    path = project_root / "test_cases.json"
    if not path.exists():
        return []
    try:
        cases = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    return cases if isinstance(cases, list) else []
