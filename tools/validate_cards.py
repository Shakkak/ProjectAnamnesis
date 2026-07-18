#!/usr/bin/env python3
"""
Card validator — checks all JSON card files in content/decks/interview-prep/.

Checks per card:
  FAIL — source_nodes empty
  FAIL — level not in {fundamental, intermediate, advanced}
  FAIL — card_type is not "reveal"
  WARN — source_nodes contains slugs not found in vault
  WARN — missing namespaced tags (role: / domain: / style:)
  WARN — answer is very short (< 40 chars — likely empty/placeholder)
  WARN — steps is very short (< 80 chars — thin, restates answer)
  WARN — legacy level tags present (junior, senior, mid-level, level:*)

Exit codes: 0 = pass (warnings allowed), 1 = one or more failures.

Usage:
  python3 tools/validate_cards.py
  python3 tools/validate_cards.py content/decks/interview-prep/transformers-attention.json
"""
import json
import sys
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
_DECKS    = _ROOT / "content" / "decks" / "interview-prep"
_VAULT    = _ROOT / "content" / "vault" / "index.json"

_VALID_LEVELS = {"fundamental", "intermediate", "advanced"}
_LEGACY_LEVEL_TAGS = {"junior", "mid-level", "senior", "paper"}
_REQUIRED_NAMESPACES = ("role:", "domain:", "style:")


def _load_vault_slugs() -> set[str]:
    if not _VAULT.exists():
        return set()
    idx = json.loads(_VAULT.read_text(encoding="utf-8"))
    return {path.split("/")[-1].replace(".md", "") for path in idx}


def validate_card(card: dict, idx: int, vault_slugs: set[str]) -> list[tuple[str, str]]:
    """Return list of (level, message). level is 'FAIL' or 'WARN'."""
    issues: list[tuple[str, str]] = []
    q = card.get("question", "")[:70]

    # card_type
    if card.get("card_type") != "reveal":
        issues.append(("FAIL", f"card_type={repr(card.get('card_type'))} — must be 'reveal'"))

    # level
    level = card.get("level", "")
    if level not in _VALID_LEVELS:
        issues.append(("FAIL", f"level={repr(level)} — must be fundamental/intermediate/advanced"))

    # source_nodes
    source_nodes = card.get("source_nodes", [])
    if not source_nodes:
        issues.append(("FAIL", "source_nodes is empty"))
    elif vault_slugs:
        bad = [s for s in source_nodes if s not in vault_slugs]
        if bad:
            issues.append(("WARN", f"unknown source_nodes slugs: {bad}"))

    # namespaced tags
    tags = card.get("tags", [])
    missing_ns = [ns for ns in _REQUIRED_NAMESPACES if not any(t.startswith(ns) for t in tags)]
    if missing_ns:
        issues.append(("WARN", f"missing namespaced tags: {missing_ns}"))

    # legacy level tags
    legacy = [t for t in tags if t in _LEGACY_LEVEL_TAGS or t.startswith("level:")]
    if legacy:
        issues.append(("WARN", f"legacy tags to remove: {legacy}"))

    # field length
    answer = card.get("answer", "")
    if len(answer.strip()) < 40:
        issues.append(("WARN", f"answer very short ({len(answer)} chars) — likely placeholder"))

    steps = card.get("steps", "")
    if len(steps.strip()) < 80:
        issues.append(("WARN", f"steps very short ({len(steps)} chars) — may be thin"))

    return issues


def validate_file(path: Path, vault_slugs: set[str]) -> tuple[int, int]:
    """Validate one section JSON file. Returns (fail_count, warn_count)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    section = data.get("name", path.stem)

    fails = 0
    warns = 0
    file_header_printed = False

    for i, card in enumerate(cards):
        issues = validate_card(card, i, vault_slugs)
        if not issues:
            continue
        if not file_header_printed:
            print(f"\n{path.name}  ({section}, {len(cards)} cards)")
            file_header_printed = True
        q = card.get("question", "")[:72]
        print(f"  card {i + 1:>3}: {q!r}")
        for level, msg in issues:
            print(f"           {level:<4}  {msg}")
            if level == "FAIL":
                fails += 1
            else:
                warns += 1

    return fails, warns


def main(paths: list[Path] | None = None) -> int:
    vault_slugs = _load_vault_slugs()
    if not vault_slugs:
        print("WARN  vault/index.json not found — source_nodes slug verification skipped")

    if paths is None:
        paths = sorted(
            p for p in _DECKS.glob("*.json")
            if p.name not in {"deck.json", "retired_ids.json"}
        )

    total_cards = 0
    total_fails = 0
    total_warns = 0

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"\n{path.name}  ERROR: {e}")
            total_fails += 1
            continue
        total_cards += len(data.get("cards", []))
        f, w = validate_file(path, vault_slugs)
        total_fails += f
        total_warns += w

    print(f"\n── Summary {'─' * 40}")
    print(f"   files   : {len(paths)}")
    print(f"   cards   : {total_cards}")
    print(f"   failures: {total_fails}")
    print(f"   warnings: {total_warns}")
    if total_fails == 0:
        print("   result  : PASS")
    else:
        print("   result  : FAIL")
    return 1 if total_fails else 0


if __name__ == "__main__":
    target_paths = [Path(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else None
    sys.exit(main(target_paths))
