"""
Agent 2 — Deck Designer.
Given extracted learning items + Deck Spec, produces a Blueprint:
  — ordered sections with item assignments and card counts
  — template selection (or generates new template HTML/CSS if template_new=true)
  — audio decision

The Blueprint is the structural contract for Agent 3 (Card Writer).
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.json"

_BLUEPRINT_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":          {"type": "string"},
                    "card_count":    {"type": "integer"},
                    "card_type":     {"type": "string"},
                    "item_indices":  {"type": "array", "items": {"type": "integer"}},
                    "key_concepts":  {"type": "array", "items": {"type": "string"}},
                    "ordering_note": {"type": "string"},
                },
                "required": ["name", "card_count", "card_type", "item_indices"],
            },
        },
        "template_id":   {"type": "string"},
        "template_new":  {"type": "boolean"},
        "template_files": {},
        "audio_needed":  {"type": "boolean"},
        "total_cards":   {"type": "integer"},
    },
    "required": ["sections", "template_id", "template_new", "audio_needed", "total_cards"],
}

_TEMPLATE_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "front_html": {"type": "string"},
        "back_html":  {"type": "string"},
        "style_css":  {"type": "string"},
    },
    "required": ["front_html", "back_html", "style_css"],
}


def _load_prompts() -> dict:
    return json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))


def _build_blueprint(items: list[dict], deck_spec: dict, client) -> dict:
    prompts = _load_prompts()

    system = prompts["blueprint_generator"]
    if prompts.get("quality_tips"):
        system += "\n\n" + prompts["quality_tips"]
    deck_tips = deck_spec.get("agent_checklists", {}).get("design", "")
    if deck_tips:
        system += f"\n\n--- DECK-SPECIFIC DESIGN CHECKLIST ---\n{deck_tips}"

    # Provide items as a compact indexed list so the agent can assign indices
    indexed_items = [
        {"idx": i, "concept": it.get("concept", ""), "item_type": it.get("item_type", "")}
        for i, it in enumerate(items)
    ]

    user_msg = (
        f"DECK SPEC:\n{json.dumps(deck_spec, indent=2, ensure_ascii=False)}\n\n"
        f"LEARNING ITEMS ({len(items)} total):\n"
        f"{json.dumps(indexed_items, indent=2, ensure_ascii=False)}"
    )

    raw = client.generate_json(
        user_msg,
        system=system,
        schema=_BLUEPRINT_SCHEMA,
        temperature=0.3,
        max_tokens=4000,
    )
    return json.loads(raw)


def _generate_template_files(deck_spec: dict, blueprint: dict, client) -> dict:
    """Call 2 (only when template_new=True): generate front.html, back.html, style.css."""
    prompts = _load_prompts()

    reqs = deck_spec.get("template_requirements") or {}
    user_msg = (
        f"Template ID: {blueprint['template_id']}\n"
        f"Requirements:\n{json.dumps(reqs, indent=2, ensure_ascii=False)}\n\n"
        f"Deck purpose: {deck_spec.get('purpose', '')}\n"
        f"Domain: {deck_spec.get('domain', '')}\n"
        f"Language: {deck_spec.get('language', 'en')}\n"
        f"RTL: {reqs.get('rtl', False)}\n"
        f"Has math: {reqs.get('has_math', False)}\n"
        f"Has code blocks: {reqs.get('has_code_blocks', False)}\n"
        f"Accent color: {reqs.get('accent_color', '#1E3A5F')}\n"
        f"Layout note: {reqs.get('layout_note', '')}"
    )

    raw = client.generate_json(
        user_msg,
        system=prompts["template_generator"],
        schema=_TEMPLATE_FILES_SCHEMA,
        temperature=0.5,
        max_tokens=6000,
    )
    return json.loads(raw)


def design_deck(items: list[dict], deck_spec: dict, client) -> dict:
    """
    Design the deck structure from learning items + Deck Spec.

    Returns a Blueprint dict. If template_new=True, blueprint["template_files"]
    will contain {"front_html": ..., "back_html": ..., "style_css": ...}.
    """
    log.info(f"Agent 2: designing deck structure for {len(items)} items...")

    blueprint = _build_blueprint(items, deck_spec, client)

    n_sections = len(blueprint.get("sections", []))
    total = blueprint.get("total_cards", 0)
    log.info(
        f"Agent 2: blueprint → {n_sections} sections, "
        f"{total} cards total, "
        f"template={blueprint.get('template_id')}, "
        f"audio={blueprint.get('audio_needed')}"
    )
    for sec in blueprint.get("sections", []):
        log.info(
            f"  section '{sec['name']}': "
            f"{sec['card_count']} cards, "
            f"{len(sec.get('item_indices', []))} items"
        )

    if blueprint.get("template_new"):
        log.info("Agent 2: generating new template HTML/CSS...")
        template_files = _generate_template_files(deck_spec, blueprint, client)
        blueprint["template_files"] = template_files
        log.info(
            f"  front.html: {len(template_files['front_html'])} chars, "
            f"back.html: {len(template_files['back_html'])} chars, "
            f"style.css: {len(template_files['style_css'])} chars"
        )
    else:
        blueprint["template_files"] = None

    return blueprint
