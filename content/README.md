# content/

User data directory — gitignored so each user maintains their own. The pipeline writes generated decks here; tools read vault and card type definitions from here.

```
content/
├── vault/          # Obsidian concept files — one .md per concept
├── decks/          # Anki deck JSON files — one folder per deck
├── card_types/     # Reusable card type definitions
└── prompts/        # Manual copy-paste prompts for content authoring
```

## vault/

Markdown concept files organised into subject subdirectories. Each file covers one concept (e.g. `attention-mechanism.md`).

Two machine-readable indexes are built from vault files — do not edit them manually:

```bash
python3 tools/build_vault_index.py   # → vault/index.json
python3 tools/build_card_index.py    # → vault/card_index.json
```

Full vault file format spec: `docs/CONTENT_STRUCTURE.md`.

## decks/

One subdirectory per Anki deck:

```
decks/<deck-slug>/
├── deck.json              # Deck settings + card type registry
├── retired_ids.json       # Card IDs removed (prevents ID reuse)
└── <section-slug>.json    # One file per section — array of card objects
```

Full card schema and all optional fields: `docs/CONTENT_STRUCTURE.md`.

## card_types/

Card type definition files referenced by `deck.json`. Built-in types: `reveal`, `typing_qa`, `multiple_choice`, `cloze`, `vocab`. Each type maps to a template in `generator/templates/{type_id}/`.

## prompts/

Manual copy-paste prompts used for authoring content (TOEFL writing, vocab, vault restructure, etc.). Not used by the automated pipeline.
