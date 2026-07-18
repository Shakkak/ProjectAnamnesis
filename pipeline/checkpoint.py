"""
Checkpoint system for pipeline resumability.
Manages timestamped output directories, history tracking, and resumption.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from utils import slugify

log = logging.getLogger(__name__)


class RunCheckpoint:
    """Manages a timestamped run directory with checkpoints and history."""

    def __init__(self, base_output_dir: Path, deck_name: str):
        self.base_dir = Path(base_output_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped run directory
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = self.base_dir / f"{timestamp}_{self._slugify(deck_name)}"
        self.run_dir.mkdir(exist_ok=True)

        # Create subdirectories
        self.canvas_dir = self.run_dir / "canvas"
        self.agent1_dir = self.run_dir / "agent1"
        self.agent2_dir = self.run_dir / "agent2"
        self.deck_dir = self.run_dir / "deck"
        self.final_dir = self.run_dir / "final"

        for d in [self.canvas_dir, self.agent1_dir, self.agent2_dir, self.deck_dir, self.final_dir]:
            d.mkdir(exist_ok=True)

        self.history_file = self.run_dir / "history.jsonl"
        self.manifest_file = self.run_dir / "manifest.json"

        # Load or create manifest
        self.manifest = self._load_or_create_manifest(deck_name)

    @staticmethod
    def _slugify(s: str) -> str:
        return slugify(s)

    def _load_or_create_manifest(self, deck_name: str) -> dict:
        """Load existing manifest or create new one."""
        if self.manifest_file.exists():
            return json.loads(self.manifest_file.read_text())

        return {
            "deck_name": deck_name,
            "created": datetime.now().isoformat(),
            "status": "in_progress",
            "steps": {
                "canvas_parsing": None,
                "agent1": None,
                "agent2": None,
                "generation": None,
            },
        }

    def append_history(self, step: str, checkpoint: dict) -> None:
        """Append a checkpoint record to history.jsonl."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            **checkpoint,
        }
        with open(self.history_file, "a") as f:
            f.write(json.dumps(record) + "\n")
        log.info(f"  checkpoint: {step} → {self.history_file.name}")

    def save_canvas_level(self, level: int, nodes_processed: int, text: str) -> None:
        """Save canvas level metadata and raw text chunk."""
        meta_file = self.canvas_dir / f"level_{level:02d}.json"
        meta_file.write_text(
            json.dumps(
                {
                    "level": level,
                    "nodes_processed": nodes_processed,
                    "text_length": len(text),
                    "timestamp": datetime.now().isoformat(),
                },
                indent=2,
            )
        )
        if text:
            text_file = self.canvas_dir / f"level_{level:02d}.txt"
            text_file.write_text(text, encoding="utf-8")
        self.append_history("canvas_level", {"level": level, "nodes": nodes_processed, "chars": len(text)})

    def save_agent1_level_items(self, level: int, items: list[dict]) -> None:
        """Save Agent 1 output for a single canvas level."""
        items_file = self.canvas_dir / f"level_{level:02d}_items.json"
        items_file.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")
        self.append_history("agent1_level", {"level": level, "items": len(items)})
        log.info(f"  level {level:02d}: {len(items)} items → {items_file.name}")

    def is_level_processed(self, level: int) -> bool:
        """Return True if Agent 1 items for this level were already saved."""
        return (self.canvas_dir / f"level_{level:02d}_items.json").exists()

    def load_level_items(self, level: int) -> list[dict]:
        """Load Agent 1 items saved for a canvas level."""
        items_file = self.canvas_dir / f"level_{level:02d}_items.json"
        return json.loads(items_file.read_text()) if items_file.exists() else []

    def save_agent1_output(self, items: list[dict]) -> None:
        """Save Agent 1 enriched learning items and extract question patterns."""
        output_file = self.agent1_dir / "learning_items.json"
        output_file.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")

        # Extract and save question patterns catalog
        patterns = [
            {
                "concept":          item.get("concept", ""),
                "item_type":        item.get("item_type", "definition"),
                "question_pattern": item.get("question_pattern", ""),
                "tags":             item.get("tags", []),
                "difficulty":       item.get("difficulty", "medium"),
            }
            for item in items
            if item.get("question_pattern")
        ]
        if patterns:
            patterns_file = self.agent1_dir / "question_patterns.json"
            patterns_file.write_text(json.dumps(patterns, indent=2, ensure_ascii=False) + "\n")
            log.info(f"  Question patterns → {patterns_file.name} ({len(patterns)} patterns)")

        type_counts = {}
        for item in items:
            t = item.get("item_type", "definition")
            type_counts[t] = type_counts.get(t, 0) + 1
        log.info(f"  Item types: {type_counts}")

        self.manifest["steps"]["agent1"] = datetime.now().isoformat()
        self.append_history("agent1_complete", {"items_count": len(items), "type_counts": type_counts})
        self._save_manifest()
        log.info(f"  Agent 1 output → {output_file.name}")

    def save_agent2_output(self, card_data: dict) -> None:
        """Save Agent 2 card data and metadata."""
        output_file = self.agent2_dir / "card_data.json"
        output_file.write_text(json.dumps(card_data, indent=2, ensure_ascii=False) + "\n")
        self.manifest["steps"]["agent2"] = datetime.now().isoformat()
        self.append_history(
            "agent2_complete",
            {"cards_count": len(card_data.get("cards", [])), "types": card_data.get("types_used", [])},
        )
        self._save_manifest()
        log.info(f"  Agent 2 output → {output_file.name}")

    def save_deck_files(self, deck_json: dict, section_file_data: dict, section_filename: str) -> None:
        """Save deck.json and section files."""
        deck_file = self.deck_dir / "deck.json"
        section_file = self.deck_dir / section_filename

        deck_file.write_text(json.dumps(deck_json, indent=2, ensure_ascii=False) + "\n")
        section_file.write_text(json.dumps(section_file_data, indent=2, ensure_ascii=False) + "\n")

        self.append_history("deck_files_written", {"deck_file": "deck.json", "section_file": section_filename})
        log.info(f"  Deck files → {self.deck_dir.name}/")

    def save_final_apkg(self, apkg_path: Path) -> None:
        """Copy final .apkg to run directory."""
        final_apkg = self.final_dir / apkg_path.name
        import shutil
        shutil.copy2(apkg_path, final_apkg)
        self.manifest["steps"]["generation"] = datetime.now().isoformat()
        self.manifest["status"] = "complete"
        self.manifest["final_deck"] = str(final_apkg)
        self._save_manifest()
        self.append_history("generation_complete", {"apkg": apkg_path.name, "size_kb": final_apkg.stat().st_size / 1024})
        log.info(f"  Final deck → {final_apkg.name}")

    def _save_manifest(self) -> None:
        """Save manifest.json."""
        self.manifest_file.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False) + "\n")

    def get_status(self) -> str:
        """Return human-readable run status."""
        return f"{self.run_dir.name} — {self.manifest['status']}"

    def load_last_checkpoint(self) -> dict | None:
        """Load the last checkpoint record from history."""
        if not self.history_file.exists():
            return None
        lines = self.history_file.read_text().strip().split("\n")
        if not lines:
            return None
        return json.loads(lines[-1])
