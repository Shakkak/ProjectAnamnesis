# Codebase Map

Quick reference for every module. Read this before touching code to avoid unnecessary file reads.
Update this file whenever a module's purpose, key functions, or structure changes significantly.

---

## Agent Pipeline (`pipeline/`)

### `pipeline/pipeline.py`
**Entry point for the full 5-agent run.** Orchestrates: Agent 0 (clarification) → Agent 1 (content) → Agent 2 (deck designer) → preview loop → Agent 3 (card writer) → Agent 4 (quality reviewer) → generator.

Key functions:
- `main()` — CLI arg parsing, runs the full pipeline
- `_chunk_text(text, max_chars=5000, split_after=4000)` — splits large level text at first `##` heading
- `_extract_chunks(chunks, level, client, system)` — calls Agent 1 per chunk, merges results
- `_write_template_files(template_id, template_files)` — writes generated template HTML/CSS to `generator/templates/{type_id}/`
- `_minimal_deck_spec(...)` — fallback Deck Spec when `--skip-clarification` is used

Key flags: `--spec PATH` (load existing Deck Spec), `--skip-clarification`, `--skip-preview`, `--skip-review`
Canvas mode: unchanged — iterates `parse_canvas_levels()` per BFS level; Deck Designer skipped (canvas already has structure).
Non-canvas: full 5-agent pipeline with Deck Spec → Blueprint → multi-section output.

---

### `pipeline/canvas_parser.py`
**Parses Obsidian `.canvas` files into text chunks via BFS traversal.**

Key functions:
- `parse_canvas_levels(canvas_path, vault_path)` — yields `(level: int, text: str)` per BFS level; skips image-only nodes; emits `# Section: X` headers when group changes
- `parse_canvas(canvas_path, vault_path, checkpoint=None)` — backward-compat wrapper, joins all levels into one string

---

### `pipeline/checkpoint.py`
**Manages timestamped run directories with per-level checkpoints and history.**

Key class: `RunCheckpoint(base_output_dir, deck_name)`
Key methods: `save_canvas_level`, `save_agent1_level_items`, `is_level_processed`, `load_level_items`, `save_agent1_output`, `save_agent2_output`, `save_deck_files`, `save_final_apkg`
Output structure: `output/<timestamp>_<deck>/canvas/ agent1/ agent2/ deck/ final/ history.jsonl manifest.json`
Also saves: `deck_spec.json`, `blueprint.json`, `preview.html` in the run dir.

---

### `pipeline/input_parser.py`
**Converts any input file to clean text for Agent 1.** Supports `.md/.txt` (direct read), `.pdf/.docx/.pptx/.xlsx/.html/.epub/.ipynb/.csv` (via markitdown subprocess), `.canvas` (via canvas_parser).

Key function: `parse_file(path)` — routes by extension, returns clean string.

---

### `pipeline/preview.py`
**Generates a self-contained HTML preview of 2 sample cards.** Substitutes card field values into actual template HTML, inlines the CSS. User opens the file in any browser to review card format and give feedback before the full run.

Key function: `generate_preview(sample_cards, blueprint, template_dir, output_path, deck_name)` — returns path to generated HTML.
Field mapping: `{{Definition}}` → question, `{{Learnable}}` → answer, `{{Extra}}` → steps, `{{Extra 2}}` → hint.

---

### `pipeline/agents/clarification/agent.py`
**Agent 0 — interactive two-step clarification.**
Step 1: LLM generates 0–5 targeted questions based on what's ambiguous in the user's request.
Step 2: Collects user answers interactively (CLI), then synthesizes a complete Deck Spec JSON.

Key function: `run_clarification(prompt_text, client, file_info="")` → Deck Spec dict.
Deck Spec schema: `purpose, audience_level, domain, section_hints, card_type, audio_needed, target_card_count, depth, language, bilingual_prompt_language, source, template_id, template_new, template_requirements`
Bypass: `--spec PATH` (load existing spec) or `--skip-clarification` (use minimal defaults).

---

### `pipeline/agents/data_provider/agent.py`
**Agent 1 — Content agent. Two modes:**
- Extract mode (file/canvas): detects domain, loads domain guide, extracts structured learning items from source text. `deck_spec` is injected as context when provided.
- Generate mode (no file): synthesizes learning items from the LLM's own knowledge, guided by the Deck Spec. Adds `confidence` field (high/medium/low) to each item.

Key functions:
- `extract_learning_items(text, client, system=None, context_note="", deck_spec=None)` — extract mode
- `generate_learning_items(deck_spec, client)` — generate mode (no source text)
- `detect_domain(text, client)`, `build_system_prompt(domain, deck_spec=None)`

Prompts: `agents/data_provider/prompts.json` (keys: `domain_detect`, `base_system`, `generate_system`)

---

### `pipeline/agents/deck_designer/agent.py`
**Agent 2 — Deck Designer. Produces a Blueprint from items + Deck Spec.**

Blueprint contains: ordered sections with `name, card_count, card_type, item_indices, key_concepts, ordering_note`; `template_id`, `template_new`, `audio_needed`, `total_cards`.
If `template_new=True`: makes a second LLM call to generate `front.html`, `back.html`, `style.css`; stored in `blueprint["template_files"]`.

Key function: `design_deck(items, deck_spec, client)` → Blueprint dict.
`item_indices` per section are indices into the Agent 1 items array — Agent 3 uses them to assign items to sections.

---

### `pipeline/agents/structure_decider/agent.py`
**Agent 3 — Card Writer (formerly Structure Decider).**

With Blueprint: calls `_write_section()` per section using the section's `item_indices`; produces multi-section output (list of `{name, cards}`).
Without Blueprint: legacy single-section mode (canvas path and fallback).
Preview support: `write_sample_cards(items, section_name, client, deck_spec, blueprint_section, vault_slugs)` — writes 2 cards for the preview loop.

Key function: `build_card_data(items, section_name, client, ..., deck_spec=None, blueprint=None, user_feedback="")` — returns `list[{name, cards}]` with Blueprint, or `{section_name, types_used, cards}` without.
Prompt is now domain-agnostic (Deck Spec context injected at runtime).

---

### `pipeline/agents/quality_reviewer/agent.py`
**Agent 4 — Quality Reviewer.**
Processes cards in batches of 15. Checks: weak question fronts (rewrites), answer completeness, wrong difficulty level, duplicate coverage (drops weaker duplicate). Cards with `drop=True` are removed from final output.

Key function: `review_cards(cards, section_name, deck_spec, client)` → cleaned card list.

---

### `agents/guides/`
**Domain-specific instructions appended to Agent 1's system prompt.**

- `mathematics.md` — teaching-first philosophy, LaTeX rules, item type targets, question design patterns, hint rules, distractor quality
- `language.md` — vocabulary, multilingual, audio fields
- `programming.md` — code concepts, algorithms

---

## Generator (`generator/`)

### `generator/main.py`
**CLI entry point for deck building.** Parses args, loads deck config, runs audio generation and deck build.

Flags: `--deck`, `--bank PATH` (or `BANK_PATH` env), `--output-dir`, `--dry-run`, `--skip-audio`, `--force-regen`, `--list-types`, `--validate-type`, `--apply-feedback`, `--retire`

Key behaviour:
- Without `--bank`: standalone mode; deck paths resolve under `content/`, template dir is `generator/templates/`
- With `--bank PATH`: bank mode; deck paths resolve under `bank_path/`, template dir is `bank_path/templates/`; `output_dir` defaults to `./output/`
- Output filename auto-detection: filename-only `output` field (bank mode) resolves against `output_dir`; relative path (standalone) resolves against deck dir

---

### `generator/loader.py`
**Validates and loads all JSON input files.**

Key functions:
- `load_deck(deck_dir)` — loads `deck.json`, resolves type registry, returns deck config dict
- `load_section(path, registry)` — loads a card data file (`{name, cards}` format), validates card types, returns `(display_name, cards)`
- `load_card_type(path)` — validates a card type definition file

Valid modes: `typing`, `mchoice`, `tapping`, `cloze`, `reveal`, `listen`
Valid roles: `question`, `answer`, `extra`, `choices`, `image`, `audio_override`, `cloze`

---

### `generator/generator.py`
**Builds the Anki `.apkg` from loaded deck config and card data.**

Key functions:
- `set_bank_path(bank: Path)` — redirects `_TEMPLATE_DIR` to `bank/templates/`; called by `main.py` when `--bank` is provided
- `build_deck(deck_config, sections, audio_out_dir, bank_path, output_dir)` — main entry; builds models, maps fields, creates notes, writes package
- `build_retired_deck(deck_config, retired_ids, bank_path, output_dir)` — builds a `*-retired.apkg` to tag orphaned cards for deletion in Anki
- `_build_model(type_id, ct_def)` — loads per-type templates via `_load_card_templates(type_id)`, routes to listen / cloze / standard model
- `_load_card_templates(type_id)` — reads `front.html`, `back.html`, `style.css` from `_TEMPLATE_DIR/{type_id}/`
- `_map_to_memrise_fields(card, ct_def, choices_pool)` — maps card data to slots `[Learnable, Definition, Extra, ..., Choices]`; handles `audio_override` autoplay flag
- `_map_to_cloze_fields(card, ct_def, choices_pool)` — maps cloze card data to `[Text, Extra, ..., Choices, Audio]`
- `_map_to_listen_fields(card, ct_def)` — maps listen card data to `[Sentence, Audio]`; auto-slugs audio filename from answer if no `audio_override`
- `_dollar_to_mathjax(text)` — converts `$...$` → `\(...\)` and `$$...$$` → `\[...\]` at build time
- `_markdown_to_html(text)` — converts markdown (tables, bold/italic, lists, code blocks, blockquotes) to HTML for Anki field rendering; protects LaTeX delimiters
- `_strip_unused_blocks(html, model_fields)` — removes `{{#Field}}...{{/Field}}` blocks for fields absent from this model
- `_convert_cloze(text)` — converts `{{word}}` → `{{c1::word}}` etc.; handles LaTeX braces inside cloze markers
- `_vault_footer(card, vault_index)` — injects vault reference HTML footer for cards with `source_nodes`
- `generate_audio(sections, registry, tts_provider, audio_out_dir, force_regen)` — synthesises TTS for all `audio: true` fields; dispatches per card type via `_resolve_provider(ct_def)`

Template system: each card type has its own directory under `generator/templates/{type_id}/` with `front.html`, `back.html`, `style.css`. Templates are self-contained — no patching, no inheritance. The vocab type uses Anki's native `{{type:Learnable}}` for typing input. All back templates include a "made with ProjectAnamnesis" watermark.

---

### `generator/tts/utils.py`
**Shared TTS utility.** `word_audio_filename(word) -> str` — NFD-normalises accented chars then slugifies to `word.mp3`. Imported by `kokoro_provider.py`, `generate_vocab_cards.py`, and Colab scripts.

---

### `generator/tts/kokoro_provider.py`
**Kokoro TTS audio generation.** `generate_audio(text, output_path, lang='en-us', voice='af_heart', **kwargs) -> bool`. Maintains a per-`lang_code` pipeline singleton so the model loads once per session. Used by card types with `"tts": {"provider": "kokoro"}`. Requires `pip install kokoro soundfile` (Colab/local — not in Docker).

---

### `content/card_types/`
**Reusable card type definitions.** Each JSON file defines fields, roles, template modes, and TTS config for one card type.

| File | Mode | Use for |
|------|------|---------|
| `reveal-interview.json` | `reveal` | ML/CV interview prep cards |
| `reveal-stats.json` | `reveal` | Statistics 110 walkthrough cards |
| `reveal-speaking.json` | `reveal` | TOEFL speaking practice |
| `reveal.json` | `reveal` | Generic reveal (legacy) |
| `vocab.json` | `typing` | Persian → English vocabulary (typed input + audio on back) |
| `toefl-email.json` | `reveal` | TOEFL email writing practice |
| `toefl-listen.json` | `listen` | Listen & repeat sentences |
| `toefl-fill.json` | `cloze` | Academic cloze fill-in |
| `cloze.json` | `cloze` | Generic cloze |
| `multiple_choice.json` | `mchoice` | Multiple choice |
| `typing_qa.json` | `typing` | Short typed answers |

---

## Tools (`tools/`)

### `pipeline/llm_client.py`
**Abstract LLM client interface.** Defines `LLMClient(ABC)` with two abstract methods: `generate()` and `generate_json()`. Both `RotatingGeminiClient` and `OpenAIClient` implement this interface so the pipeline is provider-agnostic.

---

### `pipeline/gemini_client.py`
**Rotating Gemini client.** Implements `LLMClient`. Keys loaded from `GEMINI_API_KEY_1..N` env vars. Rotates on 429. Default model: `gemini-2.5-flash`.

---

### `pipeline/openai_client.py`
**OpenAI client.** Implements `LLMClient`. Key from `OPENAI_API_KEY` env var. Model from `OPENAI_MODEL` env var or defaults to `gpt-4o-mini`. `generate_json()` uses `response_format={"type":"json_object"}`.

---

### `pipeline/pipeline.py`
**Entry point for the full agent run.** Resolves the LLM provider via `build_client(args.provider, args.model)` from `client_factory.py`. Supports `--provider`, `--model`, `--list-providers` CLI flags. Loads vault slugs from `content/vault/index.json` and passes them to `build_card_data()` for source_nodes validation.

Key functions: `_load_vault_slugs()`, `main()`

---

### `tools/enrich_vocab_cards.py`
**Vocab card enricher** — adds English definitions and example sentences to vocab card JSONs via gpt-4o-mini.

Batches 20 words per LLM call (grouped by section for context), appends `📖 definition` and `💡 example` to each card's `details` field. Skips cards that already have enrichment. Writes each section file back immediately so progress survives interruption. Re-runnable safely.

Usage: `python3 tools/enrich_vocab_cards.py` or `--file vocab-toefl-*.json` for one section. `--dry-run` previews without writing. Requires `OPENAI_API_KEY` in `.env`.

---

### `tools/check_audio.py`
**Audio file auditor** — scans any deck folder and reports missing `audio_override` files.

Reads `deck.json` to find card types with `audio_override` role fields, then checks every card to confirm the referenced file exists in `media/`. Exits with code 1 if anything is missing.

Usage: `python3 tools/check_audio.py content/decks/english/` or no args to scan all decks.

---

### `tools/validate_cards.py`
**Card validator** — checks all section JSON files in `content/decks/interview-prep/`.

Checks per card:
- FAIL: `source_nodes` empty, `level` not in canonical set, `card_type` not "reveal"
- WARN: unknown source_nodes slugs (cross-checked against vault), missing `role:`/`domain:`/`style:` tags, answer <40 chars, steps <80 chars, legacy level tags

Exit code 1 on any FAIL. Usage: `python3 tools/validate_cards.py` or pass specific file paths.

---

### `tools/vault_validator.py`
**Vault Validator (4.1)** — deterministic checks on `vault/*.md` files before card generation.

Checks: kebab-case filename, YAML frontmatter present, required fields (`title`, `tags`, `status`), tags not exclusively umbrella/excluded, `related` entries resolve to vault slugs, wikilinks resolve, file size ≤300 lines.

Output: per-file FAIL/WARN report + summary. Exit code 1 on any FAIL.

Usage: `python3 tools/vault_validator.py [--bank PATH] [file ...]`

---

### `tools/coverage.py`
**Coverage tool** — unified table and priority-analysis view of concept card coverage.
Sources: `vault/index.json` + `vault/card_index.json` + vault `.md` frontmatter `related:` links.

Two modes:
- `--mode table` (default) — human-readable table sorted by gap score (0 cards = worst)
- `--mode analyze` — priority ranking with scoring; `--anki` includes lapsing card data

Scoring (analyze): 0 cards (+100), no hands-on (+40), <3 cards (+20), referenced concepts (+5/ref capped 30), lapsing (+10 each).

Usage: `python3 tools/coverage.py [--bank PATH] [--mode table|analyze] [--folder NAME] [--top N] [--anki]`

---

### `tools/feedback_reader.py`
**Feedback reader (Tier 3)** — reads `feedback/<deck>/` JSON files for two consumers.

Key functions:
- `rejected_ids(deck_slug)` — set of card IDs with `latest == "rejected"` (used by `generator/main.py --apply-feedback`)
- `comments_by_section(deck_slug)` — `{section_name: [comment, ...]}` for Agent 2 prompt injection
- `comments_by_concept(deck_slug)` — `{concept_slug: [comment, ...]}` for concept-level feedback
- `summary(deck_slug)` — human-readable CLI summary

---

### `tools/anki_connect.py`
**AnkiConnect wrapper** — thin REST client for Anki's localhost:8765 plugin API.

Key methods: `ping()`, `deck_names()`, `notes_for_deck(deck)`, `lapsing_notes(deck)`, `add_notes(notes)`.
Raises `AnkiConnectUnavailable` when Anki is not running.

---

### `tools/migrate_tags.py`
**Tag coverage tracker** — dry-run progress checker for the card quality pass.

Reports per-file counts of: cards missing `role:*`, missing `domain:*`, missing `style:*`, and cards with redundant level tags (`junior`, `mid-level`, `senior`, `level:*`). Zero output means all cards are fully tagged.

Usage: `python3 tools/migrate_tags.py` or `python3 tools/migrate_tags.py --file training-fundamentals.json`

---

### `tools/build_vault_index.py`
**Vault header indexer** — scans all `.md` files in `vault/` and writes `vault/index.json`.

Output structure: each file maps to `{title, tags, aliases, sections}`. Each H2 section has `{header, line, summary, subsections?}` where `summary` is the first meaningful content sentence after the header (markdown stripped, ≤120 chars). Run after any vault file change.

Usage: `python3 tools/build_vault_index.py [--bank PATH]`

---

### `tools/build_card_index.py`
**Card coverage indexer** — scans all `decks/interview-prep/*.json` files and writes `vault/card_index.json`.

Maps each vault concept slug to the cards that reference it via `source_nodes`. Used by `coverage.py`, the webapp graph, and Agent 2's source_nodes validation. Run after adding or editing cards.

Usage: `python3 tools/build_card_index.py [--bank PATH]`

---

### `tools/spec_schema.json`
**JSON Schema** for custom deck spec files. Validates input to `make_deck.py`.

Defines allowed values for `role`, `domain.must/include/exclude`, `level`, `style`, and `max_cards`. All fields optional.

---

### `tools/make_deck.py`
**Custom deck generator** — filters the master 608-card deck by role, domain, style, and level, then outputs a `.apkg`.

Usage: `python tools/make_deck.py --spec my_spec.json --output custom.apkg [--skip-audio] [--dry-run]`

Key functions:
- `load_and_validate_spec(path)` — loads and schema-validates the spec JSON
- `load_all_cards()` — loads all cards from `content/decks/interview-prep/*.json` into a flat list
- `filter_cards(cards, spec)` — applies domain must/include/exclude, role, level, style, and max_cards filters
- `build_custom_deck(cards, output, skip_audio)` — groups filtered cards into sections and calls the existing generator

The `domain.include` list re-orders passing cards so preferred domains fill up the `max_cards` cap first. No LLM, no API key required at runtime.

---

### `notebooks/colab_build.py`
**General-purpose Colab build script.** Given a deck folder, auto-installs deps, generates missing `audio_override` files (parallel batches via `ThreadPoolExecutor`), builds the `.apkg`, and downloads it. Works in Colab and locally.

Key steps: clone/pull → detect providers from card types → `pip install` → generate missing audio (parallel Kokoro batches) → `generator/main.py` → download. Falls back gracefully if audio generation fails (deck still built).

Usage: `!python notebooks/colab_build.py --deck content/decks/english/`

---

## Configuration & Entry Points

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Services: `app` (generator/pipeline), `webapp`. Volumes: `./content:/app/content`, `./output`, `./cache`, `./input`. Commented bank volume for bank mode. |
| `.env` / `.env.example` | `OPENAI_API_KEY`, `GEMINI_API_KEY_1..N`, `BANK_PATH` (optional, for bank mode) |
| `requirements.txt` | `genanki`, `openai`, `fastapi`, `uvicorn`, `tqdm`, `markitdown`, etc. |
