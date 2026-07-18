"""
Anthropic client implementing LLMClient.

Key loaded from ANTHROPIC_API_KEY environment variable.
Default model: claude-sonnet-4-6 (override via ANTHROPIC_MODEL env var or model= arg).

Anthropic does not have a native json_object response mode. generate_json()
injects JSON-mode instructions into the system prompt and strips any accidental
markdown fences from the response before returning.
"""
import json
import logging
import os
import re

import anthropic

from llm_client import LLMClient

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the model wrapped its JSON output."""
    m = _FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


def _schema_hint(schema: dict) -> str:
    """Extract required card field names from a JSON schema for prompt injection."""
    items = schema.get("properties", {}).get("cards", {}).get("items", {})
    fields = items.get("required", []) or list(items.get("properties", {}).keys())
    if fields:
        return f"\nRequired JSON fields per card object: {', '.join(fields)}"
    top = schema.get("required", [])
    return f"\nRequired top-level JSON keys: {', '.join(top)}" if top else ""


class AnthropicClient(LLMClient):

    def __init__(self, api_key: str | None = None, model: str | None = None):
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise RuntimeError("No Anthropic key found. Set ANTHROPIC_API_KEY in .env")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        log.info(f"AnthropicClient: model={self.model}")

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> str:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        return resp.content[0].text if resp.content else ""

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
        sys_content = (
            (system or "")
            + hint
            + "\n\nRespond with valid JSON only. No explanation. No markdown fences."
        )
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=sys_content,
            messages=[{"role": "user", "content": prompt}],
        )
        resp = self._client.messages.create(**kwargs)
        raw = resp.content[0].text if resp.content else ""
        raw = _strip_fences(raw)
        json.loads(raw)  # surface parse errors early
        return raw
