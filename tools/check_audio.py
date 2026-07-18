#!/usr/bin/env python3
"""
Scan a deck folder and report missing audio_override files.

Reads deck.json to find card types that have audio_override fields, then checks
every card in the deck to confirm the referenced file exists in media/.

Usage:
    python3 tools/check_audio.py content/decks/english/
    python3 tools/check_audio.py content/decks/speaking/
    python3 tools/check_audio.py          # scans all decks under content/decks/

Exit code 1 if any files are missing.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _override_fields(deck_dir: Path) -> dict[str, list[str]]:
    """Return {ct_id: [audio_override_field_names]} for the deck."""
    deck_json = json.loads((deck_dir / "deck.json").read_text())
    result = {}
    for entry in deck_json.get("types", []):
        ct_path = (deck_dir / entry["definition"]).resolve()
        ct_def = json.loads(ct_path.read_text())
        fields = [
            fd["name"] for fd in ct_def.get("fields", [])
            if fd.get("role") == "audio_override"
        ]
        result[entry["id"]] = fields
    return result


def check_deck(deck_dir: Path) -> int:
    """Check one deck. Returns count of missing audio files."""
    if not (deck_dir / "deck.json").exists():
        return 0

    registry = _override_fields(deck_dir)
    if not any(registry.values()):
        return 0  # no card type in this deck uses audio_override

    media_dir = deck_dir / "media"
    missing = []
    present = 0

    for path in sorted(deck_dir.glob("*.json")):
        if path.name in ("deck.json", "retired_ids.json"):
            continue
        data = json.loads(path.read_text())
        cards = data if isinstance(data, list) else data.get("cards", [])
        for card in cards:
            ct_id = card.get("card_type", "")
            for field in registry.get(ct_id, []):
                value = card.get(field, "").strip()
                if not value:
                    continue
                if (media_dir / value).exists():
                    present += 1
                else:
                    answer = str(card.get("answer", "")).split(";")[0].strip()
                    missing.append((path.name, value, answer))

    total = present + len(missing)
    if not total:
        return 0

    if missing:
        print(f"\n{deck_dir.name}: {len(missing)}/{total} audio files MISSING")
        for fname, audio_file, answer in missing[:40]:
            print(f"  {audio_file:40}  answer={answer!r}  [{fname}]")
        if len(missing) > 40:
            print(f"  ... and {len(missing) - 40} more")
    else:
        print(f"{deck_dir.name}: {total} audio file(s) — all present")

    return len(missing)


def main() -> None:
    if len(sys.argv) > 1:
        decks = [Path(sys.argv[1])]
    else:
        decks_root = ROOT / "content" / "decks"
        if not decks_root.exists():
            print(f"No decks directory found at {decks_root}")
            sys.exit(0)
        decks = sorted(decks_root.iterdir())

    total_missing = 0
    for deck_dir in decks:
        if deck_dir.is_dir():
            total_missing += check_deck(deck_dir)

    if total_missing:
        print(f"\nTotal: {total_missing} missing audio file(s).")
        sys.exit(1)
    else:
        print("\nAll audio files present.")


if __name__ == "__main__":
    main()
