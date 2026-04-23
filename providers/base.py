"""Provider interface. All providers implement a single `complete()` method.

The interface is deliberately tiny: system prompt + user message → text response.
Stage 2 uses a helper `complete_json()` which parses the response.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base — every provider just implements complete()."""

    name: str = "base"

    # Maximum output tokens this provider/model will reliably produce in a
    # single call. Subclasses override this. Stage 2 uses it to decide whether
    # to chunk generation per-requirement.
    max_output_tokens: int = 8000

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.2) -> str:
        """Return the LLM's text response to (system, user) message pair."""

    def complete_json(self, system: str, user: str, max_tokens: int = 16000,
                      temperature: float = 0.1):
        """Call complete() and parse JSON. Strips markdown fences if present."""
        # Clamp to the provider's real capacity so we never ask for more than
        # it can return (silent truncation → JSON parse errors).
        safe_max = min(max_tokens, self.max_output_tokens)
        raw = self.complete(system, user, max_tokens=safe_max, temperature=temperature)
        return _parse_json(raw)


def _parse_json(raw: str):
    """Extract JSON from LLM output — handles ```json fences and stray prose."""
    raw = raw.strip()

    # Strip markdown fences
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: find first [ or { and last matching bracket
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = raw.find(open_ch)
        end = raw.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not parse JSON from LLM response:\n{raw[:500]}...")