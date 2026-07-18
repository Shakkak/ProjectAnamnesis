#!/usr/bin/env python3
"""
Vault coverage tool — two modes via --mode flag.

  table    (default) Human-readable table of all concepts sorted by coverage gap.
  analyze  Priority ranking for card generation, with scoring + optional AnkiConnect.

Sources: vault/index.json, vault/card_index.json, vault/**/*.md (for related: links).

Usage:
  python3 tools/coverage.py
  python3 tools/coverage.py --mode analyze
  python3 tools/coverage.py --mode analyze --anki
  python3 tools/coverage.py --mode analyze --top 20
  python3 tools/coverage.py --mode table --folder training
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

_HANDSON_TAGS = {"derivation", "application", "proof", "algebraic-derivation", "paper"}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_RELATED_RE     = re.compile(r"related:\s*\[([^\]]*)\]")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_indexes(vault: Path) -> tuple[dict, dict]:
    """Return (vault_index, card_index)."""
    vault_idx = json.loads((vault / "index.json").read_text())
    card_idx  = json.loads((vault / "card_index.json").read_text())
    return vault_idx, card_idx


def _related_from_vault(vault: Path) -> dict[str, list[str]]:
    """Parse `related:` frontmatter from each vault .md → {slug: [related_slugs]}."""
    result: dict[str, list[str]] = {}
    for md in vault.rglob("*.md"):
        slug = md.stem
        text = md.read_text(errors="ignore")
        m = _FRONTMATTER_RE.match(text)
        if not m:
            result[slug] = []
            continue
        fm = m.group(1)
        rm = _RELATED_RE.search(fm)
        if rm:
            related = [s.strip() for s in rm.group(1).split(",") if s.strip()]
        else:
            related = []
        result[slug] = related
    return result


def _reference_counts(related_map: dict[str, list[str]]) -> dict[str, int]:
    """Count how many concepts reference each slug via related:."""
    counts: dict[str, int] = {}
    for refs in related_map.values():
        for slug in refs:
            counts[slug] = counts.get(slug, 0) + 1
    return counts


def _lapsing_by_concept(vault_slugs: set[str]) -> dict[str, int]:
    """Return {slug: lapse_count} from AnkiConnect; empty dict if unavailable."""
    try:
        sys.path.insert(0, str(_ROOT / "tools"))
        from anki_connect import AnkiConnect
        ac = AnkiConnect()
        if not ac.ping():
            return {}
        lapsing = ac.lapsing_notes("interview-prep")
    except Exception:
        return {}

    counts: dict[str, int] = {}
    for note in lapsing:
        for tag in note.get("tags", []):
            slug = tag.replace(" ", "-").lower()
            if slug in vault_slugs:
                counts[slug] = counts.get(slug, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Table mode
# ---------------------------------------------------------------------------

def cmd_table(vault_idx: dict, card_idx: dict, folder_filter: str | None) -> None:
    by_concept = card_idx["by_concept"]

    vault_meta: dict[str, tuple[str, int]] = {}
    for path, data in vault_idx.items():
        parts = path.split("/")
        fldr  = parts[0] if len(parts) > 1 else "."
        slug  = parts[-1].replace(".md", "")
        n_sec = sum(1 for s in data.get("sections", []) if s["level"] == 2)
        vault_meta[slug] = (fldr, n_sec)

    all_slugs = set(vault_meta) | set(by_concept)

    rows = []
    for slug in all_slugs:
        fldr, vsecs = vault_meta.get(slug, ("(no vault)", 0))
        if folder_filter and fldr != folder_filter:
            continue
        entry = by_concept.get(slug)
        if entry:
            n_cards  = entry["card_count"]
            has_ho   = entry["has_hands_on"]
            missing  = entry["missing_types"]
        else:
            n_cards, has_ho, missing = 0, False, ["hands-on"]

        # gap score: higher = more urgent
        score = (100 if n_cards == 0 else max(0, 10 - n_cards)) + (5 if not has_ho else 0)
        rows.append((score, slug, fldr, n_cards, has_ho, vsecs, missing))

    rows.sort(key=lambda r: (-r[0], r[1]))

    hdr = f"{'concept':<40} {'folder':<20} {'cards':>5} {'hands-on':>8} {'§vault':>6}  missing"
    print(hdr)
    print("-" * len(hdr))
    for _, slug, fldr, cards, ho, vsecs, missing in rows:
        miss_str = ", ".join(missing) if missing else "-"
        print(f"{slug:<40} {fldr:<20} {cards:>5} {'yes' if ho else 'no':>8} {vsecs:>6}  {miss_str}")

    zero = card_idx["vault_slugs_without_cards"]
    print(f"\nTotal vault concepts:         {len(vault_meta)}")
    print(f"Concepts with cards:          {len(by_concept)}")
    print(f"Concepts with zero cards:     {len(zero)}")
    print(f"Concepts with hands-on cards: {sum(1 for e in by_concept.values() if e['has_hands_on'])}")


# ---------------------------------------------------------------------------
# Analyze mode
# ---------------------------------------------------------------------------

def cmd_analyze(vault_idx: dict, card_idx: dict, top: int, use_anki: bool, vault: Path) -> None:
    by_concept  = card_idx["by_concept"]
    vault_slugs = {path.split("/")[-1].replace(".md", "") for path in vault_idx}

    related_map = _related_from_vault(vault)
    ref_counts  = _reference_counts(related_map)
    lapsing     = _lapsing_by_concept(vault_slugs) if use_anki else {}

    rows: list[dict] = []
    for path, vdata in vault_idx.items():
        slug  = path.split("/")[-1].replace(".md", "")
        title = vdata.get("title", slug)
        entry = by_concept.get(slug)

        n_cards  = entry["card_count"] if entry else 0
        has_ho   = entry["has_hands_on"] if entry else False
        refs     = ref_counts.get(slug, 0)
        lapse_ct = lapsing.get(slug, 0)

        score   = 0
        reasons = []

        if n_cards == 0:
            score += 100
            reasons.append("0 cards")
        else:
            if not has_ho:
                score += 40
                reasons.append("no hands-on card")
            if n_cards < 3:
                score += 20
                reasons.append(f"only {n_cards} card(s)")

        score += min(refs * 5, 30)
        if refs >= 3:
            reasons.append(f"referenced by {refs} concepts")

        score += lapse_ct * 10
        if lapse_ct:
            reasons.append(f"{lapse_ct} lapsing")

        rows.append({
            "slug": slug, "title": title, "score": score,
            "n_cards": n_cards, "refs": refs, "lapsing": lapse_ct,
            "reasons": reasons,
        })

    rows.sort(key=lambda r: (-r["score"], r["slug"]))
    if top:
        rows = rows[:top]

    print(f"Coverage analysis — {len(vault_idx)} concepts\n")
    print(f"  0 cards         : {sum(1 for r in rows if r['n_cards'] == 0)}")
    print(f"  no hands-on     : {sum(1 for r in rows if r['n_cards'] > 0 and 'no hands-on card' in r['reasons'])}")
    if use_anki and lapsing:
        print(f"  lapsing concepts: {len(lapsing)}")

    print(f"\n{'#':<5} {'Score':<6} {'Cards':<6} {'Refs':<5} {'Concept':<40} Reasons")
    print("─" * 95)
    for i, r in enumerate(rows, 1):
        print(f"{i:<5} {r['score']:<6} {r['n_cards']:<6} {r['refs']:<5} {r['slug']:<40} {', '.join(r['reasons']) or '—'}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Vault coverage tool")
    parser.add_argument("--bank", metavar="PATH",
                        default=os.environ.get("BANK_PATH"),
                        help="External data root (default: content/ in this repo)")
    parser.add_argument("--mode",   choices=["table", "analyze"], default="table")
    parser.add_argument("--folder", help="Filter table mode by vault subfolder (e.g. training)")
    parser.add_argument("--anki",   action="store_true", help="Include lapsing data from AnkiConnect")
    parser.add_argument("--top",    type=int, default=0, metavar="N", help="Show top N (analyze mode)")
    args = parser.parse_args()

    bank  = Path(args.bank).resolve() if args.bank else _ROOT / "content"
    vault = bank / "vault"

    vault_idx, card_idx = _load_indexes(vault)

    if args.mode == "table":
        cmd_table(vault_idx, card_idx, args.folder)
    else:
        cmd_analyze(vault_idx, card_idx, args.top, args.anki, vault)


if __name__ == "__main__":
    main()
