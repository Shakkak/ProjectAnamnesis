"""Read and write card review feedback."""

import json
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FEEDBACK_DIR = PROJECT_ROOT / "feedback"


def _path(deck: str, card_id: str) -> Path:
    return FEEDBACK_DIR / deck / f"{card_id}.json"


def save(deck: str, card_id: str, action: str, comment: str = "") -> None:
    """Save a review decision. Appends — never overwrites prior decisions."""
    p = _path(deck, card_id)
    p.parent.mkdir(parents=True, exist_ok=True)

    history = []
    if p.exists():
        history = json.loads(p.read_text()).get("history", [])

    history.append({
        "action": action,           # "accepted" | "rejected" | "skipped"
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    p.write_text(json.dumps({
        "card_id": card_id,
        "deck": deck,
        "latest": action,
        "history": history,
    }, indent=2))


def get(deck: str, card_id: str) -> dict | None:
    """Return latest feedback for a card, or None if not yet reviewed."""
    p = _path(deck, card_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def get_all(deck: str) -> dict[str, dict]:
    """Return {card_id: feedback} for all reviewed cards in a deck."""
    deck_dir = FEEDBACK_DIR / deck
    if not deck_dir.exists():
        return {}
    return {
        p.stem: json.loads(p.read_text())
        for p in deck_dir.glob("*.json")
    }


def status(deck: str, card_id: str) -> str:
    """Return 'accepted', 'rejected', 'skipped', or 'pending'."""
    fb = get(deck, card_id)
    return fb["latest"] if fb else "pending"


def summary(deck: str, cards: list[dict]) -> dict:
    all_fb = get_all(deck)
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "skipped": 0}
    for card in cards:
        fb = all_fb.get(card["_id"])
        counts[fb["latest"] if fb else "pending"] += 1
    return counts
