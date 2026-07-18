"""
Agent 3 — Card Writer (formerly Structure Decider).
Converts learning items into Anki card data JSON.

When a Blueprint is provided:
  — processes items section-by-section (item_indices from Blueprint)
  — respects card_count budget per section
  — writes to multiple sections

Without a Blueprint (legacy / canvas mode):
  — processes all items as a single flat batch (original behavior preserved)
"""
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.json"
_BATCH_SIZE = 10  # items per Agent 3 call

_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "section_name": {"type": "string"},
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
                },
                "required": ["card_type", "question", "answer", "steps", "hint", "tags", "source_nodes", "level"],
            },
        },
    },
    "required": ["section_name", "cards"],
}

_VALID_LEVELS = {"fundamental", "intermediate", "advanced"}


def _load_system(deck_spec: dict | None = None) -> str:
    prompts = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
    system = prompts["system"]
    if prompts.get("quality_tips"):
        system += "\n\n" + prompts["quality_tips"]
    deck_tips = (deck_spec or {}).get("agent_checklists", {}).get("writing", "")
    if deck_tips:
        system += f"\n\n--- DECK-SPECIFIC WRITING CHECKLIST ---\n{deck_tips}"
    return system


def _build_context_block(
    deck_spec: dict | None,
    section: dict | None,
    feedback_comments: list[str] | None,
    vault_slugs: list[str] | None,
) -> str:
    """Build the contextual prefix injected into each user prompt."""
    parts = []

    if deck_spec:
        parts.append(
            f"DECK SPEC:\n"
            f"  Purpose  : {deck_spec.get('purpose', '')}\n"
            f"  Audience : {deck_spec.get('audience_level', 'intermediate')}\n"
            f"  Domain   : {deck_spec.get('domain', 'general')}\n"
            f"  Depth    : {deck_spec.get('depth', '')}\n"
        )

    if section:
        parts.append(
            f"BLUEPRINT SECTION:\n"
            f"  Name      : {section['name']}\n"
            f"  Card type : {section.get('card_type', 'reveal')}\n"
            f"  Target    : {section.get('card_count', 'unspecified')} cards\n"
            f"  Concepts  : {', '.join(section.get('key_concepts', []))}\n"
            + (f"  Note      : {section['ordering_note']}\n" if section.get('ordering_note') else "")
        )

    if vault_slugs:
        parts.append(
            "Available source_nodes slugs (use ONLY slugs from this list):\n"
            + ", ".join(vault_slugs)
        )

    if feedback_comments:
        lines = "\n".join(f"  - {c}" for c in feedback_comments)
        parts.append(
            f"FEEDBACK FROM PREVIOUS REVIEW:\n"
            f"The following cards were rejected. Generate improved replacements:\n{lines}\n"
            f"Do not reproduce the rejected cards."
        )

    return "\n\n".join(parts)


def _call_agent3(
    items: list[dict],
    section_name: str,
    client,
    context_block: str = "",
    deck_spec: dict | None = None,
) -> dict:
    system = _load_system(deck_spec)
    prompt = (
        (context_block + "\n\n" if context_block else "")
        + f"Section name: {section_name}\n\n"
        + f"Learning items:\n{json.dumps(items, indent=2, ensure_ascii=False)}"
    )
    raw = client.generate_json(
        prompt,
        system=system,
        schema=_CARD_SCHEMA,
        temperature=0.2,
        max_tokens=12000,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"Agent 3: JSON parse failed at pos {e.pos} — raw length {len(raw)}")
        log.error(f"  context: {repr(raw[max(0, e.pos-40):e.pos+40])}")
        raise


def _validate_card_fields(card: dict, vault_slug_set: set[str]) -> list[str]:
    warnings = []
    level = card.get("level", "")
    if level not in _VALID_LEVELS:
        warnings.append(f"invalid level {repr(level)}")
    source_nodes = card.get("source_nodes", [])
    if not source_nodes:
        warnings.append("source_nodes is empty")
    elif vault_slug_set:
        bad = [s for s in source_nodes if s not in vault_slug_set]
        if bad:
            warnings.append(f"unknown source_nodes slugs: {bad}")
    tags = card.get("tags", [])
    has_role   = any(t.startswith("role:")   for t in tags)
    has_domain = any(t.startswith("domain:") for t in tags)
    has_style  = any(t.startswith("style:")  for t in tags)
    if not (has_role and has_domain and has_style):
        missing = [p for p, ok in [("role:", has_role), ("domain:", has_domain), ("style:", has_style)] if not ok]
        warnings.append(f"missing namespaced tags: {missing}")
    return warnings


def _log_validation(cards: list[dict], vault_slug_set: set[str], section_name: str) -> None:
    issues = 0
    for card in cards:
        for w in _validate_card_fields(card, vault_slug_set):
            q_preview = card.get("question", "")[:60]
            log.warning(f"  card validation [{section_name}] {repr(q_preview)}: {w}")
            issues += 1
    if issues:
        log.warning(f"  {issues} validation issue(s) in {len(cards)} cards")
    else:
        log.info(f"  card validation: {len(cards)} cards OK")


def _write_section(
    items: list[dict],
    section_name: str,
    client,
    context_block: str,
    batch_cache_dir: Path | None,
    feedback_comments: list[str] | None,
    vault_slug_set: set[str],
    section_idx: int = 0,
    deck_spec: dict | None = None,
) -> list[dict]:
    """Write cards for a single section, batching if needed. Returns card list."""
    if len(items) <= _BATCH_SIZE:
        result = _call_agent3(items, section_name, client, context_block=context_block, deck_spec=deck_spec)
        cards = result.get("cards", [])
        _log_validation(cards, vault_slug_set, section_name)
        return cards

    batches = [items[i:i + _BATCH_SIZE] for i in range(0, len(items), _BATCH_SIZE)]
    all_cards: list[dict] = []

    def _bar(done: int, total: int, width: int = 10) -> str:
        filled = int(width * done / total) if total else 0
        return f"[{'█' * filled}{'░' * (width - filled)}]"

    for i, batch in enumerate(batches):
        # Per-batch cache keyed by section index + batch index
        cache_file = (
            batch_cache_dir / f"s{section_idx:02d}_batch_{i:02d}.json"
            if batch_cache_dir and not feedback_comments
            else None
        )
        if cache_file and cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            batch_cards = cached.get("cards", [])
            all_cards.extend(batch_cards)
            log.info(f"  ┤ Agent 3 {_bar(i+1, len(batches))} [{section_name}] batch {i+1}/{len(batches)} [cache] +{len(batch_cards)} cards")
            continue

        result = _call_agent3(batch, section_name, client, context_block=context_block, deck_spec=deck_spec)
        batch_cards = result.get("cards", [])
        all_cards.extend(batch_cards)

        if cache_file:
            cache_file.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

        log.info(f"  ┤ Agent 3 {_bar(i+1, len(batches))} [{section_name}] batch {i+1}/{len(batches)} [API] +{len(batch_cards)} cards")

        if i < len(batches) - 1:
            time.sleep(5)

    _log_validation(all_cards, vault_slug_set, section_name)
    return all_cards


def build_card_data(
    items: list[dict],
    section_name: str,
    client,
    batch_cache_dir: Path | None = None,
    feedback_comments: list[str] | None = None,
    vault_slugs: list[str] | None = None,
    deck_spec: dict | None = None,
    blueprint: dict | None = None,
    user_feedback: str = "",
) -> dict | list[dict]:
    """
    Convert learning items to card data.

    With Blueprint: processes items section-by-section per blueprint.item_indices.
    Returns list[{"name": ..., "cards": [...]}]  (one entry per section).

    Without Blueprint (legacy): processes all items as one section.
    Returns dict {"section_name": ..., "types_used": [...], "cards": [...]}

    user_feedback: free-text feedback from the preview step, injected into prompts.
    """
    vault_slug_set = set(vault_slugs) if vault_slugs else set()

    # Merge user_feedback into feedback_comments for prompt injection
    all_feedback = list(feedback_comments or [])
    if user_feedback.strip():
        all_feedback.append(f"[Preview feedback] {user_feedback.strip()}")

    if blueprint and blueprint.get("sections"):
        return _write_blueprint_sections(
            items, blueprint, client,
            batch_cache_dir=batch_cache_dir,
            feedback_comments=all_feedback or None,
            vault_slugs=vault_slugs,
            vault_slug_set=vault_slug_set,
            deck_spec=deck_spec,
        )

    # ── Legacy / canvas path: single section ─────────────────────────────────
    if all_feedback:
        log.info(f"Agent 3: {len(all_feedback)} feedback comment(s) injected for '{section_name}'")
    log.info(f"Agent 3: writing {len(items)} items → '{section_name}'...")

    context_block = _build_context_block(deck_spec, None, all_feedback or None, vault_slugs)
    cards = _write_section(
        items, section_name, client,
        context_block=context_block,
        batch_cache_dir=batch_cache_dir,
        feedback_comments=all_feedback or None,
        vault_slug_set=vault_slug_set,
        deck_spec=deck_spec,
    )

    log.info(f"Agent 3: {len(cards)} cards in '{section_name}'")
    types_used = list({c.get("card_type", "reveal") for c in cards})
    return {"section_name": section_name, "types_used": types_used, "cards": cards}


def _write_blueprint_sections(
    items: list[dict],
    blueprint: dict,
    client,
    batch_cache_dir: Path | None,
    feedback_comments: list[str] | None,
    vault_slugs: list[str] | None,
    vault_slug_set: set[str],
    deck_spec: dict | None,
) -> list[dict]:
    """Write all blueprint sections. Returns list of {name, cards} dicts."""
    sections_out = []
    total_written = 0

    for sec_idx, section in enumerate(blueprint["sections"]):
        sec_name = section["name"]
        indices  = section.get("item_indices") or []

        # Select items for this section (fall back to proportional slice if no indices)
        if indices:
            sec_items = [items[i] for i in indices if i < len(items)]
        else:
            # Proportional slice fallback
            total_sections = len(blueprint["sections"])
            chunk = max(1, len(items) // total_sections)
            start = sec_idx * chunk
            sec_items = items[start:start + chunk]

        log.info(
            f"Agent 3: section {sec_idx+1}/{len(blueprint['sections'])} "
            f"'{sec_name}' — {len(sec_items)} items..."
        )

        context_block = _build_context_block(deck_spec, section, feedback_comments, vault_slugs)
        cards = _write_section(
            sec_items, sec_name, client,
            context_block=context_block,
            batch_cache_dir=batch_cache_dir,
            feedback_comments=feedback_comments,
            vault_slug_set=vault_slug_set,
            section_idx=sec_idx,
            deck_spec=deck_spec,
        )

        sections_out.append({"name": sec_name, "cards": cards})
        total_written += len(cards)
        log.info(f"  → {len(cards)} cards  (running total: {total_written})")

        if sec_idx < len(blueprint["sections"]) - 1:
            time.sleep(3)

    return sections_out


def write_sample_cards(
    items: list[dict],
    section_name: str,
    client,
    deck_spec: dict | None = None,
    blueprint_section: dict | None = None,
    vault_slugs: list[str] | None = None,
) -> list[dict]:
    """
    Write exactly 2 sample cards for the preview step.
    Takes item[0] and item[mid] from the list.
    """
    n = len(items)
    if n == 0:
        return []
    sample_indices = [0] if n == 1 else [0, n // 2]
    sample_items = [items[i] for i in sample_indices]

    context_block = _build_context_block(deck_spec, blueprint_section, None, vault_slugs)
    log.info(f"Agent 3: writing {len(sample_items)} preview cards...")

    result = _call_agent3(sample_items, section_name, client, context_block=context_block, deck_spec=deck_spec)
    cards = result.get("cards", [])
    log.info(f"Agent 3: {len(cards)} preview card(s) ready")
    return cards
