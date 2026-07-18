# tools/

Standalone utilities for maintaining the vault, cards, indexes, and deck outputs. None of these require Docker — run directly with `python3`.

## Index builders

Run after editing vault files or card JSON:

```bash
python3 tools/build_vault_index.py   # → content/vault/index.json
python3 tools/build_card_index.py    # → content/vault/card_index.json
```

These two indexes power the webapp graph, the coverage tool, and Agent 2's `source_nodes` validation.

## Validators

```bash
# Card schema: source_nodes, level, namespaced tags — exits 1 on any FAIL
python3 tools/validate_cards.py

# Vault frontmatter: required fields, status, depends_on links
python3 tools/vault_validator.py
```

`validate_cards.py` distinguishes **FAIL** (blocks CI) from **WARN** (advisory):

| Severity | Condition |
|----------|-----------|
| FAIL | `source_nodes` empty |
| FAIL | `level` not in `{fundamental, intermediate, advanced}` |
| FAIL | `card_type` not a known type |
| WARN | `source_nodes` slug not found in vault |
| WARN | Missing `role:`, `domain:`, or `style:` tag |
| WARN | Answer < 40 chars or `steps` < 80 chars |

## Coverage analysis

```bash
# Gap table: which vault concepts have the fewest cards?
python3 tools/coverage.py

# Priority ranking with weighted scoring
python3 tools/coverage.py --mode analyze
```

## Custom deck filter

```bash
# Generate a personalised .apkg from a spec JSON — no API key needed
python3 tools/make_deck.py --spec my_spec.json --output my_deck.apkg

# Dry run: print what would be selected without writing a file
python3 tools/make_deck.py --spec my_spec.json --output my_deck.apkg --dry-run
```

Spec format is documented in `spec_schema.json`. Use `prompts/custom_deck_spec.md` to generate a spec with any LLM.

## Tag coverage

```bash
# Check that every card has role:/domain:/style: tags
python3 tools/migrate_tags.py
```

## Feedback

```bash
# Summarize accepted/rejected/commented cards for a deck
python3 tools/feedback_reader.py interview-prep
```

## Pruning

```bash
# Keep only the last N pipeline runs
python3 tools/prune.py outputs --keep 3

# Remove Agent 1 cache entries older than N days
python3 tools/prune.py cache --days 30
```

## Anki Connect

`anki_connect.py` — helper for pushing cards directly to a running Anki instance via the AnkiConnect plugin (development use).

## Files

| File | Purpose |
|------|---------|
| `validate_cards.py` | Schema validator for all deck card JSON files |
| `build_vault_index.py` | Builds `content/vault/index.json` (section headers + line numbers) |
| `build_card_index.py` | Builds `content/vault/card_index.json` (concept → card coverage) |
| `coverage.py` | Concept coverage gap analysis and scoring |
| `vault_validator.py` | Validates vault frontmatter, required fields, link targets |
| `make_deck.py` | Filters master deck by role/domain/style/level → custom `.apkg` |
| `migrate_tags.py` | Checks `role:`/`domain:`/`style:` tag completeness |
| `feedback_reader.py` | Reads `feedback/` JSON and prints a per-section summary |
| `prune.py` | Cleans up old pipeline outputs and stale cache entries |
| `anki_connect.py` | AnkiConnect API helper for live Anki sync |
| `spec_schema.json` | JSON Schema for custom deck spec files |
| `tag_aliases.json` | Tag normalisation map (raw → canonical) |
| `excluded_tags.json` | Tags excluded from coverage and graph views |
| `migrations/` | One-shot historical migration scripts (do not re-run) |
