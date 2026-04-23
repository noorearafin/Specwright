"""Anthropic Claude provider. Paid, highest quality.

Install: pip install anthropic
"""

from __future__ import annotations

import os

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    max_output_tokens = 32000  # Claude Sonnet/Opus 4.x support very large outputs

    def __init__(self, model: str = "claude-sonnet-4-6",
                 api_key: str | None = None, temperature: float = 0.2):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise SystemExit("anthropic not installed. Run: pip install anthropic")

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("No Anthropic API key. Set ANTHROPIC_API_KEY env var.")

        self._client = Anthropic(api_key=key)
        self.model = model
        self.default_temperature = temperature

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float | None = None) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature if temperature is not None else self.default_temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")