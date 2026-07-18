#!/usr/bin/env python3
"""
Anki deck generator — entry point.

Usage (via cli.sh or direct):
    python3 generator/main.py --deck content/decks/english
    python3 generator/main.py --deck content/decks/english --skip-audio
    python3 generator/main.py --deck content/decks/english --output-dir ./output
    python3 generator/main.py --validate-type content/card_types/vocab.json
    python3 generator/main.py --deck content/decks/english --retire

    # External data root (optional):
    python3 generator/main.py --bank /path/to/data --deck decks/english
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from loader import load_deck, load_section, load_card_type
import generator as _gen
from generator import generate_audio, build_deck, build_retired_deck

_ROOT = Path(__file__).parent.parent

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def cmd_validate_type(path: str) -> None:
    """Validate a card type definition file standalone — no deck needed."""
    try:
        ct_def = load_card_type(Path(path))
    except (FileNotFoundError, ValueError) as e:
        log.error(f"❌  {e}")
        sys.exit(1)

    tid = ct_def["type_id"]
    n_fields    = len(ct_def["fields"])
    n_templates = len(ct_def["templates"])
    log.info(f"✅  {tid}  —  {n_fields} field(s), {n_templates} template(s)")

    for fd in ct_def["fields"]:
        audio = " [audio]" if fd.get("audio") else ""
        latex = " [latex]" if fd.get("latex") else ""
        log.info(f"    {fd['role']:15}  {fd['name']:25}  label='{fd.get('label', fd['name'])}'{audio}{latex}")

    for tmpl in ct_def["templates"]:
        log.info(
            f"    template: '{tmpl['name']}'"
            f"  mode={tmpl['mode']}"
            f"  theme={tmpl.get('theme','MemRise')}"
            f"  Q={tmpl['question_field']} → A={tmpl['answer_field']}"
        )


def cmd_list_types(deck_config: dict) -> None:
    """Print all card types registered in this deck and their fields."""
    registry = deck_config["_registry"]
    log.info(f"Deck: {deck_config['deck_name']}  —  {len(registry)} type(s)")
    for ct_id, ct_def in registry.items():
        log.info(f"\n  [{ct_id}]  type_id={ct_def['type_id']}")
        for fd in ct_def["fields"]:
            flags = []
            if fd.get("required"):    flags.append("required")
            if fd.get("audio"):       flags.append("audio")
            if fd.get("latex"):       flags.append("latex")
            if fd.get("alternatives"):flags.append("alternatives")
            flag_str = f"  ({', '.join(flags)})" if flags else ""
            log.info(f"    {fd['role']:15}  {fd['name']:25}  label='{fd.get('label', fd['name'])}'{flag_str}")
        for tmpl in ct_def["templates"]:
            log.info(
                f"    template: '{tmpl['name']}'"
                f"  mode={tmpl['mode']}"
                f"  Q={tmpl['question_field']} → A={tmpl['answer_field']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Anki deck generator")

    # Bank / output location
    parser.add_argument("--bank", metavar="PATH",
                        default=os.environ.get("BANK_PATH"),
                        help="Path to external data root (or set BANK_PATH env var); defaults to content/ in this repo")
    parser.add_argument("--output-dir", metavar="PATH", default=None,
                        help="Directory for .apkg output (required in bank mode; standalone uses deck.json path)")

    # Standalone commands
    parser.add_argument("--validate-type", metavar="FILE",
                        help="Validate a card type definition file (no deck needed)")

    # Deck commands
    parser.add_argument("--deck", metavar="DIR",
                        help="Path to deck folder relative to --bank, or absolute")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Validate inputs only — no files written")
    parser.add_argument("--skip-audio",   action="store_true",
                        help="Skip TTS generation, use existing audio files")
    parser.add_argument("--voice", metavar="VOICE", default=None,
                        help="Override TTS voice for all card types. Accepts a Kokoro voice ID or: random, random-american, random-british")
    parser.add_argument("--theme", metavar="THEME", default=None,
                        help="Apply a CSS theme to all card templates. Available: carbon, midnight, void, obsidian, ember, deepsea, nord, ivory")
    parser.add_argument("--force-regen",  action="store_true",
                        help="Regenerate all audio even if files already exist")
    parser.add_argument("--list-types",   action="store_true",
                        help="Print all registered card types for this deck and exit")
    parser.add_argument("--apply-feedback", action="store_true",
                        help="Exclude rejected cards (read from feedback/<deck-slug>/)")
    parser.add_argument("--retire", action="store_true",
                        help="Build a *-retired.apkg from retired_ids.json to tag orphaned cards for deletion")

    args = parser.parse_args()

    bank_path = Path(args.bank).resolve() if args.bank else None

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    elif bank_path:
        output_dir = Path("output").resolve()  # bank mode: default to CWD/output/
    else:
        output_dir = None  # standalone: deck.json path is relative to deck dir

    if bank_path:
        _gen.set_bank_path(bank_path)
        log.info(f"Bank: {bank_path}")

    if args.theme:
        _gen.set_theme(args.theme)
        log.info(f"Theme: {args.theme}")

    # ── Standalone: validate a card type file ──────────────────────────────
    if args.validate_type:
        cmd_validate_type(args.validate_type)
        return

    # ── All other commands need --deck ─────────────────────────────────────
    if not args.deck:
        parser.error("--deck is required (or use --validate-type for standalone validation)")

    deck_path = Path(args.deck)
    if bank_path and not deck_path.is_absolute():
        deck_path = bank_path / deck_path
    deck_dir = deck_path.resolve()

    if not deck_dir.is_dir():
        log.error(f"Deck folder not found: {deck_dir}")
        sys.exit(1)

    log.info(f"Loading deck: {deck_dir}")
    try:
        deck_config = load_deck(deck_dir)
    except (FileNotFoundError, ValueError) as e:
        log.error(f"deck.json error: {e}")
        sys.exit(1)

    log.info(f"  deck  : {deck_config['deck_name']}")
    log.info(f"  types : {list(deck_config['_registry'].keys())}")

    # ── Load retired IDs (used both by --retire and as a safety check) ─────
    retired_ids: list[str] = []
    retired_ids_path = deck_dir / "retired_ids.json"
    if retired_ids_path.exists():
        retired_ids = json.loads(retired_ids_path.read_text(encoding="utf-8"))
        log.info(f"  retired_ids.json: {len(retired_ids)} retired card(s)")

    # ── --retire: build the tag-for-deletion apkg and exit ────────────────
    if args.retire:
        build_retired_deck(deck_config, retired_ids, bank_path=bank_path, output_dir=output_dir)
        return

    # ── List types and exit ────────────────────────────────────────────────
    if args.list_types:
        cmd_list_types(deck_config)
        return

    # ── Load card data ─────────────────────────────────────────────────────
    _skip = {"deck.json", "retired_ids.json"}
    data_files = sorted(f for f in deck_dir.glob("*.json") if f.name not in _skip)
    if not data_files:
        log.error(f"No card data files (*.json) found in {deck_dir}")
        sys.exit(1)

    registry = deck_config["_registry"]
    sections: list[dict] = []
    total = 0

    # Load rejected card IDs if --apply-feedback is set
    rejected: set[str] = set()
    if args.apply_feedback:
        sys.path.insert(0, str(_ROOT / "tools"))
        from feedback_reader import rejected_ids
        deck_slug = deck_dir.name
        rejected = rejected_ids(deck_slug)
        if rejected:
            log.info(f"Feedback: excluding {len(rejected)} rejected card(s)")

    retired_set = set(retired_ids)

    for data_file in data_files:
        try:
            name, cards = load_section(data_file, registry)
        except (ValueError, Exception) as e:
            log.error(f"Error loading {data_file.name}: {e}")
            sys.exit(1)
        if rejected:
            before = len(cards)
            cards = [c for c in cards if c.get("id") not in rejected]
            if len(cards) < before:
                log.info(f"  {data_file.name}: dropped {before - len(cards)} rejected card(s)")
        # Safety check: warn if a live card's ID appears in retired_ids.json
        for card in cards:
            if card.get("id") in retired_set:
                log.warning(
                    f"  {data_file.name}: card '{card['id']}' is in retired_ids.json "
                    f"but still present in the deck — remove it from the JSON or from retired_ids.json"
                )
        sections.append({"name": name, "cards": cards})
        total += len(cards)
        log.info(f"  {data_file.name} → '{name}': {len(cards)} card(s)")

    log.info(f"Total: {total} card(s) across {len(sections)} section(s)")

    if args.dry_run:
        log.info("Dry run complete — nothing written.")
        return

    # ── Audio generation ───────────────────────────────────────────────────
    if not args.skip_audio:
        log.info("--- Audio generation ---")
        generate_audio(sections, registry, force_regen=args.force_regen, voice_override=args.voice)
    else:
        log.info("Skipping audio (--skip-audio)")

    # ── Build deck ─────────────────────────────────────────────────────────
    log.info("--- Building deck ---")
    build_deck(deck_config, sections, bank_path=bank_path, output_dir=output_dir)
    log.info("Done.")


if __name__ == "__main__":
    main()
