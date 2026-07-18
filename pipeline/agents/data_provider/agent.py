"""
Agent 1 — Data Provider.
Two modes:
  extract  — given source text, extract structured learning items (file/canvas input)
  generate — given a Deck Spec, synthesize learning items from the LLM's own knowledge (no file)

When a Deck Spec is provided, it is injected into the system prompt as context
so the agent calibrates depth, audience level, and topic focus accordingly.
"""
import json
import logging
from pathlib import Path

from gemini_client import RotatingGeminiClient

log = logging.getLogger(__name__)

_GUIDES_DIR   = Path(__file__).parent.parent / "guides"
_PROMPTS_FILE = Path(__file__).parent / "prompts.json"

_KNOWN_DOMAINS = {"mathematics", "language", "programming", "science", "history", "general"}

def _load_prompts() -> dict:
    return json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))

_PROMPTS = _load_prompts()
_DOMAIN_DETECT_SYSTEM = _PROMPTS["domain_detect"]
_BASE_SYSTEM          = _PROMPTS["base_system"]
_GENERATE_SYSTEM      = _PROMPTS["generate_system"]

# Gemini response schema — ensures valid JSON regardless of LaTeX content
_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept":      {"type": "string"},
                    "item_type":    {"type": "string"},
                    "question":     {"type": "string"},
                    "answer":       {"type": "string"},
                    "details":      {"type": "string"},
                    "tags":         {"type": "array", "items": {"type": "string"}},
                    "pattern_note": {"type": "string"},
                    "confidence":   {"type": "string"},
                },
                "required": ["concept", "item_type", "question", "answer", "details", "tags"],
            },
        }
    },
    "required": ["items"],
}


def _detect_domain(text: str, client) -> str:
    raw = client.generate(
        text[:3000],
        system=_DOMAIN_DETECT_SYSTEM,
        temperature=0,
        max_tokens=10,
    )
    word = raw.strip().lower().split()[0] if raw.strip() else "general"
    return word if word in _KNOWN_DOMAINS else "general"


def _load_guide(domain: str) -> str | None:
    path = _GUIDES_DIR / f"{domain}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def detect_domain(text: str, client) -> str:
    """Detect domain from a text sample. Call once per run, reuse across levels."""
    log.info("Agent 1: detecting domain...")
    domain = _detect_domain(text, client)
    log.info(f"Agent 1: domain → {domain}")
    return domain


def _deck_spec_preamble(deck_spec: dict) -> str:
    """Build a preamble block that contextualises the agent for a specific deck."""
    lines = [
        "DECK CONTEXT (use this to calibrate depth, audience, and scope):",
        f"  Purpose       : {deck_spec.get('purpose', '')}",
        f"  Audience      : {deck_spec.get('audience_level', 'intermediate')}",
        f"  Domain        : {deck_spec.get('domain', 'general')}",
        f"  Depth         : {deck_spec.get('depth', '')}",
        f"  Target count  : {deck_spec.get('target_card_count', 50)} items",
    ]
    hints = deck_spec.get("section_hints") or []
    if hints:
        lines.append(f"  Topics to cover: {', '.join(hints)}")
    return "\n".join(lines) + "\n\n"


def build_system_prompt(domain: str, deck_spec: dict | None = None) -> str:
    """Build the Agent 1 system prompt for extract mode."""
    guide = _load_guide(domain)
    preamble = _deck_spec_preamble(deck_spec) if deck_spec else ""
    base = _BASE_SYSTEM
    if guide:
        log.info(f"Agent 1: {domain} guide loaded ({len(guide):,} chars)")
        base = base + f"\n\n--- DOMAIN GUIDE: {domain.upper()} ---\n{guide}"
    else:
        log.info("Agent 1: no domain guide — using base prompt")

    static_tips = _PROMPTS.get("quality_tips", "")
    if static_tips:
        base = base + f"\n\n{static_tips}"

    deck_tips = (deck_spec or {}).get("agent_checklists", {}).get("extraction", "")
    if deck_tips:
        base = base + f"\n\n--- DECK-SPECIFIC EXTRACTION CHECKLIST ---\n{deck_tips}"

    return preamble + base


def _build_generate_system(deck_spec: dict) -> str:
    """Build system prompt for generate mode (no source file)."""
    preamble = _deck_spec_preamble(deck_spec)
    return preamble + _GENERATE_SYSTEM


def extract_learning_items(
    text: str,
    client,
    system: str | None = None,
    context_note: str = "",
    deck_spec: dict | None = None,
) -> list[dict]:
    """
    Extract learning items from source text (extract mode).

    system: pre-built system prompt. If None, detects domain and builds it.
    deck_spec: if provided, injects context into the system prompt.
    """
    if system is None:
        domain = detect_domain(text, client)
        system = build_system_prompt(domain, deck_spec=deck_spec)
    elif deck_spec:
        # Prepend deck context to an already-built system prompt
        system = _deck_spec_preamble(deck_spec) + system

    log.info("Agent 1: extracting learning items...")

    prompt = f"Extract learning items from this material:\n\n{text}"
    if context_note:
        prompt = f"{context_note}\n\n{prompt}"

    raw = client.generate_json(
        prompt,
        system=system,
        schema=_ITEM_SCHEMA,
        temperature=0.3,
        max_tokens=16384,
    )
    data  = json.loads(raw)
    items = data["items"]
    log.info(f"Agent 1: extracted {len(items)} learning items")
    return items


def generate_learning_items(deck_spec: dict, client) -> list[dict]:
    """
    Generate learning items from scratch (generate mode, no source file).
    Uses the LLM's own knowledge guided by the Deck Spec.
    """
    system = _build_generate_system(deck_spec)
    log.info(
        f"Agent 1: generating items from scratch "
        f"(domain={deck_spec.get('domain')}, "
        f"target={deck_spec.get('target_card_count')} items)..."
    )

    section_block = ""
    hints = deck_spec.get("section_hints") or []
    if hints:
        section_block = f"\n\nTopics to cover (in roughly this order):\n" + "\n".join(f"  - {h}" for h in hints)

    prompt = (
        f"Generate comprehensive learning items for a flashcard deck.\n"
        f"Purpose: {deck_spec.get('purpose', '')}\n"
        f"Audience: {deck_spec.get('audience_level', 'intermediate')}\n"
        f"Depth: {deck_spec.get('depth', '')}\n"
        f"Target item count: {deck_spec.get('target_card_count', 50)}"
        f"{section_block}"
    )

    raw = client.generate_json(
        prompt,
        system=system,
        schema=_ITEM_SCHEMA,
        temperature=0.5,
        max_tokens=16384,
    )
    data  = json.loads(raw)
    items = data["items"]
    log.info(f"Agent 1: generated {len(items)} learning items")
    return items
