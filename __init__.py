"""Provider factory. Lazy imports — only the chosen provider's SDK is loaded."""

from __future__ import annotations

from .base import LLMProvider


def get_provider(cfg: dict) -> LLMProvider:
    name = cfg.get("provider", "gemini").lower()

    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(
            model=cfg.get("model", "gemini-2.5-flash"),
            api_key=cfg.get("api_key") or None,
            temperature=cfg.get("temperature", 0.2),
        )

    if name == "groq":
        from .groq_provider import GroqProvider
        return GroqProvider(
            model=cfg.get("model", "llama-3.3-70b-versatile"),
            api_key=cfg.get("api_key") or None,
            temperature=cfg.get("temperature", 0.2),
        )

    if name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(
            model=cfg.get("model", "llama3.1:8b"),
            base_url=cfg.get("base_url", "http://localhost:11434"),
            temperature=cfg.get("temperature", 0.2),
        )

    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            model=cfg.get("model", "claude-sonnet-4-6"),
            api_key=cfg.get("api_key") or None,
            temperature=cfg.get("temperature", 0.2),
        )

    raise ValueError(
        f"Unknown provider: {name!r}. "
        f"Pick one of: gemini, groq, ollama, anthropic."
    )
