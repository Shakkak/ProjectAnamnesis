"""Load cards from deck JSON directories, with their card-type definitions."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DECKS_DIR = PROJECT_ROOT / "content" / "decks"
CARD_TYPES_DIR = PROJECT_ROOT / "content" / "card_types"

# Make generator importable
sys.path.insert(0, str(PROJECT_ROOT / "generator"))


def load_card_types() -> dict:
    """Return all built-in card type definitions keyed by type_id."""
    defs = {}
    for f in CARD_TYPES_DIR.glob("*.json"):
        ct = json.loads(f.read_text())
        defs[ct["type_id"]] = ct
    return defs


def list_decks() -> list[str]:
    return sorted(d.name for d in DECKS_DIR.iterdir() if d.is_dir())


def load_deck(deck_name: str) -> tuple[dict, list[dict]]:
    """Return (deck_config, [card, ...]).

    Each card dict has extra keys injected:
        _id       — stable card id (from json or computed)
        _section  — section name
        _deck     — deck name
        _ct_def   — card type definition dict
    """
    deck_dir = DECKS_DIR / deck_name
    deck_cfg = json.loads((deck_dir / "deck.json").read_text())

    # Build registry: type_id → definition
    built_in = load_card_types()
    registry: dict = {}
    for entry in deck_cfg.get("types", []):
        type_id = entry if isinstance(entry, str) else entry.get("id", "")
        if type_id in built_in:
            registry[type_id] = built_in[type_id]

    cards = []
    for json_file in sorted(deck_dir.glob("*.json")):
        if json_file.name == "deck.json":
            continue
        data = json.loads(json_file.read_text())
        is_list = isinstance(data, list)
        section = json_file.stem if is_list else data.get("section", json_file.stem)
        raw_cards = data if is_list else data.get("cards", [])

        for card in raw_cards:
            ct_id = card.get("card_type", "reveal")
            card["_id"] = card.get("id") or _compute_id(section, card)
            card["_section"] = section
            card["_deck"] = deck_name
            card["_ct_def"] = registry.get(ct_id, built_in.get(ct_id, {}))
            cards.append(card)

    return deck_cfg, cards


def _compute_id(section: str, card: dict) -> str:
    import hashlib
    for f in ("question", "front", "text", "cloze"):
        q = str(card.get(f, "")).strip()
        if q:
            break
    return hashlib.md5(f"{section}|||{q[:120]}".encode()).hexdigest()[:16]
