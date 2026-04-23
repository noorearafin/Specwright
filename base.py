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

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.2) -> str:
        """Return the LLM's text response to (system, user) message pair."""

    def complete_json(self, system: str, user: str, max_tokens: int = 16000,
                      temperature: float = 0.1):
        """Call complete() and parse JSON. Strips markdown fences if present."""
        raw = self.complete(system, user, max_tokens=max_tokens, temperature=temperature)
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
