"""Tests for the Stage-3 code hygiene + verify gate (stages.py, verify.py).

Everything runs offline: _clean_code is pure string handling and the tsc
output parser is fed canned compiler output.
"""

from __future__ import annotations

from stages import _clean_code
from verify import parse_tsc_output


# ──────────────────────────────────────────────────────────────────────────────
# _clean_code — fence/prose stripping variants
# ──────────────────────────────────────────────────────────────────────────────

CODE = "import { test } from '@playwright/test';\n\ntest('x', () => {});"


def test_clean_code_passthrough():
    assert _clean_code(CODE) == CODE + "\n"


def test_clean_code_ts_fence():
    assert _clean_code(f"```ts\n{CODE}\n```") == CODE + "\n"


def test_clean_code_typescript_fence():
    assert _clean_code(f"```typescript\n{CODE}\n```") == CODE + "\n"


def test_clean_code_bare_fence():
    assert _clean_code(f"```\n{CODE}\n```") == CODE + "\n"


def test_clean_code_leading_fence_only():
    # Truncated output: opening fence but no closing one
    assert _clean_code(f"```ts\n{CODE}") == CODE + "\n"


def test_clean_code_trailing_fence_only():
    assert _clean_code(f"{CODE}\n```") == CODE + "\n"


def test_clean_code_prose_around_fence():
    raw = f"Here is the spec file:\n\n```typescript\n{CODE}\n```\n\nLet me know!"
    assert _clean_code(raw) == CODE + "\n"


def test_clean_code_prose_before_import_without_fence():
    raw = f"Sure, here's the code:\n\n{CODE}"
    assert _clean_code(raw) == CODE + "\n"


def test_clean_code_keeps_leading_comment():
    commented = f"// POM for login\n{CODE}"
    assert _clean_code(commented) == commented + "\n"


def test_clean_code_ignores_fence_after_code_started():
    # A fence-looking line INSIDE the code must not trigger stripping
    tricky = CODE + "\n// ```\nconst x = 1;"
    assert _clean_code(tricky) == tricky + "\n"


# ──────────────────────────────────────────────────────────────────────────────
# parse_tsc_output — both tsc formats, grouping per file
# ──────────────────────────────────────────────────────────────────────────────

CLASSIC = """\
tests/specs/req-1.spec.ts(2,10): error TS2305: Module '"../pages/LoginPage"' has no exported member 'LoginPage'.
tests/specs/req-1.spec.ts(14,5): error TS2339: Property 'loginAs' does not exist on type 'LoginPage'.
tests/api/req-2.spec.ts(1,24): error TS2307: Cannot find module '@playwright/test' or its corresponding type declarations.
"""

PRETTY = """\
tests/specs/req-1.spec.ts:2:10 - error TS2305: Module '"../pages/LoginPage"' has no exported member 'LoginPage'.

2 import { LoginPage } from '../pages/LoginPage';
           ~~~~~~~~~

Found 1 error in tests/specs/req-1.spec.ts:2
"""


def test_parse_classic_format_groups_by_file():
    errors = parse_tsc_output(CLASSIC)
    assert set(errors) == {"tests/specs/req-1.spec.ts", "tests/api/req-2.spec.ts"}
    assert len(errors["tests/specs/req-1.spec.ts"]) == 2
    assert errors["tests/api/req-2.spec.ts"] == [
        "(1,24): error TS2307: Cannot find module '@playwright/test' "
        "or its corresponding type declarations."
    ]


def test_parse_pretty_format_ignores_context_lines():
    errors = parse_tsc_output(PRETTY)
    assert set(errors) == {"tests/specs/req-1.spec.ts"}
    assert errors["tests/specs/req-1.spec.ts"] == [
        "(2,10): error TS2305: Module '\"../pages/LoginPage\"' "
        "has no exported member 'LoginPage'."
    ]


def test_parse_clean_output_yields_no_errors():
    assert parse_tsc_output("") == {}
    assert parse_tsc_output("Found 0 errors.\n") == {}
