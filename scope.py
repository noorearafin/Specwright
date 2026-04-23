"""Scope gate: interactive prompt + filter function.

Runs between Stage 2 and Stage 3 to let the user pick exactly which cases
to automate. Supports preset modes and full custom filtering.
"""

from __future__ import annotations

from collections import Counter


# Predefined scope presets — each maps to a set of priority/type/target filters.
# The Streamlit UI (app.py) exposes these as clickable buttons; the CLI
# (qa_agent.py) shows them as a numbered menu. Add new presets here and they
# appear in both interfaces automatically.
PRESETS = {
    # Fastest subset: only P0 functional cases. Ideal as a CI gate on every push.
    "smoke": {
        "description": "P0 happy paths only (fastest, for CI gate)",
        "priorities": ["P0"],
        "types": ["functional"],
    },
    # Broader net: P0 + P1, includes negative/boundary/contract cases.
    # Suitable for nightly runs or pre-merge checks on feature branches.
    "regression": {
        "description": "P0 + P1, all functional/negative/boundary (nightly)",
        "priorities": ["P0", "P1"],
        "types": ["functional", "negative", "boundary", "contract"],
    },
    # Security-only: use before a release or after auth/input-handling changes.
    "security": {
        "description": "Security cases only (run before release)",
        "types": ["security"],
    },
    # Accessibility-only: run before a UX review or WCAG audit.
    "accessibility": {
        "description": "Accessibility-only run (before UX review)",
        "types": ["accessibility"],
    },
    # No filter at all — every automatable case runs. Slowest but most complete.
    "everything": {
        "description": "All automatable cases (full suite)",
    },
}


def prompt_scope(cases: list[dict]) -> dict:
    """Interactive CLI to pick which cases to automate.

    Shows a summary of available automatable cases broken down by type,
    priority, and target, then lets the user pick a preset or custom filters.
    Returns a scope dict that apply_scope() uses to filter the case list.
    """
    # Only automatable cases are eligible — manual cases (e.g., real inbox checks)
    # can never be run by Playwright, so we exclude them up front.
    automatable = [c for c in cases if c.get("automatable", True)]

    # Count breakdowns so the user can see what each filter will cover
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

    # Keep asking until the user enters a valid number
    while True:
        choice = input(f"Choose [1-{len(keys) + 1}] (default: 2): ").strip() or "2"
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(keys):
                # Strip the human-readable 'description' key before returning —
                # apply_scope only understands priorities/types/targets.
                scope = dict(PRESETS[keys[n - 1]])
                scope.pop("description", None)
                break
            if n == len(keys) + 1:
                scope = _prompt_custom(types, prios, tgts)
                break
        print("  ⚠ invalid choice")

    # Show a preview count so the user can confirm before Stage 3 starts
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
    """Filter cases by scope dict. Always drops non-automatable cases.

    Each key in scope is optional. Omitting a key means "no filter on that
    dimension". An empty scope ({}) returns all automatable cases.
    """
    # Non-automatable cases (manual, CAPTCHAs, real-inbox checks) are always
    # excluded — Playwright cannot run them regardless of scope.
    out = [c for c in cases if c.get("automatable", True)]

    # Apply each dimension only when the scope explicitly specifies it
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
