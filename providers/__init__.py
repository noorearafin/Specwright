"""Provider factory. Lazy imports — only the chosen provider's SDK is loaded.

Call get_provider(cfg) with the 'llm' section of your config dict to get back
a ready-to-use LLMProvider instance. Provider SDKs are imported inside each
branch so unused providers don't slow down startup or require installation.
"""

from __future__ import annotations

from .base import LLMProvider


def get_provider(cfg: dict) -> LLMProvider:
    """Instantiate and return the LLM provider specified in the config.

    cfg must have at least a 'provider' key. Optional keys: model, api_key,
    temperature, base_url (Ollama only). Falls back to sensible defaults for
    model and temperature when omitted.
    """
    name = cfg.get("provider", "gemini").lower()

    # Each branch imports its SDK lazily — if you never use Anthropic, the
    # 'anthropic' package doesn't need to be installed at all.

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
