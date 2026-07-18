# pipeline/

AI agent pipeline: learning material or instructions → Anki-ready JSON card files → `.apkg`.

## Two input modes

### File mode — give it a document

Pass any file in `input/`. The pipeline converts it to text automatically:

| Format | Handled by |
|--------|-----------|
| `.md`, `.txt` | read directly; Obsidian syntax stripped for `.md` |
| `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.epub`, `.ipynb`, `.csv` | converted by **markitdown** |
| `.canvas` | Obsidian canvas — BFS traversal via `canvas_parser.py`; requires `--vault` |

```bash
./cli.sh pipeline --input input/notes.md      --deck-name "Biology Ch1"
./cli.sh pipeline --input input/slides.pdf    --deck-name "Lecture 3"
./cli.sh pipeline --input input/report.docx   --deck-name "Research Paper"
./cli.sh pipeline --input input/overview.canvas --vault input/vault/ --deck-name "Stats 110"
```

### Instruction mode — describe the deck you want

No file needed. Write a plain-text instruction; Agent 1 generates knowledge from scratch.

```bash
./cli.sh pipeline \
  --prompt "Build 30 cards on gradient descent for a junior ML engineer.
            Cover: the update rule, learning rate effects, momentum, common
            pitfalls, and one worked example." \
  --deck-name "Gradient Descent"
```

## Agent flow

```
User: prompt + optional file
          │
          ▼
  Agent 0: Clarification          ← interactive Q&A; produces Deck Spec JSON
          │  [--skip-clarification or --spec PATH to bypass]
          ▼
  Agent 1: Content                ← extract (file) or generate (no file) learning items
          │
          ▼
  Agent 2: Deck Designer          ← Blueprint: sections, card counts, order, template
          │  [canvas mode skips this — structure comes from BFS levels]
          ▼
  Preview: 2 sample cards         ← static HTML; user gives feedback before full run
          │  [--skip-preview to bypass]
          ▼
  Agent 3: Card Writer            ← writes cards section-by-section per Blueprint
          │
          ▼
  Agent 4: Quality Reviewer       ← fixes weak fronts, drops duplicates
          │  [--skip-review to bypass]
          ▼
  Generator → .apkg
```

### The Deck Spec

Agent 0 produces a `deck_spec.json` that all downstream agents read. It captures:

```json
{
  "purpose": "ML interview prep for FAANG",
  "audience_level": "intermediate",
  "domain": "machine-learning",
  "section_hints": ["optimization", "attention", "fine-tuning"],
  "card_type": "reveal",
  "audio_needed": false,
  "target_card_count": 80,
  "depth": "concepts + key math, no full proofs",
  "language": "en",
  "bilingual_prompt_language": null,
  "source": "file",
  "template_id": "reveal-interview",
  "template_new": false,
  "template_requirements": null
}
```

Saved to `output/<run>/deck_spec.json`. Reuse with `--spec` to skip clarification on re-runs.

## Common flags

```bash
--section "Chapter 1"        sub-deck name (default: filename stem or 'Main')
--spec PATH                  load existing Deck Spec JSON, skip Agent 0
--skip-clarification         skip Agent 0; use minimal defaults
--skip-preview               skip the 2-card preview loop
--skip-review                skip Agent 4 (quality reviewer)
--provider anthropic          LLM provider: openai | anthropic | gemini
--model claude-opus-4-8       model override (default: strong model per provider)
--list-providers             print available providers/models and exit
--skip-audio                 pass --skip-audio to generator
--skip-generate              write JSON only, don't build .apkg
--save-intermediate          dump Agent 1 JSON for debugging
```

## Files

| File | Purpose |
|------|---------|
| `pipeline.py` | CLI entry point; orchestrates the full 5-agent flow |
| `input_parser.py` | Converts any input file to text; markitdown for binary formats |
| `canvas_parser.py` | Obsidian `.canvas` files; BFS level traversal |
| `preview.py` | Generates self-contained HTML preview of 2 sample cards |
| `llm_client.py` | Abstract `LLMClient` interface (generate, generate_json) |
| `client_factory.py` | Provider + model resolution; `build_client()`, `list_providers()` |
| `openai_client.py` | OpenAI — default model: `gpt-4o` |
| `anthropic_client.py` | Anthropic — default model: `claude-opus-4-8` |
| `gemini_client.py` | Gemini rotating-key — default model: `gemini-2.5-pro` |
| `checkpoint.py` | Timestamped run checkpoints; resume from any failed step |
| `cache.py` | Content-hash cache for Agent 1 (avoid re-processing unchanged text) |
| `utils.py` | `slugify()` and other shared helpers |

## Agents

### Agent 0 — `agents/clarification/`
Interactive two-step: generates 0–5 targeted questions → collects answers → synthesizes Deck Spec JSON.
Skipped when `--spec` or `--skip-clarification` is passed.

### Agent 1 — `agents/data_provider/`
**Extract mode** (file/canvas): detects domain, loads domain guide (`agents/guides/`), extracts structured learning items. Deck Spec context is injected to calibrate depth and audience.
**Generate mode** (no file): synthesizes learning items from the LLM's knowledge. Adds `confidence` (high/medium/low) per item.

### Agent 2 — `agents/deck_designer/`
Designs the deck structure from items + Deck Spec. Outputs a Blueprint: ordered sections with item assignments (`item_indices`), card counts, card types, template selection. If no existing template fits, generates `front.html`, `back.html`, `style.css` for a new one.

### Agent 3 — `agents/structure_decider/`
Card Writer. With Blueprint: writes cards section-by-section using item assignments. Without Blueprint (canvas): legacy single-section batch mode. Accepts `user_feedback` from the preview step.

### Agent 4 — `agents/quality_reviewer/`
Lightweight review in batches of 15. Rewrites weak question fronts, fixes wrong difficulty levels, drops duplicate cards.

## LLM provider configuration

```bash
# .env — set one or more
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY_1=...        # _2, _3, ... for key rotation

# Optional runtime overrides
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-4-8
```

Auto-detect priority when multiple keys are present: OpenAI → Anthropic → Gemini.
Default models: OpenAI → `gpt-4o`, Anthropic → `claude-opus-4-8`, Gemini → `gemini-2.5-pro`.

## Caching

| Cache | Keyed by | Location |
|-------|----------|----------|
| Agent 1 | Content hash of the input text chunk | `cache/` |
| Agent 3 | Content hash of each item batch | `output/<run>/agent2/` |

Delete a cache entry to force re-processing of that chunk.
