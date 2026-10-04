"""Tests for the Stage-2 case schema (schema.py).

validate_case must coerce near-miss LLM output into the exact shape
documented in prompts.CASE_WRITER_SYSTEM, and fill safe defaults rather
than raise on missing fields.
"""

from __future__ import annotations

import pytest

from schema import validate_case, validate_cases


FULL_CASE = {
    "id": "TC-001",
    "requirement_id": "REQ-1",
    "title": "Login with valid credentials",
    "type": "functional",
    "target": "ui",
    "priority": "P0",
    "page": "LoginPage",
    "preconditions": ["Account exists"],
    "steps": [{"action": "Navigate to /login", "data": None},
              {"action": "Enter email", "data": "user@test.com"}],
    "expected": "Dashboard loads",
    "automatable": True,
}


# ──────────────────────────────────────────────────────────────────────────────
# Already-valid cases pass through unchanged
# ──────────────────────────────────────────────────────────────────────────────

def test_valid_case_is_unchanged():
    assert validate_case(FULL_CASE) == FULL_CASE


def test_extra_fields_pass_through():
    out = validate_case({**FULL_CASE, "page": "LoginPage", "notes": "keep me"})
    assert out["page"] == "LoginPage"
    assert out["notes"] == "keep me"


def test_input_dict_is_not_mutated():
    case = {"title": "x", "steps": ["press enter"]}
    validate_case(case)
    assert case == {"title": "x", "steps": ["press enter"]}


# ──────────────────────────────────────────────────────────────────────────────
# Defaults for missing fields
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_case_gets_all_defaults():
    out = validate_case({})
    assert out == {
        "id": "",
        "requirement_id": "",
        "title": "",
        "type": "functional",
        "target": "manual",
        "priority": "P2",
        "preconditions": [],
        "steps": [],
        "expected": "",
        "automatable": True,
    }


def test_missing_automatable_defaults_true():
    assert validate_case({})["automatable"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Coercions
# ──────────────────────────────────────────────────────────────────────────────

def test_string_step_becomes_action_dict():
    out = validate_case({"steps": ["Click login", {"action": "Wait"}]})
    assert out["steps"] == [{"action": "Click login", "data": None},
                            {"action": "Wait", "data": None}]


def test_step_data_is_stringified_but_none_kept():
    out = validate_case({"steps": [{"action": "POST /login", "data": 42},
                                   {"action": "Submit", "data": None}]})
    assert out["steps"] == [{"action": "POST /login", "data": "42"},
                            {"action": "Submit", "data": None}]


def test_single_bare_step_is_wrapped_in_list():
    assert validate_case({"steps": "Press enter"})["steps"] == \
        [{"action": "Press enter", "data": None}]


def test_preconditions_string_becomes_list():
    assert validate_case({"preconditions": "User exists"})["preconditions"] == \
        ["User exists"]


def test_preconditions_items_stringified():
    assert validate_case({"preconditions": [1, "two"]})["preconditions"] == \
        ["1", "two"]


def test_enums_matched_case_insensitively():
    out = validate_case({"type": "SECURITY", "target": "API", "priority": "p0"})
    assert out["type"] == "security"
    assert out["target"] == "api"
    assert out["priority"] == "P0"


def test_unknown_enums_fall_back_to_safe_defaults():
    out = validate_case({"type": "smoke", "target": "browser", "priority": "high"})
    assert out["type"] == "functional"
    assert out["target"] == "manual"
    assert out["priority"] == "P2"


def test_automatable_string_coercions():
    assert validate_case({"automatable": "false"})["automatable"] is False
    assert validate_case({"automatable": "No"})["automatable"] is False
    assert validate_case({"automatable": "true"})["automatable"] is True
    assert validate_case({"automatable": 0})["automatable"] is False


def test_numeric_id_and_title_stringified():
    out = validate_case({"id": 7, "title": 123, "expected": 0})
    assert out["id"] == "7"
    assert out["title"] == "123"
    assert out["expected"] == "0"


def test_non_dict_case_raises():
    with pytest.raises(TypeError, match="Expected a case dict"):
        validate_case("not a case")


# ──────────────────────────────────────────────────────────────────────────────
# validate_cases — batch helper
# ──────────────────────────────────────────────────────────────────────────────

def test_validate_cases_drops_non_dict_entries():
    out = validate_cases([FULL_CASE, "stray string", None, {"title": "ok"}])
    assert len(out) == 2
    assert out[0] == FULL_CASE
    assert out[1]["title"] == "ok"


def test_validate_cases_handles_none_and_empty():
    assert validate_cases(None) == []
    assert validate_cases([]) == []
