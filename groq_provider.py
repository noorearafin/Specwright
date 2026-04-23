"""Groq provider. Fast inference on open models — Llama, Qwen, DeepSeek.

Install: pip install groq
Get key: https://console.groq.com/keys
Free tier: generous rate limits, no credit card needed.
"""

from __future__ import annotations

import os
import time

from .base import LLMProvider


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, model: str = "llama-3.3-70b-versatile",
                 api_key: str | None = None, temperature: float = 0.2):
        try:
            from groq import Groq
        except ImportError:
            raise SystemExit("groq not installed. Run: pip install groq")

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise SystemExit(
                "No Groq API key. Set GROQ_API_KEY env var or api_key in config.\n"
                "Get a key: https://console.groq.com/keys"
            )

        self._client = Groq(api_key=key)
        self.model = model
        self.default_temperature = temperature

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float | None = None) -> str:
        last_err = None
        for attempt in range(4):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature if temperature is not None else self.default_temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001
                msg = str(e).lower()
                if "rate" in msg or "429" in msg:
                    wait = 10 * (attempt + 1)
                    print(f"  ⏳ rate-limited, sleeping {wait}s...")
                    time.sleep(wait)
                    last_err = e
                    continue
                raise
        raise RuntimeError(f"Groq failed after retries: {last_err}")
