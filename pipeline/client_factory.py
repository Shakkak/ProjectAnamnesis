"""
LLM client factory — single place to configure provider and model.

Provider selection order (first match wins):
  1. Explicit provider= argument or LLM_PROVIDER env var
  2. Auto-detect from available API keys (OpenAI > Anthropic > Gemini)

Model selection order:
  1. Explicit model= argument
  2. LLM_MODEL env var
  3. Provider default (see PROVIDER_DEFAULTS)

Configuration via environment variables:
  LLM_PROVIDER        = openai | anthropic | gemini
  LLM_MODEL           = <any model name>

  OPENAI_API_KEY      = sk-...
  ANTHROPIC_API_KEY   = sk-ant-...
  GEMINI_API_KEY_1    = ...          (GEMINI_API_KEY_2, _3, ... for key rotation)

CLI usage in pipeline:
  --provider openai --model gpt-4o
  --provider anthropic --model claude-opus-4-8
  --provider gemini --model gemini-2.5-pro
"""
import logging
import os

from llm_client import LLMClient

log = logging.getLogger(__name__)

# Default model for each provider — intentionally decent, not "mini"
PROVIDER_DEFAULTS: dict[str, str] = {
    "openai":    "gpt-4o",
    "anthropic": "claude-opus-4-8",
    "gemini":    "gemini-2.5-pro",
}

# Known model lists — informational only, not enforced (new models ship constantly)
KNOWN_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
    ],
    "anthropic": [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
}


def _detect_provider() -> str | None:
    """Return the first provider whose API key is present in the environment."""
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.getenv("GEMINI_API_KEY_1", "").strip():
        return "gemini"
    return None


def build_client(
    provider: str | None = None,
    model: str | None = None,
) -> LLMClient:
    """
    Build an LLM client.

    provider: "openai" | "anthropic" | "gemini" | None (auto-detect)
    model:    model name string          | None (use provider default)
    """
    # Resolve provider
    resolved_provider = (
        provider
        or os.getenv("LLM_PROVIDER", "").strip().lower()
        or _detect_provider()
    )
    if not resolved_provider:
        raise RuntimeError(
            "No LLM provider found. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GEMINI_API_KEY_1 — or pass --provider explicitly."
        )
    if resolved_provider not in PROVIDER_DEFAULTS:
        raise ValueError(
            f"Unknown provider {repr(resolved_provider)}. "
            f"Choose from: {', '.join(PROVIDER_DEFAULTS)}"
        )

    # Resolve model
    resolved_model = (
        model
        or os.getenv("LLM_MODEL", "").strip()
        or PROVIDER_DEFAULTS[resolved_provider]
    )

    log.info(f"LLM: provider={resolved_provider}  model={resolved_model}")

    if resolved_provider == "openai":
        from openai_client import OpenAIClient
        return OpenAIClient(model=resolved_model)

    if resolved_provider == "anthropic":
        from anthropic_client import AnthropicClient
        return AnthropicClient(model=resolved_model)

    if resolved_provider == "gemini":
        from gemini_client import RotatingGeminiClient
        return RotatingGeminiClient(model=resolved_model)

    raise ValueError(f"Unhandled provider: {resolved_provider}")  # unreachable


def list_providers() -> str:
    """Human-readable summary of providers and their default/known models."""
    lines = ["Available providers and models:\n"]
    for p, default in PROVIDER_DEFAULTS.items():
        known = KNOWN_MODELS.get(p, [])
        lines.append(f"  {p:<12}  default: {default}")
        others = [m for m in known if m != default]
        if others:
            lines.append(f"              other:   {', '.join(others)}")
    lines.append(
        "\nSet via env:  LLM_PROVIDER=<provider>  LLM_MODEL=<model>\n"
        "Set via CLI:  --provider <provider> --model <model>"
    )
    return "\n".join(lines)
