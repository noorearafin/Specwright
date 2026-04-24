"""Ollama provider. Runs locally — zero cost, full privacy.

Install: pip install ollama
Setup:   https://ollama.com/download  →  then `ollama pull llama3.1:8b`
Good models for this use case:
  - llama3.1:8b           — balanced, 8GB RAM
  - qwen2.5-coder:7b      — great for Stage 3 code gen
  - deepseek-r1:7b        — strong reasoning
  - llama3.1:70b          — highest quality, needs 48GB+ RAM
"""

from __future__ import annotations

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"
    max_output_tokens = 8000  # conservative; depends on model context window

    def __init__(self, model: str = "llama3.1:8b",
                 base_url: str = "http://localhost:11434",
                 temperature: float = 0.2):
        try:
            from ollama import Client
        except ImportError:
            raise SystemExit("ollama not installed. Run: pip install ollama")

        self._client = Client(host=base_url)
        self.model = model
        self.default_temperature = temperature

        # Fail fast if the model isn't pulled
        try:
            self._client.show(model)
        except Exception:
            raise SystemExit(
                f"Model '{model}' not found in Ollama. Run:\n"
                f"  ollama pull {model}\n"
                f"Or is Ollama running? Start with: ollama serve"
            )

    def complete(self, system: str, user: str, max_tokens: int = 8000,
                 temperature: float | None = None) -> str:
        resp = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={
                "num_predict": max_tokens,
                "temperature": temperature if temperature is not None else self.default_temperature,
            },
        )
        return resp["message"]["content"]