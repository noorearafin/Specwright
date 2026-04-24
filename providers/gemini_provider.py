"""Google Gemini provider. Uses the new google-genai SDK.

Install: pip install google-genai
Get key: https://aistudio.google.com/apikey
Free tier: generous rate limits on gemini-2.5-flash.
"""

from __future__ import annotations

import os
import time

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    name = "gemini"
    max_output_tokens = 8000  # Gemini 2.5 Flash/Pro single-call output ceiling

    def __init__(self, model: str = "gemini-2.5-flash",
                 api_key: str | None = None, temperature: float = 0.2):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise SystemExit(
                "google-genai not installed. Run: pip install google-genai"
            )

        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit(
                "No Gemini API key. Set GEMINI_API_KEY env var or api_key in config.\n"
                "Get a key: https://aistudio.google.com/apikey"
            )

        self._client = genai.Client(api_key=key)
        self._types = types
        self.model = model
        self.default_temperature = temperature

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float | None = None) -> str:
        cfg = self._types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature if temperature is not None else self.default_temperature,
        )

        # Retry on rate limits (free tier: 15 req/min)
        last_err = None
        for attempt in range(4):
            try:
                resp = self._client.models.generate_content(
                    model=self.model, contents=user, config=cfg,
                )
                return resp.text or ""
            except Exception as e:  # noqa: BLE001
                msg = str(e).lower()
                if "rate" in msg or "quota" in msg or "429" in msg:
                    wait = 15 * (attempt + 1)
                    print(f"  ⏳ rate-limited, sleeping {wait}s...")
                    time.sleep(wait)
                    last_err = e
                    continue
                raise
        raise RuntimeError(f"Gemini failed after retries: {last_err}")