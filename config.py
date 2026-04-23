"""Config loader. Accepts YAML or JSON, falls back to sane defaults."""

from __future__ import annotations

import json
import os
from pathlib import Path

# These defaults kick in whenever a config file is missing or incomplete.
# The user can override any key by supplying a config.yaml / config.json.
DEFAULT_CONFIG = {
    "llm": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        # api_key read from env (GEMINI_API_KEY / GROQ_API_KEY / ANTHROPIC_API_KEY)
    },
    # All six export formats are enabled by default; remove any you don't need.
    "exports": ["csv", "excel", "jira", "testrail", "html", "markdown"],
}


def load_config(path: str) -> dict:
    """Load a YAML or JSON config file and merge it with defaults.

    Returns the merged config dict. Missing keys fall back to DEFAULT_CONFIG.
    Supports ${ENV_VAR} placeholders in the api_key field so secrets stay out
    of version control (e.g., api_key: ${GROQ_API_KEY} in config.yaml).
    """
    p = Path(path)

    # If no config file exists, run with built-in defaults — zero friction for new users.
    if not p.exists():
        print(f"⚠ Config file {path} not found; using defaults.")
        return DEFAULT_CONFIG

    text = p.read_text()

    # Choose parser based on file extension
    if p.suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            raise SystemExit("YAML config needs pyyaml: pip install pyyaml")
        cfg = yaml.safe_load(text)
    else:
        cfg = json.loads(text)

    # Shallow-merge top-level keys, then deep-merge the nested 'llm' block
    # so that specifying only 'provider' doesn't wipe out the default 'model'.
    merged = {**DEFAULT_CONFIG, **cfg}
    merged["llm"] = {**DEFAULT_CONFIG["llm"], **cfg.get("llm", {})}

    # Resolve ${ENV_VAR} placeholders in api_key — lets users commit config
    # without embedding secrets, e.g.: api_key: ${GROQ_API_KEY}
    api_key = merged["llm"].get("api_key", "")
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        env_name = api_key[2:-1]
        merged["llm"]["api_key"] = os.environ.get(env_name, "")

    return merged
