#!/usr/bin/env python3
"""
Thin wrapper around the AnkiConnect REST API (localhost:8765).

Requires: Anki open + AnkiConnect plugin installed.
Plugin: https://ankiweb.net/shared/info/2055492159

Usage as a library:
    from tools.anki_connect import AnkiConnect
    ac = AnkiConnect()
    stats = ac.get_cards_info(["abc123", "def456"])

Usage as a CLI (quick diagnostics):
    python3 tools/anki_connect.py --ping
    python3 tools/anki_connect.py --decks
    python3 tools/anki_connect.py --stats-for interview-prep
"""

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


ANKI_CONNECT_URL = "http://localhost:8765"
ANKI_CONNECT_VERSION = 6


class AnkiConnectError(Exception):
    pass


class AnkiConnectUnavailable(AnkiConnectError):
    """Raised when Anki is not open or AnkiConnect is not installed."""


# ---------------------------------------------------------------------------
# Low-level request
# ---------------------------------------------------------------------------

def _request(action: str, **params: Any) -> Any:
    payload = json.dumps({
        "action": action,
        "version": ANKI_CONNECT_VERSION,
        "params": params,
    }).encode()

    try:
        with urllib.request.urlopen(
            urllib.request.Request(ANKI_CONNECT_URL, payload),
            timeout=10,
        ) as resp:
            result = json.loads(resp.read())
    except (urllib.error.URLError, OSError) as exc:
        raise AnkiConnectUnavailable(
            "Cannot reach AnkiConnect. Is Anki open with the AnkiConnect plugin installed?"
        ) from exc

    if result.get("error"):
        raise AnkiConnectError(result["error"])
    return result["result"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class AnkiConnect:
    """Wrapper around AnkiConnect. All methods raise AnkiConnectUnavailable
    if Anki is closed, AnkiConnectError for API-level errors."""

    def ping(self) -> bool:
        """Return True if AnkiConnect is reachable."""
        try:
            _request("version")
            return True
        except AnkiConnectUnavailable:
            return False

    def deck_names(self) -> list[str]:
        """Return all deck names."""
        return _request("deckNames")

    def find_notes(self, query: str) -> list[int]:
        """Return note IDs matching an Anki search query.

        Examples:
            ac.find_notes("deck:interview-prep")
            ac.find_notes("tag:bayesian-inference")
        """
        return _request("findNotes", query=query)

    def get_notes_info(self, note_ids: list[int]) -> list[dict]:
        """Return full note info for the given note IDs.

        Each result dict has: noteId, modelName, tags, fields, cards (card IDs).
        """
        return _request("notesInfo", notes=note_ids)

    def get_cards_info(self, card_ids: list[int]) -> list[dict]:
        """Return review stats for the given card IDs.

        Each result dict has: cardId, due, interval, ease, lapses, reps, etc.
        """
        return _request("cardsInfo", cards=card_ids)

    def deck_stats(self, deck_name: str) -> dict:
        """Return aggregate stats for a deck: total, new, due, learning."""
        results = _request("getDeckStats", decks=[deck_name])
        return results.get(deck_name) or results.get(list(results)[0], {})

    def notes_for_deck(self, deck_name: str) -> list[dict]:
        """Fetch all notes in a deck with their card review stats.

        Returns a list of dicts, each with:
            note_id, guid (from fields if present), tags, fields,
            cards: [{card_id, interval, ease, lapses, reps, due}]
        """
        note_ids = self.find_notes(f"deck:{deck_name}")
        if not note_ids:
            return []
        notes = self.get_notes_info(note_ids)
        all_card_ids = [cid for n in notes for cid in n.get("cards", [])]
        cards_info = {c["cardId"]: c for c in self.get_cards_info(all_card_ids)}

        result = []
        for note in notes:
            result.append({
                "note_id": note["noteId"],
                "tags": note.get("tags", []),
                "fields": {k: v["value"] for k, v in note.get("fields", {}).items()},
                "cards": [
                    {
                        "card_id": cid,
                        "interval": cards_info[cid]["interval"],
                        "ease": cards_info[cid]["factor"],
                        "lapses": cards_info[cid]["lapses"],
                        "reps": cards_info[cid]["reps"],
                        "due": cards_info[cid]["due"],
                    }
                    for cid in note.get("cards", [])
                    if cid in cards_info
                ],
            })
        return result

    def lapsing_notes(self, deck_name: str, min_lapses: int = 3) -> list[dict]:
        """Return notes where at least one card has >= min_lapses lapses.

        Useful for coverage analysis: which concepts is the user struggling with?
        """
        notes = self.notes_for_deck(deck_name)
        return [
            n for n in notes
            if any(c["lapses"] >= min_lapses for c in n["cards"])
        ]

    def add_notes(self, deck_name: str, model_name: str, notes: list[dict]) -> list[int]:
        """Add notes to Anki directly (bypass .apkg import).

        Each note dict: {fields: {field_name: value}, tags: [str], guid: str}
        Returns list of created note IDs (None entries = duplicates skipped).

        NOTE: for the main interview-prep deck, use .apkg import to preserve
        model/template definitions. Use this only for incremental additions
        where the model already exists in Anki.
        """
        anki_notes = [
            {
                "deckName": deck_name,
                "modelName": model_name,
                "fields": n["fields"],
                "tags": n.get("tags", []),
                "options": {"allowDuplicate": False},
                **({"guid": n["guid"]} if n.get("guid") else {}),
            }
            for n in notes
        ]
        return _request("addNotes", notes=anki_notes)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ping", action="store_true", help="Check if AnkiConnect is reachable")
    ap.add_argument("--decks", action="store_true", help="List all deck names")
    ap.add_argument("--stats-for", metavar="DECK", help="Show stats for a deck")
    ap.add_argument("--lapsing", metavar="DECK", help="Show lapsing notes in a deck")
    ap.add_argument("--min-lapses", type=int, default=3, metavar="N")
    args = ap.parse_args()

    ac = AnkiConnect()

    if args.ping:
        ok = ac.ping()
        print("AnkiConnect: reachable ✅" if ok else "AnkiConnect: NOT reachable ❌")
        return

    if args.decks:
        for name in sorted(ac.deck_names()):
            print(f"  {name}")
        return

    if args.stats_for:
        stats = ac.deck_stats(args.stats_for)
        print(json.dumps(stats, indent=2))
        return

    if args.lapsing:
        notes = ac.lapsing_notes(args.lapsing, min_lapses=args.min_lapses)
        print(f"{len(notes)} lapsing notes (>= {args.min_lapses} lapses):")
        for n in notes[:20]:
            front = next(iter(n["fields"].values()), "")[:80]
            lapses = max(c["lapses"] for c in n["cards"])
            print(f"  [{lapses} lapses] {front}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
