#!/usr/bin/env python3
"""
Progress tracker for the card quality pass.
Read-only — reports missing namespaced tags and redundant level tags per file.

Usage:
    python3 tools/migrate_tags.py
    python3 tools/migrate_tags.py --file training-fundamentals.json
"""

import argparse
import glob
import json
from pathlib import Path

DECK_DIR = Path(__file__).parent.parent / "content/decks/interview-prep"
SKIP = {"retired_ids.json", "deck.json"}

REDUNDANT = {"junior", "mid-level", "senior", "level:fundamental", "level:intermediate", "level:advanced"}


def analyse_file(path: Path) -> dict:
    with open(path) as f:
        data = json.load(f)
    cards = data.get("cards", [])
    missing_role = missing_domain = missing_style = redundant = 0
    for card in cards:
        tags = set(card.get("tags", []))
        if not any(t.startswith("role:") for t in tags):
            missing_role += 1
        if not any(t.startswith("domain:") for t in tags):
            missing_domain += 1
        if not any(t.startswith("style:") for t in tags):
            missing_style += 1
        redundant += len(tags & REDUNDANT)
    return {
        "cards": len(cards),
        "missing_role": missing_role,
        "missing_domain": missing_domain,
        "missing_style": missing_style,
        "redundant_tags": redundant,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Check a single file by name (e.g. training-fundamentals.json)")
    args = parser.parse_args()

    if args.file:
        paths = [DECK_DIR / args.file]
    else:
        paths = sorted(
            p for p in DECK_DIR.glob("*.json") if p.name not in SKIP
        )

    col = "{:<40} {:>6} {:>13} {:>15} {:>14} {:>15}"
    header = col.format("File", "Cards", "missing role", "missing domain", "missing style", "redundant tags")
    print(header)
    print("-" * len(header))

    totals = {"cards": 0, "missing_role": 0, "missing_domain": 0, "missing_style": 0, "redundant_tags": 0}

    for path in paths:
        r = analyse_file(path)
        print(col.format(
            path.name,
            r["cards"],
            r["missing_role"],
            r["missing_domain"],
            r["missing_style"],
            r["redundant_tags"],
        ))
        for k in totals:
            totals[k] += r[k]

    if len(paths) > 1:
        print("-" * len(header))
        print(col.format(
            "TOTAL",
            totals["cards"],
            totals["missing_role"],
            totals["missing_domain"],
            totals["missing_style"],
            totals["redundant_tags"],
        ))

        all_done = (
            totals["missing_role"] == 0
            and totals["missing_domain"] == 0
            and totals["missing_style"] == 0
            and totals["redundant_tags"] == 0
        )
        print()
        if all_done:
            print("✓ All cards have namespaced tags and no redundant level tags.")
        else:
            remaining = totals["missing_role"] + totals["missing_domain"] + totals["missing_style"]
            print(f"  {remaining} missing tag slots across {totals['cards']} cards.")
            print(f"  {totals['redundant_tags']} redundant level/role tags to remove.")


if __name__ == "__main__":
    main()
