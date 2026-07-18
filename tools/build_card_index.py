"""
Build card_index.json — two views of concept/section coverage.

by_concept: for each vault slug, which sections cover it, card count, has_hands_on
by_section: for each deck section, covered concepts and uncovered vault concepts
"""
import argparse
import json
import glob
import os
from pathlib import Path

_ROOT = Path(__file__).parent.parent

HANDS_ON_TAGS = {"derivation", "application", "proof", "algebraic-derivation", "paper"}


def is_hands_on(card):
    tags = set(card.get("tags", []))
    if tags & HANDS_ON_TAGS:
        return True
    if card.get("question", "").startswith("[Paper]"):
        return True
    return False


def load_sections(deck_dir: str):
    """Return list of (section_name, cards) from all section JSON files."""
    files = sorted(glob.glob(os.path.join(deck_dir, "*.json")))
    sections = []
    for path in files:
        if os.path.basename(path) in ("deck.json", "card_index.json", "retired_ids.json"):
            continue
        with open(path) as f:
            data = json.load(f)
        sections.append((data["name"], data.get("cards", [])))
    return sections


def load_vault_slugs(vault_index: str):
    """Return set of all vault concept slugs (filename without .md)."""
    with open(vault_index) as f:
        index = json.load(f)
    return {path.split("/")[-1].replace(".md", "") for path in index}


def build_by_concept(sections):
    """{ slug: {sections, card_count, has_hands_on, missing_types} }"""
    by_concept = {}
    for section_name, cards in sections:
        for card in cards:
            for slug in card.get("source_nodes", []):
                if slug not in by_concept:
                    by_concept[slug] = {
                        "sections": [],
                        "card_count": 0,
                        "has_hands_on": False,
                        "missing_types": [],
                    }
                entry = by_concept[slug]
                if section_name not in entry["sections"]:
                    entry["sections"].append(section_name)
                entry["card_count"] += 1
                if is_hands_on(card):
                    entry["has_hands_on"] = True
    return by_concept


def compute_missing_types(entry):
    """Flag if hands-on coverage is absent."""
    missing = []
    if not entry["has_hands_on"]:
        missing.append("hands-on")
    return missing


def build_by_section(sections, vault_slugs, by_concept):
    """{ section_name: {covered_concepts, uncovered_vault_concepts} }"""
    by_section = {}
    for section_name, cards in sections:
        covered = set()
        for card in cards:
            covered.update(card.get("source_nodes", []))
        covered_vault = covered & vault_slugs
        by_section[section_name] = {
            "covered_concepts": sorted(covered_vault),
            "uncovered_vault_concepts": [],  # filled below
        }

    # For each section, find vault concepts not covered by any card in that section
    # (vault concepts that exist but have no card with source_nodes pointing to them in this section)
    for section_name, entry in by_section.items():
        covered_set = set(entry["covered_concepts"])
        # uncovered = vault slugs that appear in by_concept but not in this section's coverage
        uncovered = []
        for slug in vault_slugs:
            if slug in by_concept and section_name in by_concept[slug]["sections"]:
                continue  # covered in this section
            # only flag if the slug has no cards at all (truly missing from deck)
        # Actually per spec: "which vault concepts are absent" from this section
        # means vault concepts that are NOT covered by any card in this section
        entry["uncovered_vault_concepts"] = sorted(vault_slugs - covered_set)

    return by_section


def main():
    parser = argparse.ArgumentParser(description="Build vault/card_index.json")
    parser.add_argument("--bank", metavar="PATH",
                        default=os.environ.get("BANK_PATH"),
                        help="External data root (default: content/ in this repo)")
    args = parser.parse_args()

    bank = Path(args.bank).resolve() if args.bank else _ROOT / "content"
    deck_dir    = str(bank / "decks" / "interview-prep")
    vault_index = str(bank / "vault" / "index.json")
    output      = str(bank / "vault" / "card_index.json")

    sections = load_sections(deck_dir)
    vault_slugs = load_vault_slugs(vault_index)

    by_concept = build_by_concept(sections)

    # Fill missing_types
    for entry in by_concept.values():
        entry["missing_types"] = compute_missing_types(entry)

    by_section = build_by_section(sections, vault_slugs, by_concept)

    # Also note vault slugs with zero cards
    zero_card_slugs = sorted(vault_slugs - set(by_concept.keys()))

    index = {
        "by_concept": by_concept,
        "by_section": by_section,
        "vault_slugs_without_cards": zero_card_slugs,
    }

    with open(output, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Wrote {output}")
    print(f"  Concepts with cards:    {len(by_concept)}")
    print(f"  Concepts without cards: {len(zero_card_slugs)}")
    print(f"  Sections indexed:       {len(by_section)}")


if __name__ == "__main__":
    main()
