"""Provider interface. All providers implement a single `complete()` method.

The interface is deliberately tiny: system prompt + user message → text response.
Stage 2 uses a helper `complete_json()` which parses the response.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class — every LLM provider just implements complete().

    The interface is intentionally minimal: system prompt + user message → text.
    All pipeline stages call complete() or complete_json(); they never talk to a
    specific provider SDK directly. Swapping providers requires only changing the
    config — no stage code changes.
    """

    name: str = "base"

    # Maximum output tokens this provider/model will reliably produce in a
    # single call. Subclasses override this. Stage 2 uses it to decide whether
    # to chunk generation per-requirement (avoid silent truncation → broken JSON).
    max_output_tokens: int = 8000

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float = 0.2) -> str:
        """Return the LLM's text response to a (system, user) message pair."""

    def complete_json(self, system: str, user: str, max_tokens: int = 16000,
                      temperature: float = 0.1):
        """Call complete() and parse the response as JSON.

        Uses a lower temperature (0.1) by default — JSON generation benefits from
        more deterministic output than prose writing (0.2).

        Clamps max_tokens to the provider's real ceiling so we never request more
        than the model can return; silent truncation would break JSON parsing.
        """
        safe_max = min(max_tokens, self.max_output_tokens)
        raw = self.complete(system, user, max_tokens=safe_max, temperature=temperature)
        return _parse_json(raw)


def _parse_json(raw: str):
    """Extract JSON from LLM output — handles ```json fences and stray prose.

    Three-step strategy:
      1. Strip ```json ... ``` fences if present.
      2. Try json.loads on the clean string.
      3. Fall back to bracket-scanning — find the first [ or { and last ] or }
         and try parsing just that slice. Handles models that add an explanation
         sentence before or after the JSON object.
    """
    raw = raw.strip()

    # Step 1: strip markdown code fences that some models add despite instructions
    fence = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()

    # Step 2: direct parse — the happy path for well-behaved models
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Step 3: bracket scan — rescue partial JSON when the model adds stray text
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = raw.find(open_ch)
        end = raw.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not parse JSON from LLM response:\n{raw[:500]}...")