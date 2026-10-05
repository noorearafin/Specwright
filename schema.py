"""Case schema validation for Stage 2 output.

Enforces the case shape documented in prompts.CASE_WRITER_SYSTEM:

    id, requirement_id, title, type, target, priority,
    preconditions (list), steps (list of {"action", "data"}),
    expected, automatable (bool)

LLMs occasionally drop fields or emit near-misses (a bare string step, a
"true"/"false" string for automatable). Rather than crash downstream —
scope gate, exporters, Stage 3 — validate_case() coerces what it can and
fills safe defaults for the rest. Extra fields (e.g. "page") pass through
untouched.
"""

from __future__ import annotations

# Allowed enum values from prompts.CASE_WRITER_SYSTEM. Unknown values fall
# back to the safest member instead of raising.
CASE_TYPES = {"functional", "negative", "boundary", "security",
              "accessibility", "performance", "contract"}
CASE_TARGETS = {"ui", "api", "manual"}
CASE_PRIORITIES = {"P0", "P1", "P2"}


def validate_case(case: dict) -> dict:
    """Return a schema-complete copy of ``case``.

    Coercions / defaults:
    - missing string fields → "" (id/requirement_id/title/expected)
    - type/target/priority matched case-insensitively against the allowed
      values; unknown → "functional" / "manual" / "P2"
    - preconditions: missing → [], bare string → [string], items stringified
    - steps: missing → [], bare string step → {"action": s, "data": None},
      dict steps get both keys filled
    - automatable: missing → True, "false"/"no"/"0" strings → False
    """
    if not isinstance(case, dict):
        raise TypeError(f"Expected a case dict, got {type(case).__name__}")

    out = dict(case)
    out["id"] = _text(case.get("id"))
    out["requirement_id"] = _text(case.get("requirement_id"))
    out["title"] = _text(case.get("title"))
    out["type"] = _enum(case.get("type"), CASE_TYPES, "functional")
    out["target"] = _enum(case.get("target"), CASE_TARGETS, "manual")
    out["priority"] = _enum(case.get("priority"), CASE_PRIORITIES, "P2")
    out["preconditions"] = _str_list(case.get("preconditions"))
    out["steps"] = [_step(s) for s in _as_list(case.get("steps"))]
    out["expected"] = _text(case.get("expected"))
    out["automatable"] = _bool(case.get("automatable"), default=True)
    return out


def validate_cases(cases) -> list[dict]:
    """Validate a whole batch. Non-dict entries (stray LLM output) are dropped."""
    return [validate_case(c) for c in cases or [] if isinstance(c, dict)]


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _enum(value, allowed: set[str], default: str) -> str:
    """Match ``value`` against ``allowed`` ignoring case; unknown → default."""
    if isinstance(value, str):
        needle = value.strip().lower()
        for member in allowed:
            if needle == member.lower():
                return member
    return default


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]  # a single bare item (e.g. one string step)


def _str_list(value) -> list[str]:
    return [p if isinstance(p, str) else str(p) for p in _as_list(value)]


def _step(step) -> dict:
    """Normalize one step to {"action": str, "data": str|None}."""
    if isinstance(step, dict):
        data = step.get("data")
        return {
            "action": _text(step.get("action")),
            "data": None if data is None else str(data),
        }
    return {"action": _text(step), "data": None}


def _bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "no", "0", ""}
    return bool(value)
