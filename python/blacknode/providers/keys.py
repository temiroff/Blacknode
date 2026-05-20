from __future__ import annotations

import json
import os
from pathlib import Path

_PROVIDER_TO_ENV = {
    "Anthropic": "ANTHROPIC_API_KEY",
    "OpenAI": "OPENAI_API_KEY",
    "NVIDIA NIM": "NVIDIA_API_KEY",
}

_ROOT = Path(__file__).resolve().parents[3]
_SHARED_KEYS_PATH = _ROOT / "editor-server" / "api_keys.json"


def shared_api_keys_path() -> Path:
    return _SHARED_KEYS_PATH


def load_shared_api_keys() -> dict[str, str]:
    if not _SHARED_KEYS_PATH.exists():
        return {}
    try:
        data = json.loads(_SHARED_KEYS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if v}


def api_key_for_provider(provider: str, env_var: str | None = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit

    env_name = env_var or _PROVIDER_TO_ENV.get(provider, "")
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value

    return load_shared_api_keys().get(provider, "")
