from __future__ import annotations
from .base import BaseProvider
from .keys import api_key_for_provider

_ANTHROPIC_PREFIXES = ("claude-",)
_OPENAI_PREFIXES    = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-", "text-", "ft:gpt-")
_OLLAMA_PREFIX      = "ollama:"
_LOCAL_PREFIX       = "local:"
_NIM_PREFIX         = "nim:"
_NIM_BASE_URL       = "https://integrate.api.nvidia.com/v1"


def resolve(
    model: str,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[BaseProvider, str]:
    """Return (provider_instance, clean_model_name).

    Auto-detection rules (when `provider` is None):
      claude-*              → Anthropic
      gpt-* / o1-* / o4-*  → OpenAI
      ollama:<name>         → Ollama  (localhost:11434)
      nim:<name>            → NVIDIA NIM  (integrate.api.nvidia.com)
      local:<name>          → OpenAI-compat at base_url (required)
      anything else         → OpenAI-compat
    """
    clean_model = model

    # ── Explicit provider name ────────────────────────────────────────────────
    if provider:
        p = provider.lower()
        if p == "anthropic":
            return _make_anthropic(api_key), clean_model
        if p in ("openai", "openai-compatible", "compat"):
            return _make_openai(api_key, base_url), clean_model
        if p == "ollama":
            clean_model = model.removeprefix("ollama:")
            return _make_ollama(), clean_model
        if p in ("nim", "nvidia"):
            clean_model = model.removeprefix("nim:")
            return _make_nim(api_key), clean_model
        raise ValueError(
            f"Unknown provider '{provider}'. "
            "Use 'anthropic', 'openai', 'ollama', or 'nim'."
        )

    # ── Auto-detect from model name ───────────────────────────────────────────
    if any(model.startswith(p) for p in _ANTHROPIC_PREFIXES):
        return _make_anthropic(api_key), clean_model

    if any(model.startswith(p) for p in _OPENAI_PREFIXES):
        return _make_openai(api_key, base_url), clean_model

    if model.startswith(_OLLAMA_PREFIX):
        clean_model = model.removeprefix(_OLLAMA_PREFIX)
        return _make_ollama(), clean_model

    if model.startswith(_NIM_PREFIX):
        clean_model = model.removeprefix(_NIM_PREFIX)
        return _make_nim(api_key), clean_model

    if model.startswith(_LOCAL_PREFIX):
        clean_model = model.removeprefix(_LOCAL_PREFIX)
        if not base_url:
            raise ValueError("local:* model requires base_url (e.g. 'http://localhost:1234/v1')")
        return _make_openai(api_key or "local", base_url), clean_model

    # fallback: OpenAI-compatible
    return _make_openai(api_key, base_url), clean_model


# ── Private helpers ───────────────────────────────────────────────────────────

def _make_anthropic(api_key):
    from .anthropic_provider import AnthropicProvider
    return AnthropicProvider(api_key_for_provider("Anthropic", "ANTHROPIC_API_KEY", api_key))

def _make_openai(api_key, base_url):
    from .openai_provider import OpenAIProvider
    return OpenAIProvider(api_key_for_provider("OpenAI", "OPENAI_API_KEY", api_key), base_url)

def _make_ollama():
    from .openai_provider import OpenAIProvider
    return OpenAIProvider(api_key="ollama", base_url="http://localhost:11434/v1")

def _make_nim(api_key):
    from .openai_provider import OpenAIProvider
    return OpenAIProvider(
        api_key=api_key_for_provider("NVIDIA NIM", "NVIDIA_API_KEY", api_key),
        base_url=_NIM_BASE_URL,
        single_tool_call=True,  # NIM models reject parallel tool calls
    )
