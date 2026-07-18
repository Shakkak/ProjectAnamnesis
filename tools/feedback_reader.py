"""
Read feedback files and produce structured summaries for two consumers:

  1. generator/main.py  — needs rejected_ids() to filter cards from deck builds
  2. pipeline/pipeline.py — needs comments_by_section() to inject into Agent 2 prompt
"""
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_FEEDBACK_DIR = _ROOT / "feedback"
_DECKS_DIR = _ROOT / "content" / "decks"


def _feedback_dir(deck_slug: str) -> Path:
    return _FEEDBACK_DIR / deck_slug


def rejected_ids(deck_slug: str) -> set[str]:
    """Return the set of card IDs with 'rejected' status."""
    fb_dir = _feedback_dir(deck_slug)
    if not fb_dir.exists():
        return set()
    result = set()
    for path in fb_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            if data.get("latest") == "rejected":
                result.add(path.stem)
        except Exception:
            pass
    return result


def _load_card_index(deck_dir: Path) -> dict[str, dict]:
    """Build {card_id: card_data} index from all section files in a deck dir."""
    index: dict[str, dict] = {}
    for path in sorted(deck_dir.glob("*.json")):
        if path.name == "deck.json":
            continue
        try:
            raw = json.loads(path.read_text())
            cards = raw if isinstance(raw, list) else raw.get("cards", [])
            section = raw.get("name", path.stem) if isinstance(raw, dict) else path.stem
            for card in cards:
                cid = card.get("id")
                if cid:
                    index[cid] = {**card, "_section": section}
        except Exception:
            pass
    return index


def comments_by_concept(deck_slug: str) -> dict[str, list[str]]:
    """
    Group rejected card comments by source_nodes concept slug.
    Returns {concept_slug: [comment, ...]} — empty comments excluded.
    """
    fb_dir = _feedback_dir(deck_slug)
    if not fb_dir.exists():
        return {}

    deck_dir = _DECKS_DIR / deck_slug
    card_index = _load_card_index(deck_dir) if deck_dir.exists() else {}

    result: dict[str, list[str]] = {}
    for path in fb_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("latest") != "rejected":
            continue

        comment = ""
        for entry in reversed(data.get("history", [])):
            if entry.get("action") == "rejected" and entry.get("comment", "").strip():
                comment = entry["comment"].strip()
                break
        if not comment:
            continue

        card = card_index.get(path.stem, {})
        concepts = card.get("source_nodes") or []
        if not concepts:
            concepts = ["_unknown"]
        for concept in concepts:
            result.setdefault(concept, []).append(comment)

    return result


def comments_by_section(deck_slug: str) -> dict[str, list[str]]:
    """
    Group rejected card comments by section name.
    Returns {section_name: [comment, ...]} — empty comments excluded.
    """
    fb_dir = _feedback_dir(deck_slug)
    if not fb_dir.exists():
        return {}

    deck_dir = _DECKS_DIR / deck_slug
    card_index = _load_card_index(deck_dir) if deck_dir.exists() else {}

    result: dict[str, list[str]] = {}
    for path in fb_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("latest") != "rejected":
            continue

        comment = ""
        for entry in reversed(data.get("history", [])):
            if entry.get("action") == "rejected" and entry.get("comment", "").strip():
                comment = entry["comment"].strip()
                break
        if not comment:
            continue

        card = card_index.get(path.stem, {})
        section = card.get("_section", "_unknown")
        result.setdefault(section, []).append(comment)

    return result


def summary(deck_slug: str) -> None:
    """Print a human-readable feedback summary for a deck."""
    fb_dir = _feedback_dir(deck_slug)
    if not fb_dir.exists():
        print(f"No feedback found for deck '{deck_slug}'")
        return

    counts: dict[str, int] = {}
    for path in fb_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            status = data.get("latest", "unknown")
            counts[status] = counts.get(status, 0) + 1
        except Exception:
            pass

    total = sum(counts.values())
    print(f"\nFeedback summary — {deck_slug} ({total} cards reviewed)")
    for status, n in sorted(counts.items()):
        print(f"  {status:10} {n}")

    by_concept = comments_by_concept(deck_slug)
    if by_concept:
        print(f"\nRejected cards with comments ({sum(len(v) for v in by_concept.values())} total):")
        for concept, comments in sorted(by_concept.items()):
            print(f"  [{concept}]")
            for c in comments:
                print(f"    - {c[:120]}")


if __name__ == "__main__":
    import sys
    deck = sys.argv[1] if len(sys.argv) > 1 else "interview-prep"
    summary(deck)
