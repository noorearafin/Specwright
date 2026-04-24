"""Config loader. Accepts YAML or JSON, falls back to sane defaults."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "llm": {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        # api_key read from env (GEMINI_API_KEY / GROQ_API_KEY / ANTHROPIC_API_KEY)
    },
    "exports": ["csv", "excel", "jira", "testrail", "html", "markdown"],
}


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"⚠ Config file {path} not found; using defaults.")
        return DEFAULT_CONFIG

    text = p.read_text()
    if p.suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            raise SystemExit("YAML config needs pyyaml: pip install pyyaml")
        cfg = yaml.safe_load(text)
    else:
        cfg = json.loads(text)

    # Merge with defaults
    merged = {**DEFAULT_CONFIG, **cfg}
    merged["llm"] = {**DEFAULT_CONFIG["llm"], **cfg.get("llm", {})}

    # Allow ${ENV_VAR} substitution in api_key
    api_key = merged["llm"].get("api_key", "")
    if isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
        env_name = api_key[2:-1]
        merged["llm"]["api_key"] = os.environ.get(env_name, "")

    return merged
