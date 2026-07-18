"""
Content-hash cache for agent outputs.
Keyed by SHA256 of input text — same content always hits the cache,
regardless of which run or when it was processed.
"""
import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).parent.parent / "cache"


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_agent1(text: str) -> list[dict] | None:
    """Return cached Agent 1 items for this text, or None if not cached."""
    path = _CACHE_DIR / "agent1" / f"{_key(text)}.json"
    if path.exists():
        log.info(f"  cache hit (Agent 1) → {path.name}")
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_agent1(text: str, items: list[dict]) -> None:
    """Save Agent 1 items to cache."""
    dir_ = _CACHE_DIR / "agent1"
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{_key(text)}.json"
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
    log.info(f"  cached (Agent 1) → {path.name}")
