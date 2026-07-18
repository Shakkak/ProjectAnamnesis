# generator/

Converts deck JSON files into a ready-to-import Anki `.apkg` package. No AI, no network — pure local processing.

## Usage

```bash
# Via cli.sh (runs inside Docker)
./cli.sh generate --deck content/decks/interview-prep/

# With options
./cli.sh generate --deck content/decks/interview-prep/ --skip-audio
./cli.sh generate --deck content/decks/interview-prep/ --dry-run

# The pipeline calls the generator automatically as its final step.
# Use cli.sh generate directly when re-building from existing JSON.
```

## Input format

The generator reads a deck directory containing:

```
content/decks/<deck-slug>/
├── deck.json          # deck settings + card type registry
└── <section>.json     # one file per section (array of card objects)
```

See `docs/INPUT.md` for the full JSON specification.

## Output

Generated `.apkg` files are written to `output/` at the project root. Import into Anki via **File → Import**.

## Files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point; validates input, calls generator, writes `.apkg` |
| `generator.py` | Core logic: template patching, audio injection, genanki packaging |
| `loader.py` | Loads and validates deck JSON; raises descriptive errors on schema violations |
| `tts/` | Text-to-speech subsystem (pluggable) |
| `tts/kokoro_provider.py` | Kokoro TTS implementation; content-hash filenames prevent collisions |

## Audio generation

Audio is generated using Kokoro (local model, run in Colab). Files are named by content hash so unchanged cards reuse cached audio and only new/edited cards get re-synthesised.

Pass `--skip-audio` to skip TTS entirely (faster builds, useful when iterating on card content).

## Card template

Cards use the **Memrise template** (patched at build time). Template updates propagate automatically on the next generator run — no manual Anki editing needed. See `docs/TEMPLATE.md` for how template slots map to card fields.

## Custom card types

Card types are defined in `content/card_types/` and referenced from `deck.json`. Built-in types: `reveal`, `typing_qa`, `multiple_choice`, `cloze`. Add a new type by writing a card type JSON definition — see `docs/INPUT.md`.
