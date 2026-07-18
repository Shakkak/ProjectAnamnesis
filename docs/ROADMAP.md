# Roadmap

Captured from planning sessions. Priority order within each tier.
Update this file when priorities shift — do not keep parallel lists elsewhere.

---

## What exists today (baseline — as of 2026-07-10)

| Component | Status |
|-----------|--------|
| `generator/` — deck builder (JSON → .apkg) | ✅ complete |
| `pipeline/` — 5-agent pipeline with clarification, preview, quality review | ✅ complete |
| `pipeline/preview.py` — 2-card HTML preview before full run | ✅ complete |
| `content/vault/` — 91 concept files (Obsidian-compatible) | ✅ complete |
| `content/decks/interview-prep/` — 444 cards, 19 sections | ✅ complete |
| `content/decks/english/` — 1271 English vocab cards | ✅ complete |
| `content/decks/toefl/` — 60 TOEFL email cards | ✅ complete |
| `content/vault/card_index.json` + `index.json` — dual index system | ✅ complete |
| `webapp/` — card review UI + graph visualization | ✅ complete |
| `tools/` — vault validator, coverage, index builders | ✅ complete |
| `prompts/` — reusable copy-paste prompts for manual card writing | ✅ complete |
| Deck Spec JSON contract between agents | ✅ complete |
| Blueprint-based multi-section output from one pipeline run | ✅ complete |
| Template generation (Agent 2 writes new HTML/CSS when needed) | ✅ complete |
| MyAnkiBank separate data repo with `--bank` mode | ✅ complete |

---

## Tier 1 — Fix broken fundamentals

### 1.1 Deck update without losing Anki history

**Problem:** Every time the deck is regenerated, Anki treats it as a new deck — no review history, no ease factors, no scheduling. Users lose weeks of study data on reimport.

**Solution:** genanki already uses stable note IDs. Anki preserves history when note IDs match on reimport. The issue is that currently we regenerate all IDs, or some IDs drift when content changes.

**Work needed:**
- Audit how note IDs are currently generated in `generator/generator.py`
- Ensure old card IDs never change even when card content is edited
- New cards get new IDs (fresh cards in Anki, which is correct)
- Test: generate deck → import → study → regenerate with 1 new card → reimport → verify old card history intact

---

### 1.2 AnkiConnect integration

**Problem:** No way to read what the user actually knows back into the system. Coverage analysis, feedback loops, and adaptive card generation all require this data.

**What AnkiConnect provides (via REST API on localhost:8765):**
- Per-card ease factor, interval, lapses, due date
- Deck/note/card lookup by ID or tag
- Push new notes directly into Anki (bypass .apkg import)

**Work needed:**
- `tools/anki_connect.py` — thin wrapper around AnkiConnect REST API
- Functions: `get_card_stats(note_ids)`, `push_notes(cards)`, `get_deck_names()`
- Document: user must install AnkiConnect plugin + have Anki open

---

## Tier 2 — Feedback loop improvements

**What exists:** webapp accept/reject/comment → `feedback/` files → injected into next pipeline run as `feedback_comments` per section. Per-card feedback already flows into Agent 3 prompts.

**What's missing:**
- Structural feedback ("too many cards on X") should update the saved Deck Spec Blueprint for next run — currently only card-level text feedback is used
- `--refine "add 10 more cards on attention"` flag: re-run only affected Blueprint sections, merge result with existing deck JSON without touching other sections

---

## Tier 4 — Vault tools

### 4.1 VaultValidator (tool, not agent)

Deterministic checks before card generation:

- Frontmatter present and has required fields
- Tags are not exclusively umbrella/type tags (cross-check with `excluded_tags.json`)
- `depends_on` entries resolve to existing files in `vault/`
- Wikilinks resolve
- File is named in kebab-case
- Flag suspiciously large files (>300 lines) that likely cover multiple concepts

Output: per-file report — pass / warn / fail. Warn is advisory, fail blocks generation.

### 4.2 VaultWriter agent

Takes a source document (PDF, markdown, lecture notes) and writes structured vault files into `vault/`.

Different from the current Data Provider agent: output is a `.md` concept file, not a card item. Produces the frontmatter schema, `depends_on` links, wikilinks, and full content.

Useful for users who have source material but no existing vault.

---

## Tier 5 — System design (later, do not implement yet)

These require Tier 1–3 to be stable before they make sense.

### 5.1 Two-path entry point

- **Simple path:** `./cli.sh pipeline --input notes.md --deck-name "Chapter 1"` → cards in 10 minutes, no vault required. Current system, keep it working.
- **Graph path:** vault-first workflow with coverage analysis, review UI, feedback loop. New system.

Both paths use the same generator and card schema. The difference is what feeds the generator.

### 5.2 Incremental updates

Currently the whole deck is regenerated every time. With stable IDs and AnkiConnect, a smarter update is possible:

- Detect which vault files changed since last generation (git diff or content hash)
- Only regenerate cards for changed concepts
- Only push new/changed cards to Anki

### 5.3 Curriculum ordering

For the graph path: topological sort of `depends_on` edges to determine card generation order. Foundation concepts generated first. Advanced concepts that reference prerequisites get generated after.

### 5.4 Cross-topic synthesis (automated)

Currently cross-topic cards are hand-crafted. Automatable when:
- Both concepts have ≥2 cards each (sufficient coverage)
- Concepts share a `related_to` edge or shared tags
- No existing synthesis card already covers this pair

Agent generates the synthesis question given both concept files as context.

### 5.5 Vault creation from prompt (batch)

For the prompt-based vault path: instead of one prompt per concept (100 concepts = 100 pastes), generate a structured prompt that covers 5–10 related concepts at once. User pastes once, splits the output into files.

---

## Decisions already made

| Decision | Choice | Reason |
|----------|--------|--------|
| Card review UI | Web-based (FastAPI + browser) | Native app overhead not justified for technical users |
| Anki integration | AnkiConnect plugin | Already exists, battle-tested, no DB reverse engineering |
| Vault creation paths | Manual, agent-written, prompt-based | Three paths with different quality/effort tradeoffs |
| Vault location | `content/vault/` | Separate from developer docs and agent prompts |
| Tag linking | Option A (explicit `source_nodes`) for new cards | Unambiguous, alias map as fallback for existing cards |
| Excluded tags | `tools/excluded_tags.json` — level, card-type, umbrella | Prevents false concept links from organizational tags |
| Feedback format | `feedback/<card-id>.json`, append-only | Simple, inspectable, no database needed |
| Structured card metadata | Namespaced prefixes in `tags` (`role:`, `domain:`, `style:`) | Future-proof: new values added freely, no schema migration |
| Custom deck distribution | LLM generates spec JSON (user's API key), local CLI filters | End users need no API key; LLM step is one-time per persona |

---

## Out of scope (decided against)

| Idea | Reason dropped |
|------|---------------|
| Neo4j / graph database | Obsidian vault + vault/index.json + card_index.json sufficient at this scale |
| Native Windows app | Web UI is simpler, faster to build, sufficient for technical users |
| Embeddings / vector search | Not needed while concept graph fits in a JSON file |
| Agent-generated `depends_on` edges | Hallucination risk too high; humans write structure, agents write content |
