"""Tests for the scope gate (scope.py).

Cases use the REAL Stage 2 shape: steps are dicts {"action": str, "data": str|null}
(see prompts.CASE_WRITER_SYSTEM), so grep must match text inside actions/data.
"""

from __future__ import annotations

import pytest

from scope import (
    PRESETS,
    apply_scope,
    coverage_report,
    describe_scope,
    load_saved_scopes,
    resolve_scope,
    save_scope,
    validate_scope,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture: a realistic Stage-2 case set
# ──────────────────────────────────────────────────────────────────────────────

def _case(id, req, title, type_, target, priority, steps, *,
          page=None, preconditions=None, expected="", automatable=True) -> dict:
    return {
        "id": id,
        "requirement_id": req,
        "title": title,
        "type": type_,
        "target": target,
        "priority": priority,
        "page": page,
        "preconditions": preconditions or [],
        "steps": steps,
        "expected": expected,
        "automatable": automatable,
    }


@pytest.fixture
def cases() -> list[dict]:
    return [
        _case("TC-001", "REQ-1", "Login with valid credentials",
              "functional", "ui", "P0",
              steps=[{"action": "Navigate to /login", "data": None},
                     {"action": "Enter email", "data": "user@test.com"},
                     {"action": "Enter password and submit", "data": "S3cret!"}],
              page="LoginPage",
              preconditions=["Account user@test.com exists"],
              expected="Dashboard loads with welcome banner"),
        _case("TC-002", "REQ-1", "Reject wrong password",
              "negative", "ui", "P1",
              steps=[{"action": "Navigate to /login", "data": None},
                     {"action": "Enter password", "data": "wrong-pass"}],
              page="LoginPage",
              expected="Inline error shown, no session created"),
        _case("TC-003", "REQ-1", "Lockout after five failed attempts",
              "security", "ui", "P1",
              steps=[{"action": "Submit bad credentials five times", "data": None}],
              page="LoginPage",
              preconditions=["Rate limiting enabled"],
              expected="Account locked message"),
        _case("TC-004", "REQ-2", "Login API returns token",
              "functional", "api", "P0",
              steps=[{"action": "POST /api/login", "data": '{"email": "user@test.com"}'}],
              expected="200 with JWT in body"),
        _case("TC-005", "REQ-2", "Login API rejects malformed payload",
              "contract", "api", "P1",
              steps=[{"action": "POST /api/login", "data": '{"email": 42}'}],
              expected="400 with validation errors"),
        _case("TC-006", "REQ-2", "SQL injection in email field is rejected",
              "security", "api", "P0",
              steps=[{"action": "POST /api/login", "data": "' OR 1=1 --"}],
              expected="400, no stack trace leaked"),
        _case("TC-007", "REQ-3", "Form labels announced by screen reader",
              "accessibility", "ui", "P2",
              steps=[{"action": "Tab through the login form", "data": None}],
              page="LoginPage",
              expected="Every input has an accessible name"),
        _case("TC-008", "REQ-3", "Password reset email received",
              "functional", "manual", "P2",
              steps=[{"action": "Request reset and check real inbox", "data": None}],
              expected="Email arrives within 5 minutes",
              automatable=False),
        _case("TC-009", "REQ-1", "Boundary: email at max length accepted",
              "boundary", "ui", "P2",
              steps=[{"action": "Enter 254-char email", "data": "a" * 10 + "@x.io"}],
              page="LoginPage",
              expected="Login succeeds"),
    ]


def _ids(selected: list[dict]) -> list[str]:
    return [c["id"] for c in selected]


# ──────────────────────────────────────────────────────────────────────────────
# apply_scope — basics, dict-shaped steps must not blow up
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_scope_drops_manual_only(cases):
    out = apply_scope(cases, {})
    assert _ids(out) == [c["id"] for c in cases if c["automatable"]]
    assert "TC-008" not in _ids(out)


def test_none_scope_is_treated_as_empty(cases):
    assert _ids(apply_scope(cases, None)) == _ids(apply_scope(cases, {}))


def test_include_manual_pulls_in_non_automatable(cases):
    out = apply_scope(cases, {"include_manual": True})
    assert "TC-008" in _ids(out)
    assert len(out) == len(cases)


# ──────────────────────────────────────────────────────────────────────────────
# grep — must search inside dict step actions AND data
# ──────────────────────────────────────────────────────────────────────────────

def test_grep_matches_step_action(cases):
    # "Navigate" only appears in step actions, never in titles/expected
    out = apply_scope(cases, {"grep": "navigate"})
    assert _ids(out) == ["TC-001", "TC-002"]


def test_grep_matches_step_data(cases):
    # "wrong-pass" only appears in a step's data field
    out = apply_scope(cases, {"grep": "wrong-pass"})
    assert _ids(out) == ["TC-002"]


def test_grep_matches_preconditions(cases):
    out = apply_scope(cases, {"grep": "rate limiting"})
    assert _ids(out) == ["TC-003"]


def test_grep_regex_and_title(cases):
    out = apply_scope(cases, {"grep": "lockout|injection"})
    assert _ids(out) == ["TC-003", "TC-006"]


def test_grep_invalid_regex_falls_back_to_literal(cases):
    # "' OR 1=1 --" in TC-006 step data; "1=1 --" is a valid literal needle
    out = apply_scope(cases, {"grep": "1=1 --"})
    assert _ids(out) == ["TC-006"]
    # An unparseable pattern must not raise
    assert apply_scope(cases, {"grep": "[unclosed"}) == []


# ──────────────────────────────────────────────────────────────────────────────
# Presets
# ──────────────────────────────────────────────────────────────────────────────

EXPECTED_PRESET_IDS = {
    "smoke": ["TC-001", "TC-004"],
    "regression": ["TC-001", "TC-002", "TC-004", "TC-005"],
    "security": ["TC-003", "TC-006"],
    "accessibility": ["TC-007"],
    "api": ["TC-004", "TC-005", "TC-006"],
    "ui": ["TC-001", "TC-002", "TC-003", "TC-007", "TC-009"],
    "everything": ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005",
                   "TC-006", "TC-007", "TC-009"],
}


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_every_preset(cases, name):
    scope = {k: v for k, v in PRESETS[name].items() if k != "description"}
    assert _ids(apply_scope(cases, scope)) == EXPECTED_PRESET_IDS[name]


def test_expected_preset_table_covers_all_presets():
    assert set(EXPECTED_PRESET_IDS) == set(PRESETS)


# ──────────────────────────────────────────────────────────────────────────────
# Include / exclude filters
# ──────────────────────────────────────────────────────────────────────────────

def test_include_priorities(cases):
    assert _ids(apply_scope(cases, {"priorities": ["P0"]})) == ["TC-001", "TC-004", "TC-006"]


def test_include_requirements(cases):
    out = apply_scope(cases, {"requirements": ["REQ-2"]})
    assert _ids(out) == ["TC-004", "TC-005", "TC-006"]


def test_include_ids(cases):
    assert _ids(apply_scope(cases, {"ids": ["TC-003", "TC-009"]})) == ["TC-003", "TC-009"]


def test_exclude_types(cases):
    out = apply_scope(cases, {"exclude_types": ["security", "accessibility"]})
    assert _ids(out) == ["TC-001", "TC-002", "TC-004", "TC-005", "TC-009"]


def test_exclude_priorities(cases):
    out = apply_scope(cases, {"exclude_priorities": ["P2"]})
    assert "TC-007" not in _ids(out) and "TC-009" not in _ids(out)


def test_exclude_targets(cases):
    assert _ids(apply_scope(cases, {"exclude_targets": ["ui"]})) == ["TC-004", "TC-005", "TC-006"]


def test_exclude_requirements(cases):
    out = apply_scope(cases, {"exclude_requirements": ["REQ-1", "REQ-3"]})
    assert _ids(out) == ["TC-004", "TC-005", "TC-006"]


def test_exclude_ids(cases):
    out = apply_scope(cases, {"exclude_ids": ["TC-001"]})
    assert "TC-001" not in _ids(out)


def test_include_and_exclude_combine(cases):
    out = apply_scope(cases, {"targets": ["ui"], "exclude_types": ["accessibility"]})
    assert _ids(out) == ["TC-001", "TC-002", "TC-003", "TC-009"]


# ──────────────────────────────────────────────────────────────────────────────
# limit — highest priority kept, result in stable ID order
# ──────────────────────────────────────────────────────────────────────────────

def test_limit_keeps_highest_priority_first(cases):
    out = apply_scope(cases, {"limit": 3})
    assert _ids(out) == ["TC-001", "TC-004", "TC-006"]  # the three P0s


def test_limit_result_is_in_stable_id_order(cases):
    # 4th pick is the lowest-ID P1 (TC-002), which must slot back before the
    # higher-ID P0s in the final ID-ordered output
    out = apply_scope(cases, {"limit": 4})
    assert _ids(out) == ["TC-001", "TC-002", "TC-004", "TC-006"]


def test_limit_larger_than_selection_is_noop(cases):
    assert len(apply_scope(cases, {"limit": 99})) == 8


def test_limit_zero_is_ignored(cases):
    assert len(apply_scope(cases, {"limit": 0})) == 8


# ──────────────────────────────────────────────────────────────────────────────
# validate_scope
# ──────────────────────────────────────────────────────────────────────────────

def test_validate_unknown_key(cases):
    warnings = validate_scope(cases, {"priorty": ["P0"], "priorities": ["P0"]})
    assert any("Unknown scope key 'priorty'" in w for w in warnings)


def test_validate_impossible_value(cases):
    warnings = validate_scope(cases, {"priorities": ["P5"]})
    assert any("'P5' in scope['priorities'] matches no case" in w for w in warnings)


def test_validate_zero_case_scope(cases):
    warnings = validate_scope(cases, {"priorities": ["P0"], "types": ["accessibility"]})
    assert any("ZERO" in w for w in warnings)


def test_validate_clean_scope_has_no_warnings(cases):
    assert validate_scope(cases, {"priorities": ["P0"]}) == []


# ──────────────────────────────────────────────────────────────────────────────
# describe_scope
# ──────────────────────────────────────────────────────────────────────────────

def test_describe_empty_scope():
    assert describe_scope({}) == "everything automatable"
    assert describe_scope(None) == "everything automatable"


def test_describe_full_scope():
    desc = describe_scope({
        "priorities": ["P0", "P1"],
        "exclude_types": ["accessibility"],
        "grep": "login",
        "limit": 5,
        "include_manual": True,
    })
    assert "priorities=P0/P1" in desc
    assert "NOT types=accessibility" in desc
    assert "grep~'login'" in desc
    assert "limit=5" in desc
    assert "incl. manual cases" in desc


# ──────────────────────────────────────────────────────────────────────────────
# coverage_report
# ──────────────────────────────────────────────────────────────────────────────

def test_coverage_full(cases):
    cov = coverage_report(cases, cases)
    assert cov["total_requirements"] == 3
    assert cov["uncovered"] == []
    assert cov["covered"] == {"REQ-1": 4, "REQ-2": 3, "REQ-3": 2}


def test_coverage_reports_dropped_requirement(cases):
    selected = apply_scope(cases, {"requirements": ["REQ-2"]})
    cov = coverage_report(cases, selected)
    assert cov["covered"] == {"REQ-2": 3}
    assert cov["uncovered"] == ["REQ-1", "REQ-3"]
    assert cov["total_requirements"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# Saved scopes — save/load roundtrip, resolve
# ──────────────────────────────────────────────────────────────────────────────

def test_load_missing_file_returns_empty(tmp_path):
    assert load_saved_scopes(tmp_path / "scopes.yaml") == {}


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "scopes.yaml"
    scope = {"priorities": ["P0", "P1"], "grep": "login", "limit": 5}
    save_scope("ci-gate", scope, path)
    assert load_saved_scopes(path) == {"ci-gate": scope}


def test_save_merges_and_drops_junk_keys(tmp_path):
    path = tmp_path / "scopes.yaml"
    save_scope("first", {"priorities": ["P0"]}, path)
    # Falsy values and unknown keys must not be persisted
    save_scope("second", {"types": ["security"], "grep": None, "bogus": ["x"]}, path)
    saved = load_saved_scopes(path)
    assert saved == {"first": {"priorities": ["P0"]},
                     "second": {"types": ["security"]}}


def test_resolve_scope_preset(tmp_path):
    scope = resolve_scope("smoke", scopes_path=tmp_path / "scopes.yaml")
    assert scope == {"priorities": ["P0"], "types": ["functional"]}
    assert "description" not in scope


def test_resolve_scope_saved(tmp_path):
    path = tmp_path / "scopes.yaml"
    save_scope("payments-smoke", {"requirements": ["REQ-2"]}, path)
    assert resolve_scope("payments-smoke", scopes_path=path) == {"requirements": ["REQ-2"]}


def test_resolve_scope_unknown_raises_keyerror(tmp_path):
    with pytest.raises(KeyError, match="Unknown scope 'nope'"):
        resolve_scope("nope", scopes_path=tmp_path / "scopes.yaml")
