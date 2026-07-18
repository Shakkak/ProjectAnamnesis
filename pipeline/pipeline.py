#!/usr/bin/env python3
"""
Agent pipeline: learning material or instructions → Anki .apkg

Input modes:
  File mode        — provide an input file; markitdown converts non-text formats automatically
    ./cli.sh pipeline --input input/notes.md        --deck-name "Biology Ch1"
    ./cli.sh pipeline --input input/slides.pdf      --deck-name "Lecture 3"
    ./cli.sh pipeline --input input/report.docx     --deck-name "Research Paper"
    ./cli.sh pipeline --input input/overview.canvas --vault input/vault/ --deck-name "Stats 110"

  Directory mode   — provide a folder; each file processed independently then grouped into deck(s)
    ./cli.sh pipeline --input-dir input/lectures/   --deck-name "Biology Course"

  Instruction mode — describe the deck you want; agents build knowledge from scratch
    ./cli.sh pipeline --prompt "Build 30 cards on gradient descent for a junior ML engineer." --deck-name "Gradient Descent"

New flags:
    --spec PATH             Load Deck Spec JSON from file, skip Agent 0 (clarification)
    --skip-clarification    Skip Agent 0 entirely (use a minimal spec inferred from args)
    --skip-preview          Skip the 2-card preview loop
    --skip-review           Skip Agent 4 (quality reviewer)

Common flags:
    --section "Chapter 1"     sub-deck name (defaults to filename stem or 'Main')
    --provider anthropic       LLM provider: openai | anthropic | gemini
    --model claude-opus-4-8    model override
    --list-providers           print available providers/models and exit
    --skip-audio               pass --skip-audio to generator
    --skip-generate            write JSON only, don't build .apkg
    --save-intermediate        dump Agent 1 JSON for debugging
"""
import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from client_factory import build_client, list_providers
from input_parser import parse_file
from canvas_parser import parse_canvas, parse_canvas_levels
from agents.clarification.agent import run_clarification
from agents.data_provider.agent import (
    extract_learning_items, generate_learning_items,
    detect_domain, build_system_prompt,
)
from agents.deck_designer.agent import design_deck
from agents.structure_decider.agent import build_card_data, write_sample_cards
from agents.quality_reviewer.agent import review_cards
from preview import generate_preview
from cache import get_agent1, save_agent1
from checkpoint import RunCheckpoint
from utils import slugify as _slugify

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from feedback_reader import comments_by_section as _feedback_by_section

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

_ROOT        = Path(__file__).parent.parent
_CARD_TYPES  = _ROOT / "content" / "card_types"
_VAULT_INDEX = _ROOT / "content" / "vault" / "index.json"
_TEMPLATE_DIR = _ROOT / "generator" / "templates"

_TYPE_FILES = {
    "reveal": "reveal.json",
    "qa":     "typing_qa.json",
    "mc":     "multiple_choice.json",
    "cloze":  "cloze.json",
}

_SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".epub", ".ipynb"}

_ORGANIZER_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":         {"type": "string"},
                    "file_indices": {"type": "array", "items": {"type": "integer"}},
                    "rationale":    {"type": "string"},
                },
                "required": ["name", "file_indices", "rationale"],
            },
        }
    },
    "required": ["groups"],
}

_ORGANIZER_SYSTEM = """\
You are given a set of files that have been processed into learning items.
Decide how to group them into Anki decks.

Rules:
- Files on the same topic or part of the same course should be merged into one deck \
(they will become sections within that deck).
- Files on clearly different topics or different formats (e.g., lecture notes vs. problem sets) \
should be separate decks.
- If unsure, prefer fewer decks.
- Every file must appear in exactly one group.
- Use the provided deck name hint as a base. For one group, use the name as-is. \
For multiple groups, give each a descriptive subtitle.

Return a JSON object with a "groups" array. Each group has:
  name          — the deck name for this group
  file_indices  — list of integer indices of the files that belong to this deck
  rationale     — one sentence explaining the grouping decision
"""


def _load_vault_slugs() -> list[str]:
    if not _VAULT_INDEX.exists():
        return []
    idx = json.loads(_VAULT_INDEX.read_text(encoding="utf-8"))
    return sorted({path.split("/")[-1].replace(".md", "") for path in idx})


class Progress:
    def __init__(self, total_levels: int, total_items: int = 0):
        self.total_levels  = total_levels
        self.total_items   = total_items
        self.done_levels   = 0
        self.failed_levels = 0
        self.items_so_far  = 0

    def level_done(self, level: int, n_items: int, cached: bool = False) -> None:
        self.done_levels  += 1
        self.items_so_far += n_items
        src = "cache" if cached else "API"
        bar = self._bar(self.done_levels, self.total_levels)
        log.info(
            f"  ┤ Agent 1 {bar} level {level:02d}/{self.total_levels-1} "
            f"[{src}] +{n_items} items (total {self.items_so_far})"
        )

    def level_failed(self, level: int) -> None:
        self.failed_levels += 1
        log.warning(f"  ┤ Agent 1 level {level:02d} FAILED ({self.failed_levels} pending)")

    def agent1_summary(self) -> None:
        log.info(
            f"\n── Agent 1 complete ──────────────────────────────\n"
            f"   levels : {self.done_levels}/{self.total_levels}  (failed: {self.failed_levels})\n"
            f"   items  : {self.items_so_far}\n"
            f"──────────────────────────────────────────────────"
        )

    @staticmethod
    def _bar(done: int, total: int, width: int = 12) -> str:
        filled = int(width * done / total) if total else 0
        return f"[{'█' * filled}{'░' * (width - filled)}]"


def _chunk_text(text: str, max_chars: int = 5000, split_after: int = 4000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, remaining = [], text
    while len(remaining) > max_chars:
        cut = remaining.find("\n##", split_after)
        if cut == -1:
            cut = remaining.find("\n\n", split_after)
        if cut == -1:
            cut = split_after
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _extract_chunks(chunks: list[str], level: int, client, system: str) -> list[dict]:
    n = len(chunks)
    all_items: list[dict] = []
    for i, chunk in enumerate(chunks):
        note = (
            f"Note: due to large data, BFS level {level} was split into {n} chunks. "
            f"This is chunk {i+1} of {n}."
        ) if n > 1 else ""
        if n > 1:
            log.info(f"    chunk {i+1}/{n}: {len(chunk):,} chars...")
        all_items.extend(extract_learning_items(chunk, client, system=system, context_note=note))
        if i < n - 1:
            time.sleep(5)
    return all_items


def _collect_input_files(directory: Path) -> list[Path]:
    files = sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
    )
    return files


def _organize_manifests(file_manifests: list[dict], deck_name: str, client) -> list[dict]:
    """
    Given per-file manifests [{filename, items}], group them into deck groups.
    Returns [{name, items}] — one entry per output deck.
    """
    summaries = []
    for i, m in enumerate(file_manifests):
        sample_concepts = [it.get("concept", "") for it in m["items"][:8]]
        summaries.append(
            f"File {i}: {m['filename']} — {len(m['items'])} items, "
            f"sample concepts: {', '.join(sample_concepts)}"
        )

    user_msg = (
        f"Deck name hint: {deck_name}\n\n"
        f"Files:\n" + "\n".join(summaries)
    )

    raw = client.generate_json(
        user_msg,
        system=_ORGANIZER_SYSTEM,
        schema=_ORGANIZER_SCHEMA,
        temperature=0.2,
        max_tokens=1000,
    )
    decision = json.loads(raw)

    groups = []
    for g in decision["groups"]:
        combined: list[dict] = []
        for fi in g["file_indices"]:
            for item in file_manifests[fi]["items"]:
                tagged = dict(item)
                tagged["source_file"] = file_manifests[fi]["filename"]
                combined.append(tagged)
        groups.append({
            "name":      g["name"],
            "items":     combined,
            "rationale": g.get("rationale", ""),
        })
        log.info(
            f"  Organizer group '{g['name']}': "
            f"files {g['file_indices']} → {len(combined)} items  [{g.get('rationale','')}]"
        )
    return groups


def _write_template_files(template_id: str, template_files: dict) -> None:
    """Write generated template files to generator/templates/{template_id}/."""
    tdir = _TEMPLATE_DIR / template_id
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "front.html").write_text(template_files["front_html"], encoding="utf-8")
    (tdir / "back.html").write_text(template_files["back_html"],  encoding="utf-8")
    (tdir / "style.css").write_text(template_files["style_css"],  encoding="utf-8")
    log.info(f"Template written → {tdir}/")


def _minimal_deck_spec(
    prompt_text: str | None,
    input_path: Path | None,
    section_name: str,
    deck_name: str,
) -> dict:
    """Fallback spec when --skip-clarification is used."""
    return {
        "purpose": f"Flashcard deck: {deck_name}",
        "audience_level": "intermediate",
        "domain": "general",
        "section_hints": [section_name],
        "card_type": "reveal",
        "audio_needed": False,
        "target_card_count": 50,
        "depth": "concepts and key details",
        "language": "en",
        "bilingual_prompt_language": None,
        "source": "generate" if (input_path is None) else "file",
        "template_id": "reveal-interview",
        "template_new": False,
        "template_requirements": None,
    }


def _run_deck_pipeline(
    items: list[dict],
    deck_name: str,
    section_name: str,
    deck_spec: dict,
    checkpoint: "RunCheckpoint",
    client,
    vault_slugs: list[str],
    args,
    is_canvas: bool = False,
) -> None:
    """Run Agent 2 → Preview → Agent 3 → Agent 4 → generator for one deck."""
    deck_slug = _slugify(deck_name)
    deck_dir  = _ROOT / "content" / "decks" / deck_slug

    # ── Agent 2: Deck Designer ────────────────────────────────────────────────
    blueprint: dict | None = None
    if not is_canvas and items:
        log.info("\n── Agent 2: Deck Designer ────────────────────────────────")
        blueprint = design_deck(items, deck_spec, client)

        if blueprint.get("template_new") and blueprint.get("template_files"):
            _write_template_files(blueprint["template_id"], blueprint["template_files"])

        (checkpoint.run_dir / "blueprint.json").write_text(
            json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n"
        )

    # ── Preview: 2 sample cards ───────────────────────────────────────────────
    user_preview_feedback = ""
    if not args.skip_preview and not is_canvas and items and blueprint:
        log.info("\n── Preview: writing 2 sample cards ──────────────────────")
        first_section = blueprint["sections"][0] if blueprint.get("sections") else None
        sample_section_name = first_section["name"] if first_section else section_name

        sample_cards = write_sample_cards(
            items,
            sample_section_name,
            client,
            deck_spec=deck_spec,
            blueprint_section=first_section,
            vault_slugs=vault_slugs or None,
        )

        if sample_cards:
            preview_path = checkpoint.run_dir / "preview.html"
            generate_preview(
                sample_cards,
                blueprint,
                template_dir=_TEMPLATE_DIR,
                output_path=preview_path,
                deck_name=deck_name,
            )
            print(f"\n── Preview ready ─────────────────────────────────────────")
            print(f"   Open in browser: {preview_path}")
            print(f"   Then give feedback below (or press Enter to proceed):\n")
            try:
                user_preview_feedback = input("  Feedback > ").strip()
            except EOFError:
                pass
            print()
            if user_preview_feedback:
                log.info(f"Preview feedback: {user_preview_feedback}")

    # ── Agent 3: Card Writer ──────────────────────────────────────────────────
    _section_feedback = _feedback_by_section(deck_slug).get(section_name, [])

    log.info("\n── Agent 3: Card Writer ──────────────────────────────────")

    result = build_card_data(
        items, section_name, client,
        batch_cache_dir=checkpoint.agent2_dir,
        feedback_comments=_section_feedback or None,
        vault_slugs=vault_slugs or None,
        deck_spec=deck_spec,
        blueprint=blueprint,
        user_feedback=user_preview_feedback,
    )

    if isinstance(result, list):
        sections_output = result
    else:
        sections_output = [{"name": result.get("section_name", section_name), "cards": result.get("cards", [])}]

    log.info("Sanitizing tags...")
    for sec in sections_output:
        for card in sec["cards"]:
            if "tags" in card and isinstance(card["tags"], list):
                card["tags"] = [_slugify(tag) for tag in card["tags"]]

    total_cards = sum(len(s["cards"]) for s in sections_output)
    log.info(f"Agent 3: {total_cards} cards across {len(sections_output)} section(s)")

    checkpoint.save_agent2_output({"sections": sections_output})

    # ── Agent 4: Quality Reviewer ─────────────────────────────────────────────
    if not args.skip_review and not is_canvas:
        log.info("\n── Agent 4: Quality Reviewer ─────────────────────────────")
        for sec in sections_output:
            sec["cards"] = review_cards(sec["cards"], sec["name"], deck_spec, client)
        total_after = sum(len(s["cards"]) for s in sections_output)
        log.info(f"Agent 4 complete: {total_after} cards kept (was {total_cards})")

    # ── Write deck files ──────────────────────────────────────────────────────
    deck_dir.mkdir(parents=True, exist_ok=True)

    all_types_used: list[str] = []
    for sec in sections_output:
        for card in sec["cards"]:
            ct = card.get("card_type", "reveal")
            if ct not in all_types_used:
                all_types_used.append(ct)

    type_entries = []
    for t in dict.fromkeys(all_types_used):
        fname = _TYPE_FILES.get(t)
        if fname and (_CARD_TYPES / fname).exists():
            type_entries.append({"id": t, "definition": f"../../card_types/{fname}"})
        else:
            log.warning(f"  no card type definition for '{t}' — skipped")

    deck_json = {
        "deck_name": deck_name,
        "output":    f"../../../output/{deck_slug}.apkg",
        "sub_decks": True,
        "types":     type_entries,
    }
    (deck_dir / "deck.json").write_text(
        json.dumps(deck_json, indent=2, ensure_ascii=False) + "\n"
    )
    log.info(f"  deck.json → {deck_dir / 'deck.json'}")

    for sec in sections_output:
        sec_slug = _slugify(sec["name"])
        sec_file = deck_dir / f"{sec_slug}.json"
        sec_file.write_text(json.dumps({"name": sec["name"], "cards": sec["cards"]}, indent=2, ensure_ascii=False) + "\n")
        log.info(f"  section  → {sec_file}  ({len(sec['cards'])} cards)")

    checkpoint.save_deck_files(
        deck_json,
        {"sections": sections_output},
        f"{_slugify(sections_output[0]['name'])}.json",
    )

    if args.skip_generate:
        log.info("Skipping generator (--skip-generate). Import the JSON files manually.")
        return

    # ── Run generator ─────────────────────────────────────────────────────────
    log.info("Running generator...")
    cmd = [sys.executable, str(_ROOT / "generator" / "main.py"), "--deck", str(deck_dir)]
    if args.skip_audio:
        cmd.append("--skip-audio")

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        log.error("Generator failed — check the output above")
        sys.exit(1)

    final_apkg = _ROOT / "output" / f"{deck_slug}.apkg"
    if final_apkg.exists():
        checkpoint.save_final_apkg(final_apkg)

    log.info(f"\n✅ Complete: {checkpoint.get_status()}")
    log.info(f"📁 Outputs saved to: {checkpoint.run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent pipeline: raw material → .apkg")
    parser.add_argument("--input",                help="Input file (.md, .txt, .pdf, .docx, .pptx, .canvas, …)")
    parser.add_argument("--input-dir",            help="Input directory — each file processed independently, then grouped into deck(s)")
    parser.add_argument("--prompt",               help="Instruction string instead of a file: describe what deck to build")
    parser.add_argument("--vault",                help="Obsidian vault root (required when --input is a .canvas file)")
    parser.add_argument("--deck-name",            help="Anki deck name")
    parser.add_argument("--section",              help="Section / sub-deck name (defaults to filename stem or 'Main')")
    parser.add_argument("--spec",                 help="Path to an existing Deck Spec JSON — skips Agent 0 clarification")
    parser.add_argument("--provider",             help="LLM provider: openai | anthropic | gemini")
    parser.add_argument("--model",                help="Model name override (default: provider's strong default)")
    parser.add_argument("--list-providers",       action="store_true", help="Print available providers/models and exit")
    parser.add_argument("--skip-clarification",   action="store_true", help="Skip Agent 0 (clarification); use minimal spec")
    parser.add_argument("--skip-preview",         action="store_true", help="Skip the 2-card preview loop")
    parser.add_argument("--skip-review",          action="store_true", help="Skip Agent 4 (quality reviewer)")
    parser.add_argument("--skip-audio",           action="store_true", help="Pass --skip-audio to generator")
    parser.add_argument("--skip-generate",        action="store_true", help="Write JSON only, don't build .apkg")
    parser.add_argument("--save-intermediate",    action="store_true", help="Save Agent 1 JSON for debugging")
    args = parser.parse_args()

    if args.list_providers:
        print(list_providers())
        sys.exit(0)

    if not args.deck_name:
        parser.error("--deck-name is required")

    input_sources = sum(bool(x) for x in [args.input, args.input_dir, args.prompt])
    if input_sources == 0:
        parser.error("provide one of: --input FILE, --input-dir DIR, --prompt TEXT")
    if input_sources > 1:
        parser.error("--input, --input-dir, and --prompt are mutually exclusive")

    output_base = _ROOT / "output"
    client      = build_client(args.provider, args.model)
    vault_slugs = _load_vault_slugs()
    if vault_slugs:
        log.info(f"Vault: {len(vault_slugs)} slugs loaded")

    # ── Agent 0: Clarification ────────────────────────────────────────────────
    if args.spec:
        spec_path = Path(args.spec)
        if not spec_path.exists():
            log.error(f"Spec file not found: {spec_path}")
            sys.exit(1)
        deck_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        log.info(f"Deck Spec loaded from {spec_path}")
    elif args.skip_clarification:
        deck_spec = _minimal_deck_spec(args.prompt, None, args.section or "Main", args.deck_name)
        log.info("Agent 0: skipped — using minimal spec")
    else:
        if args.input:
            input_path = Path(args.input)
            size_kb    = input_path.stat().st_size // 1024
            file_info  = f"{input_path.name} ({input_path.suffix.lstrip('.').upper()}, {size_kb} KB)"
            query      = f"Build a deck from: {input_path.name}"
        elif args.input_dir:
            input_dir = Path(args.input_dir)
            files     = _collect_input_files(input_dir)
            file_info = f"{len(files)} files in {input_dir.name}/: {', '.join(f.name for f in files)}"
            query     = f"Build a deck from a folder of {len(files)} files: {', '.join(f.name for f in files)}"
        else:
            file_info = ""
            query     = args.prompt.strip()
        deck_spec = run_clarification(query, client, file_info=file_info)

    # ── Directory mode ────────────────────────────────────────────────────────
    if args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            log.error(f"Input directory not found: {input_dir}")
            sys.exit(1)

        files = _collect_input_files(input_dir)
        if not files:
            log.error(f"No supported files found in {input_dir} (supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))})")
            sys.exit(1)
        log.info(f"Directory mode: {len(files)} file(s) in {input_dir}")

        # Run Agent 1 independently per file
        checkpoint = RunCheckpoint(output_base, args.deck_name)
        spec_out   = checkpoint.run_dir / "deck_spec.json"
        spec_out.write_text(json.dumps(deck_spec, indent=2, ensure_ascii=False) + "\n")
        log.info(f"Deck Spec saved → {spec_out}")

        file_manifests: list[dict] = []
        for fpath in files:
            log.info(f"\n── Agent 1: {fpath.name} ────────────────────────────────")
            text  = parse_file(fpath)
            log.info(f"  {len(text):,} characters")
            items = extract_learning_items(text, client, deck_spec=deck_spec)
            log.info(f"  → {len(items)} items")
            if args.save_intermediate:
                inter = checkpoint.run_dir / f"{fpath.stem}.intermediate.json"
                inter.write_text(json.dumps(items, indent=2, ensure_ascii=False))
                log.info(f"  intermediate JSON → {inter}")
            file_manifests.append({"filename": fpath.name, "items": items})

        # Organizer: group files into decks
        log.info(f"\n── Organizer: grouping {len(file_manifests)} file(s) ──────────────")
        groups = _organize_manifests(file_manifests, args.deck_name, client)
        log.info(f"Organizer: {len(groups)} deck group(s)")

        for i, group in enumerate(groups):
            group_name = group["name"]
            group_items = group["items"]
            log.info(f"\n{'='*60}")
            log.info(f"Deck {i+1}/{len(groups)}: '{group_name}' ({len(group_items)} items)")
            log.info(f"{'='*60}")

            group_checkpoint = RunCheckpoint(output_base, group_name)
            group_spec = dict(deck_spec)
            group_spec["source"] = "file"

            checkpoint.run_dir.joinpath(f"group_{i+1}_items.json").write_text(
                json.dumps(group_items, indent=2, ensure_ascii=False) + "\n"
            )
            group_checkpoint.save_agent1_output(group_items)

            _run_deck_pipeline(
                group_items,
                group_name,
                args.section or group_name,
                group_spec,
                group_checkpoint,
                client,
                vault_slugs,
                args,
            )

        if len(groups) > 1:
            log.info(f"\n✅ All {len(groups)} decks complete.")
        return

    # ── Single-file or instruction mode ──────────────────────────────────────
    if args.prompt:
        input_path   = None
        prompt_text  = args.prompt.strip()
        section_name = args.section or "Main"
        log.info(f"Instruction mode: {prompt_text[:120]}{'…' if len(prompt_text) > 120 else ''}")
    else:
        input_path   = Path(args.input)
        if not input_path.exists():
            log.error(f"Input file not found: {input_path}")
            sys.exit(1)
        prompt_text  = ""
        section_name = args.section or input_path.stem

    checkpoint = RunCheckpoint(output_base, args.deck_name)
    log.info(f"Run: {checkpoint.get_status()}")

    spec_out = checkpoint.run_dir / "deck_spec.json"
    spec_out.write_text(json.dumps(deck_spec, indent=2, ensure_ascii=False) + "\n")
    log.info(f"Deck Spec saved → {spec_out}")

    deck_slug = _slugify(args.deck_name)

    # ── Agent 1: Content (extract or generate) ────────────────────────────────
    is_canvas = (input_path is not None and input_path.suffix.lower() == ".canvas")
    items: list[dict] = []

    if deck_spec.get("source") == "generate" or input_path is None:
        log.info("Agent 1: generate mode (no source file)")
        items = generate_learning_items(deck_spec, client)

    elif is_canvas:
        if not args.vault:
            log.error("--vault is required when --input is a .canvas file")
            sys.exit(1)
        vault_path = Path(args.vault)
        if not vault_path.is_dir():
            log.error(f"Vault path not found: {vault_path}")
            sys.exit(1)

        levels_list = list(parse_canvas_levels(input_path, vault_path))
        sample = " ".join(t for _, t in levels_list[:3])[:3000]
        domain = detect_domain(sample, client)
        system = build_system_prompt(domain, deck_spec=deck_spec)

        progress = Progress(total_levels=len(levels_list))
        skipped: list[tuple] = []
        total_chars = 0

        log.info(f"\n── Agent 1  ({len(levels_list)} canvas levels) ──────────────────────────")

        for level, text in levels_list:
            checkpoint.save_canvas_level(level, 0, text)
            total_chars += len(text)

            if checkpoint.is_level_processed(level):
                run_cached = checkpoint.load_level_items(level)
                items.extend(run_cached)
                progress.level_done(level, len(run_cached), cached=True)
                continue

            cached = get_agent1(text)
            if cached is not None:
                checkpoint.save_agent1_level_items(level, cached)
                items.extend(cached)
                progress.level_done(level, len(cached), cached=True)
                continue

            chunks = _chunk_text(text)
            if len(chunks) > 1:
                log.info(f"  level {level:02d}: {len(text):,} chars — split into {len(chunks)} chunks")
            try:
                level_items = _extract_chunks(chunks, level, client, system)
            except Exception as exc:
                skipped.append((level, text, str(exc)))
                progress.level_failed(level)
                continue
            save_agent1(text, level_items)
            checkpoint.save_agent1_level_items(level, level_items)
            items.extend(level_items)
            progress.level_done(level, len(level_items))

        if skipped:
            log.info(f"\nRetrying {len(skipped)} failed level(s) after 30s cooldown...")
            time.sleep(30)
            for level, text, original_reason in skipped:
                try:
                    level_items = _extract_chunks(_chunk_text(text), level, client, system)
                    save_agent1(text, level_items)
                    progress.level_done(level, len(level_items))
                except Exception as exc:
                    log.warning(f"  retry level {level:02d}: permanently skipped.\n    first: {original_reason}\n    second: {exc}")
                    level_items = []
                    progress.level_failed(level)
                checkpoint.save_agent1_level_items(level, level_items)
                items.extend(level_items)

        progress.agent1_summary()
        log.info(f"Canvas: {total_chars:,} total chars, {len(items)} items from {len(levels_list)} levels")

    else:
        log.info(f"Parsing: {input_path}")
        text = parse_file(input_path)
        log.info(f"  {len(text):,} characters")
        items = extract_learning_items(text, client, deck_spec=deck_spec)

    checkpoint.save_agent1_output(items)

    if args.save_intermediate:
        if input_path is not None:
            inter = input_path.with_suffix(".intermediate.json")
        else:
            inter = _ROOT / "output" / f"{deck_slug}-intermediate.json"
        inter.write_text(json.dumps(items, indent=2, ensure_ascii=False))
        log.info(f"  intermediate JSON → {inter}")

    log.info(f"Agent 1 complete: {len(items)} items")

    _run_deck_pipeline(
        items,
        args.deck_name,
        section_name,
        deck_spec,
        checkpoint,
        client,
        vault_slugs,
        args,
        is_canvas=is_canvas,
    )


if __name__ == "__main__":
    main()
