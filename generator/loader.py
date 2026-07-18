"""
Loader — reads and validates the three JSON input files defined in INPUT.md:
  1. card type definitions  (card_types/<name>.json)
  2. deck settings          (decks/<name>/deck.json)
  3. card data              (decks/<name>/<section>.json)
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Roles that map to template slots (implemented)
VALID_ROLES = {"question", "answer", "extra", "choices", "image", "audio_override", "cloze"}

# No planned-but-unimplemented roles remain
PLANNED_ROLES: set[str] = set()

VALID_MODES = {"typing", "mchoice", "tapping", "cloze", "reveal", "listen"}

PLANNED_MODES: set[str] = set()

# Roles where only one field per card type definition is allowed
_UNIQUE_ROLES = {"question", "answer", "choices", "cloze"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Card type definition loader
# ---------------------------------------------------------------------------

def load_card_type(path: Path) -> dict:
    path = Path(path).resolve()
    data = _read_json(path)

    # Top-level required keys — note: "templates" not "card_types"
    for key in ("type_id", "fields", "templates"):
        if key not in data:
            raise ValueError(f"{path}: missing required key '{key}'")

    field_names = set()
    seen_unique_roles: set[str] = set()

    for fd in data["fields"]:
        for key in ("name", "role"):
            if key not in fd:
                raise ValueError(f"{path}: field missing required key '{key}'")

        role = fd["role"]
        all_roles = VALID_ROLES | PLANNED_ROLES
        if role not in all_roles:
            raise ValueError(
                f"{path}: unknown role '{role}' "
                f"(valid: {sorted(VALID_ROLES)}, planned: {sorted(PLANNED_ROLES)})"
            )

        # Catch duplicate unique-role fields
        if role in _UNIQUE_ROLES:
            if role in seen_unique_roles:
                raise ValueError(
                    f"{path}: role '{role}' is assigned to more than one field — "
                    f"only one field per card type may have this role"
                )
            seen_unique_roles.add(role)

        field_names.add(fd["name"])

    for tmpl in data["templates"]:
        for key in ("name", "question_field", "answer_field", "mode"):
            if key not in tmpl:
                raise ValueError(f"{path}: templates entry missing required key '{key}'")

        for ref_key in ("question_field", "answer_field"):
            if tmpl[ref_key] not in field_names:
                raise ValueError(
                    f"{path}: templates['{tmpl['name']}'].{ref_key} "
                    f"'{tmpl[ref_key]}' is not defined in fields"
                )

        mode = tmpl["mode"]
        all_modes = VALID_MODES | PLANNED_MODES
        if mode not in all_modes:
            raise ValueError(
                f"{path}: unknown mode '{mode}' "
                f"(valid: {sorted(VALID_MODES)}, planned: {sorted(PLANNED_MODES)})"
            )
        if mode in PLANNED_MODES:
            raise ValueError(
                f"{path}: mode '{mode}' is planned but not yet implemented — "
                f"remove it or use a supported mode: {sorted(VALID_MODES)}"
            )

        if tmpl["mode"] == "mchoice":
            if "choices_field" not in tmpl:
                log.warning(
                    f"{path}: templates['{tmpl['name']}'] is mchoice mode "
                    f"but has no 'choices_field' — choices will be empty"
                )
            elif tmpl["choices_field"] not in field_names:
                raise ValueError(
                    f"{path}: templates['{tmpl['name']}'].choices_field "
                    f"'{tmpl['choices_field']}' is not defined in fields"
                )

    return data


# ---------------------------------------------------------------------------
# Deck settings loader
# ---------------------------------------------------------------------------

def load_deck(deck_dir: Path) -> dict:
    deck_dir  = Path(deck_dir).resolve()
    deck_file = deck_dir / "deck.json"

    if not deck_file.exists():
        raise FileNotFoundError(f"deck.json not found in {deck_dir}")

    data = _read_json(deck_file)

    # Note: key is "types" not "card_types"
    for key in ("deck_name", "output", "types"):
        if key not in data:
            raise ValueError(f"deck.json: missing required key '{key}'")

    if not isinstance(data["types"], list) or len(data["types"]) == 0:
        raise ValueError("deck.json: 'types' must be a non-empty list")

    # Build registry: short id → loaded card type definition
    registry: dict[str, dict] = {}
    for entry in data["types"]:
        for key in ("id", "definition"):
            if key not in entry:
                raise ValueError(f"deck.json: types entry missing '{key}'")

        ct_id   = entry["id"]
        ct_path = (deck_dir / entry["definition"]).resolve()

        if not ct_path.exists():
            raise FileNotFoundError(f"Card type definition not found: {ct_path}")

        log.info(f"  loading type '{ct_id}' from {ct_path.name}")
        registry[ct_id] = load_card_type(ct_path)

    data["_registry"] = registry
    data["_deck_dir"]  = deck_dir
    return data


# ---------------------------------------------------------------------------
# Card data / section loader
# ---------------------------------------------------------------------------

def load_section(path: Path, registry: dict) -> tuple[str, list]:
    """
    Load one card data file. Returns (display_name, valid_cards).

    Supports two formats:
      Array:  [ {card}, {card}, ... ]
              → display name defaults to the filename stem

      Object: { "name": "Chapter 1", "cards": [ {card}, ... ] }
              → display name comes from the "name" key
    """
    path = Path(path)
    raw  = _read_json(path)

    if isinstance(raw, list):
        cards        = raw
        display_name = path.stem
    elif isinstance(raw, dict) and "cards" in raw:
        cards        = raw["cards"]
        display_name = raw.get("name", path.stem)
        if not isinstance(cards, list):
            raise ValueError(f"{path}: 'cards' must be a JSON array")
    else:
        raise ValueError(
            f"{path}: must be a JSON array or an object with a 'cards' key"
        )

    valid  = []
    errors = 0

    for idx, card in enumerate(cards):
        label = f"{path.name}[{idx}]"

        if not isinstance(card, dict):
            log.warning(f"{label}: not an object, skipping")
            errors += 1
            continue

        ct_id = card.get("card_type")
        if not ct_id:
            log.warning(f"{label}: missing 'card_type', skipping")
            errors += 1
            continue

        if ct_id not in registry:
            log.warning(f"{label}: unknown card_type '{ct_id}', skipping")
            errors += 1
            continue

        ct_def = registry[ct_id]

        skip = False
        for fd in ct_def["fields"]:
            if fd.get("required") and not str(card.get(fd["name"], "")).strip():
                log.error(
                    f"{label}: required field '{fd['name']}' is missing or empty, skipping"
                )
                skip   = True
                errors += 1
                break

        if not skip:
            # LaTeX field value sanity check
            for fd in ct_def["fields"]:
                if fd.get("latex"):
                    val = str(card.get(fd["name"], "")).strip()
                    if val and r"\(" not in val and r"\[" not in val:
                        log.warning(
                            f"{label}: field '{fd['name']}' has latex=true "
                            f"but value contains no LaTeX markers (\\( or \\[)"
                        )
            valid.append(card)

    if errors:
        log.warning(f"{path.name}: {errors} card(s) skipped")

    return display_name, valid


# keep old name as alias so nothing breaks if called directly
def load_card_data(path: Path, registry: dict) -> list:
    _, cards = load_section(path, registry)
    return cards
