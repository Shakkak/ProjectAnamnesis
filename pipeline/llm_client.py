"""
Abstract LLM client interface.

Both RotatingGeminiClient and OpenAIClient implement this interface so the
rest of the pipeline is provider-agnostic.
"""
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Minimal interface required by Agent 1 and Agent 2."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 100,
    ) -> str:
        """Generate plain text."""
        ...

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict,
        temperature: float = 0.3,
        max_tokens: int = 6000,
    ) -> str:
        """Generate structured JSON. Returns raw JSON string."""
        ...
