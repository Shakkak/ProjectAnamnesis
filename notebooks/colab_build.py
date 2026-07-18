#!/usr/bin/env python3
"""
General-purpose deck builder for Google Colab (or any environment without Docker).

Given a deck folder, this script:
  1. Clones / updates the repo (Colab only; skipped when run locally)
  2. Detects which TTS providers the deck needs and installs them
  3. Generates missing audio_override files in parallel batches using the
     provider declared in each card type's ``tts.provider`` field
  4. Builds the .apkg via the standard generator
  5. Downloads the output (Colab only)

Usage in Colab:
    !git clone https://github.com/Shakkak/ProjectAnamnesis.git
    !git clone https://github.com/Shakkak/MyAnkiBank.git /content/ProjectAnamnesis/content
    !python ProjectAnamnesis/notebooks/colab_build.py --deck content/decks/english

The generator automatically checks content/templates/ before its bundled templates,
so cloning a data repo as content/ is all that's needed — no extra flags.

Flags:
    --skip-audio   build deck without generating/checking audio files
    --dry-run      validate inputs only, write nothing
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

BATCH_SIZE  = 20
MAX_WORKERS = 4


# ---------------------------------------------------------------------------
# Step 1 — resolve repo root from script location
# ---------------------------------------------------------------------------

def step_setup() -> Path:
    """Resolve the repo root from this script's location and set up sys.path.

    If the directory is a git repo, runs ``git pull`` so the generator code
    is always up to date.

    Recommended Colab workflow:
        !git clone https://github.com/Shakkak/ProjectAnamnesis.git
        !python ProjectAnamnesis/notebooks/colab_build.py --deck content/decks/english/
    """
    repo_root = Path(__file__).parent.parent.resolve()
    os.chdir(repo_root)
    sys.path.insert(0, str(repo_root / "generator"))
    log.info(f"Repo root: {repo_root}")

    # Pull latest code when running from a git clone (not a ZIP upload)
    if (repo_root / ".git").exists():
        log.info("Git repo detected — pulling latest changes ...")
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        msg = result.stdout.strip() or result.stderr.strip()
        if result.returncode == 0:
            log.info(f"  {msg}")
        else:
            log.warning(f"  git pull failed (continuing with local version): {msg}")

    return repo_root


# ---------------------------------------------------------------------------
# Step 2 — detect providers from card type definitions
# ---------------------------------------------------------------------------

def load_registry(deck_dir: Path) -> dict[str, dict]:
    """Load and resolve all card type definitions for the deck."""
    deck_json = json.loads((deck_dir / "deck.json").read_text())
    registry = {}
    for entry in deck_json.get("types", []):
        ct_path = (deck_dir / entry["definition"]).resolve()
        registry[entry["id"]] = json.loads(ct_path.read_text())
    return registry


def detect_providers(registry: dict) -> set[str]:
    """Return the set of TTS providers any card type needs."""
    providers = set()
    for ct_def in registry.values():
        needs_audio = any(
            fd.get("audio") or fd.get("role") == "audio_override"
            for fd in ct_def.get("fields", [])
        )
        if needs_audio:
            providers.add(ct_def.get("tts", {}).get("provider", "kokoro"))
    return providers


# ---------------------------------------------------------------------------
# Step 3 — install dependencies
# ---------------------------------------------------------------------------

def step_install(providers: set[str]) -> None:
    pkgs = ["genanki", "tqdm"]
    if "kokoro" in providers:
        pkgs += ["kokoro", "soundfile", "numpy"]
    log.info(f"Installing: {', '.join(pkgs)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + pkgs, check=True)
    log.info("Dependencies ready.\n")


# ---------------------------------------------------------------------------
# Step 4 — generate missing audio_override files (parallel batches)
# ---------------------------------------------------------------------------

def _word_audio_filename(word: str) -> str:
    w = unicodedata.normalize("NFD", word)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", w.strip().lower()).strip("_")
    return f"{slug}.mp3"


def collect_missing(deck_dir: Path, registry: dict) -> list[tuple[str, str, dict]]:
    """
    Scan every card in the deck for audio_override fields whose files are absent.
    Returns list of (filename, text_to_speak, tts_config).
    """
    media_dir = deck_dir / "media"
    media_dir.mkdir(exist_ok=True)

    # Map ct_id → (override_field, answer_field)
    override_map: dict[str, tuple[str, str]] = {}
    for ct_id, ct_def in registry.items():
        fields = ct_def.get("fields", [])
        ov = next((fd["name"] for fd in fields if fd.get("role") == "audio_override"), None)
        ans = next((fd["name"] for fd in fields if fd.get("role") == "answer"), None)
        if ov:
            override_map[ct_id] = (ov, ans)

    seen: dict[str, tuple[str, dict]] = {}  # filename → (text, tts_config)

    for path in sorted(deck_dir.glob("*.json")):
        if path.name in ("deck.json", "retired_ids.json"):
            continue
        data = json.loads(path.read_text())
        cards = data if isinstance(data, list) else data.get("cards", [])
        for card in cards:
            ct_id = card.get("card_type", "")
            if ct_id not in override_map:
                continue
            ov_field, ans_field = override_map[ct_id]
            filename = card.get(ov_field, "").strip()
            answer = (card.get(ans_field, "") if ans_field else "").split(";")[0].strip()
            if not filename and answer:
                filename = _word_audio_filename(answer)
            if not filename or (media_dir / filename).exists():
                continue
            tts_cfg = registry[ct_id].get("tts", {})
            seen[filename] = (answer or filename.replace("_", " ").replace(".mp3", ""), tts_cfg)

    return [(fn, text, cfg) for fn, (text, cfg) in seen.items()]


_VOICES_AMERICAN = ["af_heart", "af_bella", "am_michael", "am_fenrir"]
_VOICES_BRITISH  = ["bf_emma", "bm_george"]
_RANDOM_POOLS = {
    "random":          _VOICES_AMERICAN + _VOICES_BRITISH,
    "random-american": _VOICES_AMERICAN,
    "random-british":  _VOICES_BRITISH,
}


def _resolve_voice(voice: str) -> str:
    import random
    pool = _RANDOM_POOLS.get(voice)
    return random.choice(pool) if pool else voice


def _generate_kokoro(items: list[tuple[str, str, dict]], media_dir: Path, voice_override: str | None = None) -> list[str]:
    """Generate files using Kokoro. Returns list of failed filenames."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
        from tqdm import tqdm
    except ImportError as e:
        log.error(f"Kokoro import failed: {e}")
        return [fn for fn, _, _ in items]

    # One pipeline per lang_code — model loads once regardless of how many voices are used.
    # Random pools are resolved per item so each word gets a different voice.
    pipelines: dict[str, KPipeline] = {}

    # Build work list: (fn, text, resolved_voice, lang_code)
    work = []
    for fn, text, cfg in items:
        voice = voice_override or cfg.get("voice", "af_heart")
        voice = _resolve_voice(voice)
        lang = cfg.get("language", "en-us")
        lang_code = "b" if ("gb" in lang or "uk" in lang) else "a"
        work.append((fn, text, voice, lang_code))

    # Load all required pipelines upfront
    for _, _, _, lang_code in work:
        if lang_code not in pipelines:
            log.info(f"  Loading Kokoro pipeline (lang={lang_code}) ...")
            pipelines[lang_code] = KPipeline(lang_code=lang_code)

    failed = []

    def _synth(args):
        fn, text, voice, lang_code = args
        out = media_dir / fn
        try:
            pipeline = pipelines[lang_code]
            chunks = [audio for _, _, audio in pipeline(text, voice=voice)]
            if not chunks:
                return fn, False
            sf.write(str(out), np.concatenate(chunks), samplerate=24000)
            return fn, True
        except Exception:
            return fn, False

    bar = tqdm(total=len(work), unit="word", desc="Generating audio")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for start in range(0, len(work), BATCH_SIZE):
            batch = work[start:start + BATCH_SIZE]
            futures = {pool.submit(_synth, item): item for item in batch}
            for future in as_completed(futures):
                fn, ok = future.result()
                bar.update(1)
                if not ok:
                    failed.append(fn)
                    bar.write(f"  ✗ failed: {fn}")
    bar.close()

    return failed


def step_generate_audio(deck_dir: Path, registry: dict, voice_override: str | None = None) -> bool:
    """Generate all missing audio_override files. Returns True if none failed."""
    items = collect_missing(deck_dir, registry)
    if not items:
        log.info("Audio: all files present — nothing to generate.")
        return True

    log.info(f"Generating {len(items)} missing audio file(s)...")
    media_dir = deck_dir / "media"

    # Split by provider
    by_provider: dict[str, list] = {}
    for fn, text, cfg in items:
        by_provider.setdefault(cfg.get("provider", "kokoro"), []).append((fn, text, cfg))

    failed = []
    for provider_name, provider_items in by_provider.items():
        failed += _generate_kokoro(provider_items, media_dir, voice_override=voice_override)

    if failed:
        log.warning(f"Failed to generate {len(failed)} file(s). Deck will build without them.")
        return False

    log.info(f"Generated {len(items)} audio file(s).\n")
    return True


# ---------------------------------------------------------------------------
# Step 5 — build deck
# ---------------------------------------------------------------------------

def step_build(deck_dir: Path, skip_audio: bool, repo_root: Path,
               voice_override: str | None = None, theme: str | None = None) -> bool:
    gen = repo_root / "generator" / "main.py"
    cmd = [sys.executable, str(gen), "--deck", str(deck_dir)]
    if skip_audio:
        cmd.append("--skip-audio")
    if voice_override:
        cmd += ["--voice", voice_override]
    if theme:
        cmd += ["--theme", theme]
    log.info(f"Building deck ...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.stdout:
        log.info(result.stdout.strip())
    if result.returncode != 0:
        log.error(f"Generator failed:\n{result.stderr}")
        return False
    return True


# ---------------------------------------------------------------------------
# Step 6 — download (Colab) or print path (local)
# ---------------------------------------------------------------------------

def step_download(deck_dir: Path) -> None:
    deck_json = json.loads((deck_dir / "deck.json").read_text())
    output_path = (deck_dir / deck_json["output"]).resolve()
    if not output_path.exists():
        log.warning(f"Output not found: {output_path}")
        return
    size_mb = output_path.stat().st_size / 1024 / 1024
    log.info(f"Output: {output_path.name} ({size_mb:.1f} MB)")
    try:
        from google.colab import files
        files.download(str(output_path))
    except (ImportError, Exception):
        log.info(f"  Path: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an Anki deck (with Kokoro TTS) in Colab or locally."
    )
    parser.add_argument("--deck", required=True, help="Deck folder containing deck.json")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio generation entirely")
    parser.add_argument("--voice", metavar="VOICE", default=None,
                        help="Override TTS voice. Accepts a Kokoro voice ID or: random, random-american, random-british")
    parser.add_argument("--theme", metavar="THEME", default=None,
                        help="Apply a CSS theme to all card templates. Available: carbon, midnight, void, obsidian, ember, deepsea, nord, ivory")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs, do not write files")
    args = parser.parse_args()

    repo_root = step_setup()

    deck_dir = Path(args.deck)
    if not deck_dir.is_absolute():
        deck_dir = (repo_root / deck_dir).resolve()
    if not deck_dir.is_dir():
        log.error(f"Deck folder not found: {deck_dir}")
        sys.exit(1)

    log.info(f"Deck: {deck_dir}\n")
    registry  = load_registry(deck_dir)
    providers = detect_providers(registry)
    log.info(f"Providers: {providers or {'none'}}")

    if args.dry_run:
        missing = collect_missing(deck_dir, registry) if not args.skip_audio else []
        log.info(f"Dry run — {len(missing)} audio file(s) would be generated.")
        return

    if providers:
        step_install(providers)

    if not args.skip_audio:
        step_generate_audio(deck_dir, registry, voice_override=args.voice)

    if not step_build(deck_dir, skip_audio=args.skip_audio, repo_root=repo_root,
                      voice_override=args.voice, theme=args.theme):
        sys.exit(1)

    step_download(deck_dir)
    log.info("Done.")


if __name__ == "__main__":
    main()
