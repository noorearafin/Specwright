"""Scope gate: presets, rich filtering, saved scopes, and coverage reporting.

Runs between Stage 2 and Stage 3 to let the user pick exactly which cases
to automate. Supports:

- Preset modes (smoke / regression / security / accessibility / api / ui / everything)
- Include filters: priorities, types, targets, requirements, ids
- Exclude filters: exclude_priorities, exclude_types, exclude_targets,
  exclude_requirements, exclude_ids
- Keyword search (``grep``) over title / steps / expected — regex or literal
- ``limit`` cap that keeps the highest-priority cases first
- ``include_manual`` to pull in non-automatable cases (for export-only runs)
- Named custom scopes persisted to ``scopes.yaml`` for team reuse
- Requirement coverage report so a filter can't silently drop a requirement
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path


PRESETS = {
    "smoke": {
        "description": "P0 happy paths only (fastest, for CI gate)",
        "priorities": ["P0"],
        "types": ["functional"],
    },
    "regression": {
        "description": "P0 + P1, all functional/negative/boundary (nightly)",
        "priorities": ["P0", "P1"],
        "types": ["functional", "negative", "boundary", "contract"],
    },
    "security": {
        "description": "Security cases only (run before release)",
        "types": ["security"],
    },
    "accessibility": {
        "description": "Accessibility-only run (before UX review)",
        "types": ["accessibility"],
    },
    "api": {
        "description": "API-target cases only (no browser needed)",
        "targets": ["api"],
    },
    "ui": {
        "description": "UI-target cases only (browser flows)",
        "targets": ["ui"],
    },
    "everything": {
        "description": "All automatable cases (full suite)",
    },
}

# Keys apply_scope understands; anything else triggers a validation warning.
_INCLUDE_KEYS = {"priorities", "types", "targets", "requirements", "ids"}
_EXCLUDE_KEYS = {"exclude_" + k for k in _INCLUDE_KEYS}
_OTHER_KEYS = {"grep", "limit", "include_manual", "description"}
KNOWN_KEYS = _INCLUDE_KEYS | _EXCLUDE_KEYS | _OTHER_KEYS

_FIELD_FOR = {
    "priorities": "priority",
    "types": "type",
    "targets": "target",
    "requirements": "requirement_id",
    "ids": "id",
}

SCOPES_FILE = "scopes.yaml"


# ──────────────────────────────────────────────────────────────────────────────
# Core filtering
# ──────────────────────────────────────────────────────────────────────────────

def apply_scope(cases: list[dict], scope: dict) -> list[dict]:
    """Filter cases by scope dict.

    Drops non-automatable cases unless ``include_manual`` is true. Include
    filters narrow the set, exclude filters remove from it, ``grep`` keyword-
    matches title/steps/expected, and ``limit`` caps the result keeping the
    highest-priority cases first.
    """
    scope = scope or {}

    if scope.get("include_manual"):
        out = list(cases)
    else:
        out = [c for c in cases if c.get("automatable", True)]

    for key, field in _FIELD_FOR.items():
        if scope.get(key):
            allowed = set(scope[key])
            out = [c for c in out if c.get(field) in allowed]
        if scope.get("exclude_" + key):
            blocked = set(scope["exclude_" + key])
            out = [c for c in out if c.get(field) not in blocked]

    if scope.get("grep"):
        rx = _compile_grep(scope["grep"])
        out = [c for c in out if rx.search(_searchable_text(c))]

    limit = scope.get("limit")
    if limit and limit > 0 and len(out) > limit:
        out = sorted(out, key=_priority_rank)[:limit]
        out.sort(key=lambda c: c.get("id", ""))  # restore stable ID order

    return out


def _compile_grep(pattern: str) -> re.Pattern:
    """Compile grep as case-insensitive regex; fall back to literal match."""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def _searchable_text(case: dict) -> str:
    parts = [
        case.get("id", ""),
        case.get("requirement_id", ""),
        case.get("title", ""),
        case.get("expected", ""),
        " ".join(case.get("steps") or []),
        " ".join(case.get("preconditions") or []),
    ]
    return " ".join(str(p) for p in parts)


def _priority_rank(case: dict) -> tuple:
    # P0 < P1 < P2 sorts naturally; unknown priorities go last.
    prio = case.get("priority") or "P9"
    return (prio, case.get("id", ""))


# ──────────────────────────────────────────────────────────────────────────────
# Validation, description, coverage
# ──────────────────────────────────────────────────────────────────────────────

def validate_scope(cases: list[dict], scope: dict) -> list[str]:
    """Return human-readable warnings: typo'd keys, filter values that match
    nothing, or a filter combination that selects zero cases."""
    warnings = []
    scope = scope or {}

    for key in scope:
        if key not in KNOWN_KEYS:
            warnings.append(f"Unknown scope key '{key}' (ignored). "
                            f"Valid keys: {sorted(KNOWN_KEYS - {'description'})}")

    for key, field in _FIELD_FOR.items():
        present = {c.get(field) for c in cases}
        for k in (key, "exclude_" + key):
            for value in scope.get(k) or []:
                if value not in present:
                    warnings.append(
                        f"'{value}' in scope['{k}'] matches no case "
                        f"(known {field} values: {sorted(v for v in present if v)})")

    if not apply_scope(cases, scope):
        warnings.append("This scope selects ZERO cases — nothing would be automated.")

    return warnings


def describe_scope(scope: dict) -> str:
    """One-line human-readable summary of a scope dict."""
    scope = scope or {}
    bits = []
    for key in sorted(_INCLUDE_KEYS):
        if scope.get(key):
            bits.append(f"{key}={'/'.join(scope[key])}")
    for key in sorted(_EXCLUDE_KEYS):
        if scope.get(key):
            bits.append(f"NOT {key[8:]}={'/'.join(scope[key])}")
    if scope.get("grep"):
        bits.append(f"grep~'{scope['grep']}'")
    if scope.get("limit"):
        bits.append(f"limit={scope['limit']}")
    if scope.get("include_manual"):
        bits.append("incl. manual cases")
    return ", ".join(bits) if bits else "everything automatable"


def coverage_report(all_cases: list[dict], selected: list[dict]) -> dict:
    """Per-requirement coverage of the selection vs the full case set.

    Returns ``{"covered": {req: n_selected}, "uncovered": [req, ...],
    "total_requirements": n}`` so callers can warn when a filter silently
    drops every case for some requirement.
    """
    all_reqs = sorted({c.get("requirement_id") for c in all_cases if c.get("requirement_id")})
    sel_counts = Counter(c.get("requirement_id") for c in selected)
    covered = {r: sel_counts[r] for r in all_reqs if sel_counts[r] > 0}
    uncovered = [r for r in all_reqs if sel_counts[r] == 0]
    return {
        "covered": covered,
        "uncovered": uncovered,
        "total_requirements": len(all_reqs),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Saved scopes (scopes.yaml)
# ──────────────────────────────────────────────────────────────────────────────

def load_saved_scopes(path: str | Path = SCOPES_FILE) -> dict:
    """Load named custom scopes from a YAML file. Missing file → {}."""
    p = Path(path)
    if not p.exists():
        return {}
    import yaml
    data = yaml.safe_load(p.read_text()) or {}
    return {name: scope for name, scope in data.items() if isinstance(scope, dict)}


def save_scope(name: str, scope: dict, path: str | Path = SCOPES_FILE) -> Path:
    """Persist a named scope to the YAML file (merging with existing ones)."""
    import yaml
    p = Path(path)
    existing = load_saved_scopes(p)
    existing[name] = {k: v for k, v in scope.items() if v and k in KNOWN_KEYS}
    p.write_text(yaml.safe_dump(existing, sort_keys=False, allow_unicode=True))
    return p


def resolve_scope(name: str, scopes_path: str | Path = SCOPES_FILE) -> dict:
    """Resolve a scope name → dict. Checks built-in presets first, then
    scopes.yaml. Raises KeyError with the available names if not found."""
    if name in PRESETS:
        return {k: v for k, v in PRESETS[name].items() if k != "description"}
    saved = load_saved_scopes(scopes_path)
    if name in saved:
        return saved[name]
    available = list(PRESETS) + list(saved)
    raise KeyError(f"Unknown scope '{name}'. Available: {available}")


# ──────────────────────────────────────────────────────────────────────────────
# Interactive CLI gate
# ──────────────────────────────────────────────────────────────────────────────

def prompt_scope(cases: list[dict]) -> dict:
    """Interactive CLI to pick which cases to automate."""
    automatable = [c for c in cases if c.get("automatable", True)]

    types = Counter(c.get("type", "?") for c in automatable)
    prios = Counter(c.get("priority", "?") for c in automatable)
    tgts = Counter(c.get("target", "?") for c in automatable)
    reqs = Counter(c.get("requirement_id", "?") for c in automatable)

    print("=" * 60)
    print("📋 Scope Selection")
    print("=" * 60)
    print(f"Automatable cases: {len(automatable)} of {len(cases)} total")
    print(f"  By type:        {dict(types)}")
    print(f"  By priority:    {dict(prios)}")
    print(f"  By target:      {dict(tgts)}")
    print(f"  By requirement: {dict(reqs)}")
    print()

    saved = load_saved_scopes()
    keys = list(PRESETS.keys())
    saved_keys = list(saved.keys())

    print("Presets:")
    for i, k in enumerate(keys, 1):
        print(f"  {i}) {k:<15} — {PRESETS[k]['description']}")
    for j, k in enumerate(saved_keys, len(keys) + 1):
        print(f"  {j}) {k:<15} — saved scope ({describe_scope(saved[k])})")
    custom_n = len(keys) + len(saved_keys) + 1
    print(f"  {custom_n}) custom         — choose filters manually")
    print()

    while True:
        choice = input(f"Choose [1-{custom_n}] (default: 2): ").strip() or "2"
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(keys):
                scope = dict(PRESETS[keys[n - 1]])
                scope.pop("description", None)
                break
            if len(keys) < n <= len(keys) + len(saved_keys):
                scope = dict(saved[saved_keys[n - len(keys) - 1]])
                break
            if n == custom_n:
                scope = _prompt_custom(types, prios, tgts, reqs)
                break
        print("  ⚠ invalid choice")

    for w in validate_scope(cases, scope):
        print(f"  ⚠ {w}")

    # Preview + coverage
    selected = apply_scope(cases, scope)
    cov = coverage_report(cases, selected)
    print(f"\n→ Scope: {describe_scope(scope)}")
    print(f"→ {len(selected)} cases matched the filter "
          f"({len(cov['covered'])}/{cov['total_requirements']} requirements covered).")
    if cov["uncovered"]:
        print(f"  ⚠ No cases selected for: {', '.join(cov['uncovered'])}")

    if input("Proceed? [Y/n]: ").strip().lower() not in ("", "y", "yes"):
        print("Cancelled.")
        raise SystemExit(0)

    name = input("Save this scope for reuse? Enter a name (blank = skip): ").strip()
    if name:
        path = save_scope(name, scope)
        print(f"  ✓ saved as '{name}' in {path}")

    return scope


def _prompt_custom(types, prios, tgts, reqs) -> dict:
    def pick(label, options):
        picked = input(
            f"{label} (space-separated from {list(options)}; blank = all): "
        ).strip().split()
        return picked or None

    scope = {
        "priorities": pick("Priorities", prios),
        "types": pick("Types", types),
        "targets": pick("Targets", tgts),
        "requirements": pick("Requirements", reqs),
    }
    scope["exclude_types"] = pick("EXCLUDE types", types)
    grep = input("Keyword filter (regex over title/steps/expected; blank = none): ").strip()
    if grep:
        scope["grep"] = grep
    limit = input("Max cases (blank = no cap): ").strip()
    if limit.isdigit():
        scope["limit"] = int(limit)
    return scope
