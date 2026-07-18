"""
OpenAI client implementing LLMClient.

Key loaded from OPENAI_API_KEY environment variable.
Default model: gpt-4o (override via model= constructor argument or client_factory).

JSON generation uses response_format={"type":"json_object"} — the system
prompt instructs the model to return valid JSON. The schema parameter is
used only to append field names to the system prompt as a hint; OpenAI does
not enforce a JSON schema the way Gemini does.
"""
import json
import logging
import os

from openai import OpenAI

from llm_client import LLMClient

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"


def _schema_hint(schema: dict) -> str:
    """Extract required field names from a JSON schema for prompt injection."""
    items = schema.get("properties", {}).get("cards", {}).get("items", {})
    fields = items.get("required", []) or list(items.get("properties", {}).keys())
    if fields:
        return f"\n\nRequired JSON fields per card: {', '.join(fields)}"
    # fall back to top-level required fields
    top = schema.get("required", [])
    return f"\n\nRequired top-level JSON keys: {', '.join(top)}" if top else ""


class OpenAIClient(LLMClient):
    """
    Single-key OpenAI client. Does not rotate keys (OpenAI rate limits are
    per-organisation, not per-key). For quota-exhaustion handling, wrap in
    a retry loop at the call site.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        key = api_key or os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "No OpenAI key found. Set OPENAI_API_KEY in .env"
            )
        self._client = OpenAI(api_key=key)
        self.model = model or DEFAULT_MODEL
        log.info(f"OpenAIClient: model={self.model}")

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict,
        temperature: float = 0.3,
        max_tokens: int = 6000,
    ) -> str:
        hint = _schema_hint(schema)
        sys_content = (system or "") + hint + "\n\nRespond with valid JSON only. No markdown fences."
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt},
        ]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        # Sanity-parse to surface errors early (same contract as Gemini client)
        json.loads(raw)
        return raw
