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
        """Send a (system, user) prompt pair to Gemini and return the text response.

        Retries up to 4 times on rate-limit errors with exponential back-off
        (15s, 30s, 45s, 60s). The free tier allows ~15 requests/min, so Stage 2's
        1-second inter-chunk sleep is usually enough, but burst calls can still
        hit the limit.
        """
        cfg = self._types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature if temperature is not None else self.default_temperature,
        )

        # Retry on rate limits — Gemini free tier: 15 req/min
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
                    # Increase wait time with each retry to give the quota time to reset
                    wait = 15 * (attempt + 1)
                    print(f"  ⏳ rate-limited, sleeping {wait}s...")
                    time.sleep(wait)
                    last_err = e
                    continue
                raise  # non-rate-limit errors bubble up immediately
        raise RuntimeError(f"Gemini failed after retries: {last_err}")