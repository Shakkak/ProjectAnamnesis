# ProjectAnamnesis

*Anamnesis — the philosophical concept of recollection; that learning is the act of remembering.*

A platform for turning any learning material into professional Anki decks. Give it a document, a file, or a plain-text description of what you want to learn — a 5-agent pipeline produces a polished `.apkg` ready to import into Anki.

---

## How it works

```
Your prompt or file
        │
        ▼
Agent 0 — Clarification      asks 0–5 questions; produces a Deck Spec
        │
        ▼
Agent 1 — Content            extracts items from your file, or generates them from scratch
        │
        ▼
Agent 2 — Deck Designer      plans sections, assigns items, selects (or generates) template
        │
        ▼
Preview                      renders 2 sample cards → you give feedback before the full run
        │
        ▼
Agent 3 — Card Writer        writes cards section-by-section per the plan
        │
        ▼
Agent 4 — Quality Reviewer   fixes weak question fronts, drops duplicates
        │
        ▼
Generator                    applies templates, bundles audio, builds .apkg
        │
        ▼
      Anki deck
```

**Three input modes:**

- **File mode** — drop any document into `input/`. Supported: `.md`, `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.epub`, `.ipynb`, `.canvas` (Obsidian). Binary formats converted automatically via [markitdown](https://github.com/microsoft/markitdown).
- **Directory mode** — point at a folder of files. Agent 1 processes each file independently, then an organizer groups them into one or more decks based on topic similarity. Files on the same subject become sections in one deck; clearly different topics become separate decks.
- **Instruction mode** — no file needed. Describe the deck you want and Agent 1 synthesizes the knowledge from scratch.

---

## Quick start

### Requirements

- Docker and Docker Compose
- At least one LLM API key (OpenAI, Anthropic, or Gemini)

### 1. Configure your API key

```bash
cp .env.example .env
# Edit .env — add at least one:
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY_1=...
```

Strong models are used by default: `claude-opus-4-8` for Anthropic, `gemini-2.5-pro` for Gemini, `gpt-4o` for OpenAI.

### 2. Run the pipeline

The pipeline starts with an interactive clarification step that asks a few questions about what you want, then runs automatically.

```bash
# From a Markdown file
./cli.sh pipeline --input input/notes.md --deck-name "Biology Ch1"

# From a PDF
./cli.sh pipeline --input input/paper.pdf --deck-name "Research Paper"

# From a DOCX, PPTX, HTML, EPUB — all supported
./cli.sh pipeline --input input/slides.pptx --deck-name "Lecture 3"

# From an Obsidian canvas
./cli.sh pipeline --input input/overview.canvas --vault input/vault/ --deck-name "Course Notes"

# From a folder of files — each processed independently, then grouped into deck(s)
./cli.sh pipeline --input-dir input/lectures/ --deck-name "Biology Course"

# From instructions only (no file — agent generates knowledge from scratch)
./cli.sh pipeline \
  --prompt "Build 50 cards on transformer attention for an ML engineer preparing for interviews.
            Cover: scaled dot-product attention, multi-head, positional encoding,
            cross-attention, and common interview pitfalls." \
  --deck-name "Transformer Attention"
```

### 3. The preview loop

Before writing the full deck, the pipeline renders 2 sample cards to `output/<run>/preview.html`. Open that file in your browser, check the card style and content, then type feedback in the terminal or press Enter to proceed.

```
── Preview ready ─────────────────────────────────────────
   Open in browser: /app/output/2026-07-10_transformer-attention/preview.html
   Then give feedback below (or press Enter to proceed):

  Feedback > the question fronts are too simple, make them more interview-style
```

Your feedback is injected into Agent 3's prompt for the full run.

### 4. Import into Anki

The `.apkg` appears in `output/`. Open Anki → **File → Import**.

---

## All pipeline flags

```bash
# Input
--input FILE             input file (.md, .txt, .pdf, .docx, .pptx, .canvas, …)
--input-dir DIR          folder of files — each processed independently, then grouped into deck(s)
--prompt TEXT            instruction string — describe the deck, no file needed
--vault PATH             Obsidian vault root (required for .canvas input)

# Deck
--deck-name NAME         Anki deck name (required)
--section NAME           sub-deck / section name (default: filename stem or 'Main')

# Agent control
--spec PATH              load an existing deck_spec.json — skip Agent 0 entirely
--skip-clarification     skip Agent 0; use minimal defaults (good for scripted runs)
--skip-preview           skip the 2-card preview loop
--skip-review            skip Agent 4 (quality reviewer)

# LLM
--provider PROVIDER      openai | anthropic | gemini  (auto-detected from .env if omitted)
--model MODEL            model override (default: strong model per provider)
--list-providers         print available providers and models, then exit

# Output
--skip-audio             skip audio generation (faster, for card review or text-only decks)
--skip-generate          write JSON only, don't build .apkg
--save-intermediate      save Agent 1 JSON to file for debugging
```

### Common patterns

```bash
# Re-run without repeating clarification questions (reuse saved spec)
./cli.sh pipeline --input input/notes.md --deck-name "Bio" --spec output/2026-07-10_bio/deck_spec.json

# Fully automated run (CI, scripts, no interaction)
./cli.sh pipeline \
  --prompt "30 fundamental cards on binary search trees for a CS student" \
  --deck-name "BST" \
  --skip-clarification --skip-preview --skip-review

# Specific provider and model
./cli.sh pipeline --input input/notes.md --deck-name "Notes" \
  --provider anthropic --model claude-opus-4-8

# Write JSON files only (review before generating .apkg)
./cli.sh pipeline --input input/notes.md --deck-name "Notes" --skip-generate

# Debug: save Agent 1 output
./cli.sh pipeline --input input/notes.md --deck-name "Notes" --save-intermediate
```

---

## Build from existing JSON (no AI)

If you already have card JSON files, use `./cli.sh generate` to build directly — no pipeline, no agents.

### Basic usage

```bash
# Build a deck (audio generated automatically if card type has TTS configured)
./cli.sh generate --deck content/decks/my-deck/

# Skip audio — faster, useful when iterating on card content or templates
./cli.sh generate --deck content/decks/my-deck/ --skip-audio

# Validate inputs only — no files written
./cli.sh generate --deck content/decks/my-deck/ --dry-run
```

### Using an external data repo (bank mode)

If your deck data lives in a separate repository (e.g. MyAnkiBank), point `--bank` at it:

```bash
./cli.sh generate \
  --bank /path/to/MyAnkiBank \
  --deck decks/reflection \
  --output-dir output/

# Or set BANK_PATH once in your environment
export BANK_PATH=/path/to/MyAnkiBank
./cli.sh generate --deck decks/reflection
```

In bank mode `--deck` is resolved relative to `--bank`, and the generator automatically picks up templates from `--bank/templates/` before its own bundled ones.

### All generator flags

```bash
# Location
--bank PATH          External data root (or set BANK_PATH env var)
--output-dir PATH    Where to write the .apkg (defaults to deck folder in standalone mode)

# Deck selection
--deck DIR           Path to deck folder (absolute, or relative to --bank)

# Build control
--dry-run            Validate card JSON and templates — no files written
--skip-audio         Skip TTS generation; use existing audio files in media/
--voice VOICE        Override TTS voice for all card types (see voice options below)
--theme THEME        Apply a CSS color theme to all card templates (see theme options below)
--force-regen        Regenerate all audio even if the .mp3 file already exists
--retire             Build a *-retired.apkg to tag orphaned cards for deletion in Anki

# Inspection
--list-types         Print all card types registered for this deck and exit
--validate-type FILE Validate a single card type JSON file (no deck needed)
```

### Common patterns

```bash
# Rebuild after editing a template (skip audio to keep it fast)
./cli.sh generate --deck content/decks/reflection/ --skip-audio

# Force-regenerate all audio after changing voices in the card type JSON
./cli.sh generate --deck content/decks/reflection/ --force-regen

# Use a random American voice for every word, overriding the card type JSON
./cli.sh generate --deck content/decks/reflection/ --voice random-american --force-regen

# Apply a color theme — midnight purple instead of the template default
./cli.sh generate --deck content/decks/reflection/ --skip-audio --theme midnight

# Check what card types a deck uses
./cli.sh generate --deck content/decks/reflection/ --list-types

# Validate a new card type definition before wiring it to a deck
./cli.sh generate --validate-type content/card_types/my-type.json

# Colab equivalent (same flags, different entry point)
!python3 /content/ProjectAnamnesis/notebooks/colab_build.py \
    --deck content/decks/reflection \
    --skip-audio
```

### TTS voice options

The `voice` field in a card type's `tts` block accepts a Kokoro voice ID or one of three random-pool keys:

| Value | Behaviour |
|-------|-----------|
| `"af_heart"` | American female (default) |
| `"af_bella"` | American female, alternate |
| `"am_michael"` | American male |
| `"am_fenrir"` | American male, alternate |
| `"bf_emma"` | British female |
| `"bm_george"` | British male |
| `"random-american"` | Random pick from all American voices per word |
| `"random-british"` | Random pick from all British voices per word |
| `"random"` | Random pick from all voices (American + British) per word |

```json
"tts": {
  "provider": "kokoro",
  "language": "en-us",
  "voice": "random-american"
}
```

Audio files are cached by content hash — if a file already exists it is reused. Use `--force-regen` to re-randomize voices on an existing deck.

---

### Card themes

Pass `--theme NAME` to apply a pre-built CSS color palette to every card in the deck. Themes override the template's default colors without touching card data or audio.

```bash
./cli.sh generate --deck content/decks/reflection/ --skip-audio --theme midnight

# Colab
!python3 /content/ProjectAnamnesis/notebooks/colab_build.py \
    --deck content/decks/reflection --skip-audio --theme obsidian
```

| Theme | Feel | Background | Text |
|-------|------|------------|------|
| *(default)* | Each template's own palette | — | — |
| `carbon` | Neutral charcoal dark | `#0f0f0f` | `#f0f0f0` |
| `midnight` | Deep purple-black | `#0f0a1e` | `#e2d9f3` |
| `void` | Minimal pure black | `#000000` | `#e8e8e8` |
| `obsidian` | Dark with warm gold | `#0a0a0a` | `#f5e6b0` |
| `ember` | Dark warm orange glow | `#0d0500` | `#fff7ed` |
| `deepsea` | Dark ocean blue depth | `#00060f` | `#e0f2fe` |
| `nord` | Light Arctic blue-gray | `#eceff4` | `#2e3440` |
| `ivory` | Warm parchment light | `#f0ead8` | `#1a1000` |

Themes work by appending a `:root { }` CSS variable block after the template's own stylesheet — the cascade ensures theme values win. Templates that use CSS variables (`reveal-*`, `toefl-speaking`) respond fully; templates with hardcoded hex values respond to the outer background and surface colors.

> **Work in progress** — `toefl-email`, `toefl-fill`, `toefl-listen`, and `reflection` templates still use hardcoded hex colors and will only partially respond to themes (outer bg changes, but internal text and panel colors stay fixed). Full theme support for these templates is planned.

---

## Features

| | |
|---|---|
| **5-agent pipeline** | Clarification → Content → Deck Designer → Card Writer → Quality Reviewer |
| **Interactive preview** | 2 sample cards rendered before the full run; your feedback shapes the output |
| **Template generation** | Agent 2 designs new HTML/CSS templates when no existing one fits |
| **Multiple card types** | Typing Q&A, multiple choice, cloze, reveal, listen & repeat |
| **Per-deck visual identity** | Each deck has its own HTML/CSS template — modern, clean, unique |
| **Automatic audio** | Kokoro TTS (high quality, offline); pre-generated MP3s bundled into `.apkg` |
| **LaTeX / math** | `$...$` and `$$...$$` converted to Anki MathJax at build time |
| **RTL support** | Persian, Arabic, Hebrew — direction controlled in the template |
| **Bilingual decks** | Per-field language override; mixed-language cards in one deck |
| **Multi-provider LLM** | OpenAI, Anthropic, or Gemini — auto-detected from `.env` |
| **Content-hash caching** | Agent 1 results cached by input hash — re-runs skip unchanged chunks |
| **Resumable pipeline** | Timestamped checkpoints; pick up from any failed step |
| **Deck Spec persistence** | `deck_spec.json` saved per run — reuse with `--spec` for fast re-runs |
| **Coverage analysis** | `tools/coverage.py` shows which vault concepts have no cards yet |
| **Docker-native** | Nothing needs installing on the host |

---

## Project structure

```
pipeline/               AI agent pipeline
  pipeline.py           CLI entry point; orchestrates all 5 agents
  preview.py            2-card HTML preview generator
  input_parser.py       File → text; markitdown for binary formats
  canvas_parser.py      Obsidian canvas reader (BFS traversal)
  agents/
    clarification/      Agent 0: interactive Q&A → Deck Spec JSON
    data_provider/      Agent 1: extract from file or generate from scratch
    deck_designer/      Agent 2: Blueprint (sections, items, template)
    structure_decider/  Agent 3: Card Writer
    quality_reviewer/   Agent 4: fix weak fronts, drop duplicates
    guides/             Domain-specific prompts (math, language, programming)

generator/              Deck builder (JSON → .apkg)
  main.py               CLI: --bank, --output-dir, --retire, …
  generator.py          Field mapping, template loading, genanki packaging
  loader.py             JSON validation
  templates/            Per-deck HTML/CSS templates (one dir per card type)
  tts/                  Pluggable TTS providers

content/                Study data (standalone mode)
  decks/                Deck JSON files (one subdir per deck)
  card_types/           Card type definitions
  vault/                Obsidian concept files + index.json + card_index.json

tools/                  Dev utilities (index builders, validators, coverage, prune)
docs/                   Developer documentation
input/                  Drop source files here
output/                 Generated .apkg files + per-run checkpoints (gitignored)
cache/                  Agent 1 response cache (gitignored)
```

Full module map: [`docs/CODEBASE.md`](docs/CODEBASE.md)

---

## The Deck Spec

Agent 0 (clarification) produces a `deck_spec.json` that all downstream agents read. It captures everything needed to build a coherent deck:

```json
{
  "purpose": "Cell biology fundamentals for a first-year university course",
  "audience_level": "beginner",
  "domain": "biology",
  "section_hints": ["cell structure", "mitosis", "protein synthesis"],
  "card_type": "reveal",
  "audio_needed": false,
  "target_card_count": 60,
  "depth": "concepts + key terminology",
  "language": "en",
  "bilingual_prompt_language": null,
  "source": "file",
  "template_id": "reveal",
  "template_new": false,
  "template_requirements": null
}
```

The spec is saved to `output/<run>/deck_spec.json`. Pass it back with `--spec` to skip clarification on re-runs or when running multiple sections of the same deck.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/CONTENT_STRUCTURE.md`](docs/CONTENT_STRUCTURE.md) | Vault file format, card schema, source_nodes, index systems |
| [`docs/CODEBASE.md`](docs/CODEBASE.md) | Module map — read before touching code |
| [`pipeline/README.md`](pipeline/README.md) | Pipeline agents, input formats, all flags |

---

## Using a separate data repository

If you keep decks, card types, and templates in a separate repo, clone it directly as `content/`:

```bash
git clone https://github.com/Shakkak/ProjectAnamnesis.git
git clone https://github.com/YourUser/YourDataRepo.git ProjectAnamnesis/content
```

The generator checks `content/templates/` before its bundled templates automatically — no flags, no configuration. Run normally:

```bash
cd ProjectAnamnesis
./cli.sh generate --deck content/decks/my-deck/
```

For Colab builds, use [`notebooks/colab_build.py`](notebooks/colab_build.py) — same two-clone pattern.

---

## License

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Free to use, study, and share for non-commercial purposes.
