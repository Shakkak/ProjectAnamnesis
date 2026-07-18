#!/usr/bin/env python3
"""
Prune accumulated output/ and cache/ directories.

Usage:
  python3 tools/prune.py outputs --keep 5      # keep 5 most recent runs per deck
  python3 tools/prune.py cache --days 30       # delete cache entries older than 30 days
  python3 tools/prune.py outputs --keep 5 --dry-run
  python3 tools/prune.py cache --days 30 --dry-run
"""
import argparse
import time
from pathlib import Path

_ROOT    = Path(__file__).parent.parent
_OUTPUTS = _ROOT / "output"
_CACHE   = _ROOT / "cache" / "agent1"


def cmd_outputs(keep: int, dry_run: bool) -> None:
    if not _OUTPUTS.exists():
        print("output/ does not exist — nothing to do")
        return

    # Group run dirs by deck slug (suffix after first underscore-separated date)
    runs = sorted(_OUTPUTS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = [r for r in runs if r.is_dir()]

    # Group by deck slug: dir names are YYYY-MM-DD_HH-MM-SS_<slug>
    by_deck: dict[str, list[Path]] = {}
    for r in runs:
        parts = r.name.split("_", 3)
        slug = parts[3] if len(parts) > 3 else r.name
        by_deck.setdefault(slug, []).append(r)

    deleted = 0
    for slug, deck_runs in by_deck.items():
        to_delete = deck_runs[keep:]
        for run_dir in to_delete:
            print(f"{'[dry-run] ' if dry_run else ''}delete {run_dir.name}")
            if not dry_run:
                import shutil
                shutil.rmtree(run_dir)
            deleted += 1

    print(f"\n{'Would delete' if dry_run else 'Deleted'} {deleted} run dir(s) across {len(by_deck)} deck(s)")


def cmd_cache(days: int, dry_run: bool) -> None:
    if not _CACHE.exists():
        print("cache/agent1/ does not exist — nothing to do")
        return

    cutoff = time.time() - days * 86400
    deleted = 0
    for f in _CACHE.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            age_days = (time.time() - f.stat().st_mtime) / 86400
            print(f"{'[dry-run] ' if dry_run else ''}delete {f.name}  ({age_days:.0f}d old)")
            if not dry_run:
                f.unlink()
            deleted += 1

    print(f"\n{'Would delete' if dry_run else 'Deleted'} {deleted} cache file(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune output/ and cache/ directories")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_out = sub.add_parser("outputs", help="Prune output/ run directories")
    p_out.add_argument("--keep",    type=int, default=5, help="Keep N most recent runs per deck (default: 5)")
    p_out.add_argument("--dry-run", action="store_true")

    p_cache = sub.add_parser("cache", help="Prune cache/agent1/ by age")
    p_cache.add_argument("--days",   type=int, default=30, help="Delete entries older than N days (default: 30)")
    p_cache.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.cmd == "outputs":
        cmd_outputs(args.keep, args.dry_run)
    else:
        cmd_cache(args.days, args.dry_run)


if __name__ == "__main__":
    main()
