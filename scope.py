"""Scope gate: interactive prompt + filter function.

Runs between Stage 2 and Stage 3 to let the user pick exactly which cases
to automate. Supports preset modes and full custom filtering.
"""

from __future__ import annotations

from collections import Counter


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
    "everything": {
        "description": "All automatable cases (full suite)",
    },
}


def prompt_scope(cases: list[dict]) -> dict:
    """Interactive CLI to pick which cases to automate."""
    automatable = [c for c in cases if c.get("automatable", True)]

    types = Counter(c.get("type", "?") for c in automatable)
    prios = Counter(c.get("priority", "?") for c in automatable)
    tgts = Counter(c.get("target", "?") for c in automatable)

    print("=" * 60)
    print("📋 Scope Selection")
    print("=" * 60)
    print(f"Automatable cases: {len(automatable)} of {len(cases)} total")
    print(f"  By type:     {dict(types)}")
    print(f"  By priority: {dict(prios)}")
    print(f"  By target:   {dict(tgts)}")
    print()

    print("Presets:")
    keys = list(PRESETS.keys())
    for i, k in enumerate(keys, 1):
        print(f"  {i}) {k:<15} — {PRESETS[k]['description']}")
    print(f"  {len(keys) + 1}) custom         — choose filters manually")
    print()

    while True:
        choice = input(f"Choose [1-{len(keys) + 1}] (default: 2): ").strip() or "2"
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(keys):
                scope = dict(PRESETS[keys[n - 1]])
                scope.pop("description", None)
                break
            if n == len(keys) + 1:
                scope = _prompt_custom(types, prios, tgts)
                break
        print("  ⚠ invalid choice")

    # Preview
    selected = apply_scope(cases, scope)
    print(f"\n→ {len(selected)} cases matched the filter.")
    if input("Proceed? [Y/n]: ").strip().lower() in ("", "y", "yes"):
        return scope
    print("Cancelled.")
    raise SystemExit(0)


def _prompt_custom(types, prios, tgts) -> dict:
    def pick(label, options):
        picked = input(
            f"{label} (space-separated from {list(options)}; blank = all): "
        ).strip().split()
        return picked or None

    return {
        "priorities": pick("Priorities", prios),
        "types": pick("Types", types),
        "targets": pick("Targets", tgts),
    }


def apply_scope(cases: list[dict], scope: dict) -> list[dict]:
    """Filter cases by scope dict. Always drops non-automatable cases."""
    out = [c for c in cases if c.get("automatable", True)]

    if scope.get("priorities"):
        s = set(scope["priorities"])
        out = [c for c in out if c.get("priority") in s]

    if scope.get("types"):
        s = set(scope["types"])
        out = [c for c in out if c.get("type") in s]

    if scope.get("targets"):
        s = set(scope["targets"])
        out = [c for c in out if c.get("target") in s]

    return out
