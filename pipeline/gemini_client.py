"""
Rotating Gemini client — transparently switches to the next key on quota exhaustion.
Keys are loaded from GEMINI_API_KEY_1 / _2 / _3 (... _N) environment variables.
"""
import logging
import os
import time

from google import genai
from google.genai import types

from llm_client import LLMClient

log = logging.getLogger(__name__)

DEFAULT_MODEL = "models/gemini-2.5-flash"


def _load_keys() -> list[str]:
    keys = []
    i = 1
    while True:
        k = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
        if not k:
            break
        keys.append(k)
        i += 1
    return keys


class RotatingGeminiClient(LLMClient):
    """
    Wraps multiple Gemini API keys. When a key returns 429 it is marked
    exhausted and the next key is tried automatically. Raises RuntimeError
    only when every key is exhausted.
    """

    def __init__(self, keys: list[str] | None = None, model: str = DEFAULT_MODEL):
        resolved = keys if keys is not None else _load_keys()
        if not resolved:
            raise RuntimeError(
                "No Gemini keys found. Set GEMINI_API_KEY_1, GEMINI_API_KEY_2, … in .env"
            )
        self._clients = [genai.Client(api_key=k) for k in resolved]
        self.model = model
        self._exhausted: set[int] = set()
        log.info(f"GeminiClient: {len(self._clients)} key(s) loaded, model={model}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> str:
        """Generate plain text, rotating keys on quota errors."""
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        return self._call(prompt, config=cfg).text or ""

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict,
        temperature: float = 0.3,
        max_tokens: int = 6000,
    ) -> str:
        """Generate with a JSON response schema (structured output). Returns raw JSON string."""
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        return self._call(prompt, config=cfg).text or ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(self, contents, *, config=None):
        active = [i for i in range(len(self._clients)) if i not in self._exhausted]
        if not active:
            raise RuntimeError(f"All {len(self._clients)} Gemini key(s) exhausted")

        for i in active:
            for attempt in range(4):  # up to 3 retries per key for transient errors
                try:
                    resp = self._clients[i].models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    return resp
                except Exception as e:
                    code = getattr(e, "code", None)
                    if code == 429:
                        self._exhausted.add(i)
                        remaining = len(self._clients) - len(self._exhausted)
                        log.warning(
                            f"Gemini key {i + 1}/{len(self._clients)} exhausted "
                            f"— {remaining} key(s) remaining"
                        )
                        break  # try next key
                    if code == 503:
                        wait = 10 * (attempt + 1)  # 10s, 20s, 30s
                        if attempt == 3:
                            raise
                        log.warning(f"Gemini 503 (server overload) — retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    raise  # all other errors propagate immediately

        raise RuntimeError(f"All {len(self._clients)} Gemini key(s) exhausted")
