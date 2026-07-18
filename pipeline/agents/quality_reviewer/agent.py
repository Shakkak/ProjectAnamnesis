"""
Agent 4 — Quality Reviewer.
Lightweight review pass over generated cards.

Checks per card:
  — Weak question fronts (forces rewrite to teaching question)
  — Incomplete answers
  — Wrong difficulty level
  — Duplicate coverage (flags weaker duplicate for removal)

Processes cards in batches of 15 to keep context size manageable.
Cards marked drop=true are removed from the final output.
"""
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.json"
_BATCH_SIZE = 15


def _load_system(deck_spec: dict | None = None) -> str:
    prompts = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
    system = prompts["review_system"]
    if prompts.get("quality_tips"):
        system += "\n\n" + prompts["quality_tips"]
    deck_tips = (deck_spec or {}).get("agent_checklists", {}).get("review", "")
    if deck_tips:
        system += f"\n\n--- DECK-SPECIFIC REVIEW CHECKLIST ---\n{deck_tips}"
    return system


def _review_batch(
    cards: list[dict],
    section_name: str,
    deck_spec: dict,
    client,
) -> tuple[list[dict], int, str]:
    """
    Review a batch of cards. Returns (reviewed_cards, issues_found, issues_summary).
    """
    _REVIEW_SCHEMA = {
        "type": "object",
        "properties": {
            "cards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_type":    {"type": "string"},
                        "question":     {"type": "string"},
                        "answer":       {"type": "string"},
                        "steps":        {"type": "string"},
                        "hint":         {"type": "string"},
                        "tags":         {"type": "array", "items": {"type": "string"}},
                        "source_nodes": {"type": "array", "items": {"type": "string"}},
                        "level":        {"type": "string"},
                        "drop":         {"type": "boolean"},
                    },
                    "required": ["card_type", "question", "answer", "level", "drop"],
                },
            },
            "issues_found":   {"type": "integer"},
            "issues_summary": {"type": "string"},
        },
        "required": ["cards", "issues_found", "issues_summary"],
    }

    system = _load_system(deck_spec)
    user_msg = (
        f"Section: {section_name}\n"
        f"Deck Spec:\n{json.dumps(deck_spec, indent=2, ensure_ascii=False)}\n\n"
        f"Cards to review ({len(cards)}):\n"
        f"{json.dumps(cards, indent=2, ensure_ascii=False)}"
    )

    raw = client.generate_json(
        user_msg,
        system=system,
        schema=_REVIEW_SCHEMA,
        temperature=0.1,
        max_tokens=8000,
    )
    data = json.loads(raw)
    return data["cards"], data["issues_found"], data.get("issues_summary", "")


def review_cards(
    cards: list[dict],
    section_name: str,
    deck_spec: dict,
    client,
) -> list[dict]:
    """
    Review all cards in a section. Returns the cleaned card list (dropped cards removed).
    """
    if not cards:
        return cards

    log.info(f"Agent 4: reviewing {len(cards)} cards in '{section_name}'...")

    batches = [cards[i:i + _BATCH_SIZE] for i in range(0, len(cards), _BATCH_SIZE)]
    all_reviewed: list[dict] = []
    total_issues = 0

    for i, batch in enumerate(batches):
        reviewed_batch, issues, summary = _review_batch(batch, section_name, deck_spec, client)
        total_issues += issues
        if issues > 0:
            log.info(f"  batch {i+1}/{len(batches)}: {issues} issue(s) — {summary}")
        else:
            log.info(f"  batch {i+1}/{len(batches)}: clean")
        all_reviewed.extend(reviewed_batch)
        if i < len(batches) - 1:
            time.sleep(3)

    # Remove cards marked for dropping
    before = len(all_reviewed)
    kept = [c for c in all_reviewed if not c.pop("drop", False)]
    dropped = before - len(kept)

    log.info(
        f"Agent 4: '{section_name}' — {total_issues} total issues, "
        f"{dropped} card(s) dropped, {len(kept)} cards kept"
    )
    return kept
