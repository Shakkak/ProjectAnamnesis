#!/usr/bin/env python3
"""
Custom deck generator — filter master deck by role, domain, style, and level.

Usage:
    python tools/make_deck.py --spec my_spec.json --output custom.apkg
    python tools/make_deck.py --spec my_spec.json --output custom.apkg --skip-audio

The spec JSON is validated against tools/spec_schema.json.
Run from the project root.
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from collections import Counter

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

_ROOT   = Path(__file__).parent.parent
_DECK   = _ROOT / "content" / "decks" / "interview-prep"
_SCHEMA = Path(__file__).parent / "spec_schema.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Spec validation ──────────────────────────────────────────────────────────

def load_and_validate_spec(spec_path: Path) -> dict:
    with open(spec_path) as f:
        spec = json.load(f)
    if _HAS_JSONSCHEMA:
        with open(_SCHEMA) as f:
            schema = json.load(f)
        try:
            jsonschema.validate(spec, schema)
        except jsonschema.ValidationError as e:
            log.error(f"Spec validation failed: {e.message}")
            sys.exit(1)
    else:
        log.warning("jsonschema not installed — skipping spec validation")
    return spec


# ── Card loading ─────────────────────────────────────────────────────────────

def load_all_cards() -> list[dict]:
    """Load every card from the interview-prep deck. Returns flat list."""
    cards = []
    skip = {"retired_ids.json", "deck.json"}
    for path in sorted(_DECK.glob("*.json")):
        if path.name in skip:
            continue
        with open(path) as f:
            data = json.load(f)
        section_cards = data.get("cards", []) if isinstance(data, dict) else data
        for c in section_cards:
            c["_section"] = path.stem
        cards.extend(section_cards)
    log.info(f"Loaded {len(cards)} cards from {_DECK.name}/")
    return cards


# ── Filtering ────────────────────────────────────────────────────────────────

def _tag_values(card: dict, prefix: str) -> set[str]:
    """Extract values for a namespaced prefix, e.g. 'role:' → {'mle', 'ds'}."""
    return {t[len(prefix):] for t in card.get("tags", []) if t.startswith(prefix)}


def filter_cards(cards: list[dict], spec: dict) -> list[dict]:
    max_cards = spec.get("max_cards", 200)
    role_filter   = set(spec.get("role", []))
    level_filter  = set(spec.get("level", []))
    style_filter  = set(spec.get("style", []))
    domain_spec   = spec.get("domain", {})
    must_domains  = set(domain_spec.get("must", []))
    excl_domains  = set(domain_spec.get("exclude", []))
    incl_domains  = set(domain_spec.get("include", []))

    def passes(card: dict) -> bool:
        card_roles   = _tag_values(card, "role:")
        card_domains = _tag_values(card, "domain:")
        card_styles  = _tag_values(card, "style:")
        card_level   = card.get("level", "")

        # exclude domains
        if excl_domains and card_domains & excl_domains:
            return False
        # must domains
        if must_domains and not (card_domains & must_domains):
            return False
        # role filter
        if role_filter and not (card_roles & role_filter):
            return False
        # level filter
        if level_filter and card_level not in level_filter:
            return False
        # style filter
        if style_filter and not (card_styles & style_filter):
            return False
        return True

    passing = [c for c in cards if passes(c)]

    # If include domains specified: sort so include-domain cards come first
    if incl_domains:
        def priority(card: dict) -> int:
            return 0 if _tag_values(card, "domain:") & incl_domains else 1
        passing.sort(key=priority)

    result = passing[:max_cards]
    return result


# ── Summary ──────────────────────────────────────────────────────────────────

def print_summary(cards: list[dict], spec: dict, output: Path) -> None:
    domain_counts: Counter = Counter()
    role_counts: Counter   = Counter()
    level_counts: Counter  = Counter()

    for c in cards:
        for d in _tag_values(c, "domain:"):
            domain_counts[d] += 1
        for r in _tag_values(c, "role:"):
            role_counts[r] += 1
        level_counts[c.get("level", "?")] += 1

    print(f"\n{'─'*55}")
    print(f"  Custom deck: {output.name}")
    print(f"  Total cards: {len(cards)}")
    print(f"\n  Domains:")
    for d, n in domain_counts.most_common():
        print(f"    {d:<30} {n}")
    print(f"\n  Roles:")
    for r, n in role_counts.most_common():
        print(f"    {r:<30} {n}")
    print(f"\n  Levels:")
    for lv in ("fundamental", "intermediate", "advanced"):
        print(f"    {lv:<30} {level_counts.get(lv, 0)}")
    print(f"{'─'*55}\n")


# ── Deck building ────────────────────────────────────────────────────────────

def build_custom_deck(cards: list[dict], output: Path, skip_audio: bool) -> None:
    """Group filtered cards into sections and call the generator."""
    sys.path.insert(0, str(_ROOT / "generator"))
    from loader import load_deck
    from generator import build_deck, generate_audio
    from tts.kokoro_provider import generate_audio as tts_provider

    # Load master deck config (card type registry, templates, etc.)
    deck_config = load_deck(_DECK)

    # Override output path
    deck_config["output"] = str(output.resolve())
    deck_config["_deck_dir"] = str(_DECK)

    # Group cards by section
    from collections import defaultdict
    by_section: dict[str, list] = defaultdict(list)
    for c in cards:
        by_section[c.get("_section", "custom")].append(c)

    sections = [{"name": name, "cards": cards_}
                for name, cards_ in by_section.items()]

    if not skip_audio:
        registry = deck_config["_registry"]
        generate_audio(sections, registry, tts_provider, force_regen=False)

    build_deck(deck_config, sections)
    log.info(f"✓  Deck written to {output}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a custom Anki deck from a spec JSON file."
    )
    parser.add_argument("--spec",   required=True,  type=Path, help="Path to spec JSON file")
    parser.add_argument("--output", required=True,  type=Path, help="Output .apkg path")
    parser.add_argument("--skip-audio", action="store_true",
                        help="Skip TTS audio generation (faster, text-only deck)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show summary without generating the deck")
    args = parser.parse_args()

    spec   = load_and_validate_spec(args.spec)
    cards  = load_all_cards()
    result = filter_cards(cards, spec)

    if not result:
        log.error("No cards matched the spec. Check your filters.")
        sys.exit(1)

    print_summary(result, spec, args.output)

    if args.dry_run:
        log.info("Dry run — deck not written.")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    build_custom_deck(result, args.output, args.skip_audio)


if __name__ == "__main__":
    main()
