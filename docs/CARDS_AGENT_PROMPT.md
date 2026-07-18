# Anki Card Agent Prompt

A self-contained prompt for any agent that needs to **write or edit** Anki cards in
`content/decks/interview-prep/`. Hand this file to the agent verbatim — following it should
produce cards indistinguishable from a careful human pass over the deck.

Read `docs/CONTENT_STRUCTURE.md` first (per `CLAUDE.md`) for the authoritative schema and the
namespaced-tag reference tables (§2.5) — this document focuses on the *editorial* judgment that
schema alone doesn't convey: how to phrase a question, how much to put in `steps`, which tags to
pick, how `source_nodes` and `id` actually behave.

---

## 1. What a card is, and why it exists

Every card is one entry in `content/decks/interview-prep/<section>.json`, under `"cards"`. It
will be reviewed by a person studying for ML/CV/research-engineer interviews, displayed via the
`reveal` card type (question front; answer + steps + hint on the back, self-rated), and bridged
back to the vault through `source_nodes`. The deck builder injects a level badge and a
"Further reading" footer linking to the vault concepts in `source_nodes` — so a card's
correctness is judged not just on its own content but on whether it's correctly anchored to the
right concept file(s).

A card you write must work on **two** axes:
1. As a standalone interview exchange (question a candidate could actually be asked; answer a
   strong candidate would actually give)
2. As a structured data record that fits the deck's schema, tagging system, and concept graph

---

## 2. Card schema — every field, with editorial guidance

```json
{
  "card_type": "reveal",
  "question": "[Level] Interview-style question, phrased as something an interviewer says",
  "answer": "What a strong candidate says — 2 to 4 sentences, the core idea stated plainly",
  "steps": "Deeper follow-up: derivation, numerical example, comparison table, edge cases, papers",
  "hint": "Only when the first move is genuinely non-obvious — otherwise omit or leave \"\"",
  "tags": ["topic-slug", "another-topic", "role:mle", "domain:ml-core", "style:conceptual"],
  "source_nodes": ["concept-slug-1", "concept-slug-2"],
  "id": "auto-generated — leave absent for new cards",
  "level": "fundamental"
}
```

### `card_type`
Always `"reveal"` in this deck. Don't introduce other types (`cloze`, `multiple_choice`,
`typing_qa` exist as definitions in `content/card_types/` but this deck uses `reveal`
exclusively — 608/608 cards).

### `question`
- Phrase it the way an interviewer actually would — a real question, not a textbook prompt.
  Compare: ❌ "Explain batch normalization." ✅ "Compare batch normalization, layer
  normalization, and instance normalization. When is each appropriate, and why does batch norm
  fail with small batch sizes?"
- **Optional seniority prefix** `[Junior]` / `[Mid]` / `[Senior]` — signals the audience the
  question targets (junior → definitional/fundamental; mid → applied/comparative; senior →
  open-ended/architectural). Roughly 40% of cards carry one; the rest don't need one — only add
  it when the question is explicitly framed at a particular candidate level (e.g. "How would
  you explain X to a junior teammate?" vs. "Design a system that...").
- **`[Paper]` prefix** — for derivation/proof/exercise cards sourced from or modeled on an
  actual paper or classic problem set (e.g. "Derive the MLE for a Gaussian and show it's
  biased"). These pair with `style:derivation` and usually `level: intermediate` or `advanced`.
- These prefixes are independent of the `level` field — they describe the *question's framing*,
  not the card's pedagogical depth. Don't conflate them.

### `answer`
- 2–4 sentences. What a strong candidate says out loud in an interview — the direct, correct
  core answer, not a hedge or an outline of what they'd cover.
- State the key formula/result first, then the one-line "why" if it fits. Save derivations,
  numerical walk-throughs, and edge cases for `steps`.
- LaTeX is supported (`$...$` inline, `$$...$$` display) — use it for any formula rather than
  describing it in words.

### `steps`
- The deep-dive: full derivations, numerical worked examples, comparison tables (Markdown
  tables render fine), common pitfalls/"gotchas", paper citations, "interview context" notes
  connecting the concept to practice.
- This is where most of the card's teaching value lives — don't make it a thin restatement of
  `answer`. A good `steps` field often runs several sentences to a few paragraphs and may
  include a table, a numerical example, and a "why this matters in practice" note (see the
  Earth Observation example in §4 for a dense, well-structured version).
- Markdown formatting (bold, tables, bullet lists, inline code) and LaTeX both work here.

### `hint`
- Only include when the first move toward the answer is genuinely non-obvious (e.g. "use
  Lagrange multipliers" or "think about which dimensions the statistics are computed over").
- If the question is self-explanatory once read, **omit it or leave `""`** — most cards
  (the majority in this deck) have an empty hint. Don't manufacture a hint just to fill the
  field.

### `tags`
See §3 — this is the field most likely to be done sloppily if rushed.

### `source_nodes`
**Required on every card, never empty.** A list of vault concept slugs (the `.md` filename
without extension or directory — e.g. `content/vault/training/regularization-dropout.md` →
`"regularization-dropout"`). See §5.

### `id`
- A stable 16-character hex string. **Never invent one** — for a brand-new card, omit the
  field entirely (or leave it absent) and let the generator assign it.
- It's derived as `md5(section_name + "|||" + question[:120])[:16]` — stable across edits to
  `answer`/`steps`/`hint`/`tags`, but it **changes if you substantially rewrite the question**
  (which is correct: a rewritten question is effectively a new card, and should get a new id so
  old review history doesn't wrongly attach to it). Keep this in mind when editing — a light
  wording tweak is fine, but don't casually rewrite a question's opening clause unless you
  intend to "reset" the card.

### `level`
One of exactly three canonical values: **`"fundamental"`**, **`"intermediate"`**,
**`"advanced"`** — describing pedagogical depth, not interviewer seniority (that's what the
`[Junior]/[Mid]/[Senior]` question prefix is for; see above — the two are independent and
shouldn't be conflated). If you encounter a card with `level: "senior"` or `"mid-level"`, that's
leftover inconsistency from an older scheme — don't propagate it; always write one of the three
canonical values on new/edited cards.

---

## 3. Tagging — the part that needs the most care

`tags` mixes two kinds of entries that **coexist in the same flat array**:

1. **Plain content tags** (no colon) — kebab-case topic/concept words, e.g. `"dropout"`,
   `"batch-normalization"`, `"pca"`, `"derivation"`, `"comparison"`. These describe *what the
   card is about* and *what kind of exercise it is*.
2. **Namespaced metadata tags** (contain `:`) — structured classification under three
   prefixes. **Full reference tables are in `docs/CONTENT_STRUCTURE.md` §2.5** — read them
   before tagging; summary:
   - `role:` — who the card serves (pick 1–3): `mle`, `ds`, `cv-engineer`, `nlp-engineer`,
     `research`, `eo-specialist`
   - `domain:` — coarse topic bucket (pick 1–3): `ml-core`, `deep-learning`, `computer-vision`,
     `transformers-nlp`, `self-supervised`, `generative-models`, `statistics`, `math`,
     `earth-observation`, `biodiversity-ml`, `vision-language`, `production-ml`
   - `style:` — question type (pick 1–2): `conceptual`, `derivation`, `problem-solving`,
     `practical`, `tradeoffs`, `debugging`

Every card should carry **both** kinds: a few plain content tags identifying the concept(s),
plus the namespaced `role:`/`domain:`/`style:` set. Look at the worked examples in §4 — every
one mixes plain tags (`"pca"`, `"derivation"`, `"comparison"`) with namespaced ones
(`role:mle`, `domain:math`, `style:derivation`).

### Hard rules

- **Never add these as content tags** — they're redundant with the `level` field and must be
  removed during any edit you touch: `junior`, `mid-level`, `senior`, `level:fundamental`,
  `level:intermediate`, `level:advanced`.
- Plain content tags should be kebab-case and specific — avoid the umbrella tags listed in
  `tools/excluded_tags.json` (`machine-learning`, `deep-learning`, `statistics`, `training`,
  `evaluation`, `cross-topic`, etc.) — these are too broad to mean one concept and are
  explicitly excluded from concept-linking.
- `tools/migrate_tags.py` reports missing namespaced tags and redundant level tags per file —
  run it after a tagging pass if you want a checklist of what's still missing:
  ```bash
  python3 tools/migrate_tags.py
  ```
- New namespaced values can be added under any prefix at any time without a schema migration —
  but check the existing tables first; almost everything you need already exists there.

---

## 4. Worked examples (read these before writing — they encode the target voice and density)

**Conceptual comparison card** (`ml-cv-interview.json`, level `intermediate`):
```json
{
  "question": "Compare batch normalization, layer normalization, and instance normalization. When is each appropriate, and why does batch norm fail with small batch sizes?",
  "answer": "Batch norm normalizes across the batch dimension per channel, layer norm normalizes across all features per sample, and instance norm normalizes each sample's spatial dimensions per channel independently. Batch norm fails with small batches because per-batch statistics become unreliable.",
  "steps": "Batch normalization computes statistics over $(N, H, W)$ for each channel — it needs sufficient batch size for stable estimates. Layer normalization normalizes over all features for each individual sample, making it batch-size independent and preferred in transformers and language models. Instance normalization normalizes each sample's spatial dimensions independently per channel, used in style transfer. Group normalization is a compromise that normalizes within feature groups, working well at any batch size. The key question is always: over which dimensions are statistics computed?",
  "hint": "The key question is: over which dimensions are the statistics computed?",
  "tags": ["batch-normalization", "layer-normalization", "instance-normalization", "comparison", "role:mle", "role:nlp-engineer", "role:cv-engineer", "domain:ml-core", "style:conceptual", "style:tradeoffs"],
  "source_nodes": ["normalization-layers"],
  "level": "intermediate"
}
```
Notice: the answer states the three mechanisms and the failure mode in one breath; `steps`
expands each one, adds a fourth comparison point (GroupNorm) the answer didn't mention, and
closes with the unifying heuristic ("the key question is...") — which then doubles as the
`hint`.

**`[Paper]` derivation card** (`probability-distributions.json`, level `intermediate`):
```json
{
  "question": "[Paper] Observe $n$ i.i.d. samples from $\\mathcal{N}(\\mu,\\sigma^2)$. Derive $\\hat{\\mu}_{MLE}$ and $\\hat{\\sigma}^2_{MLE}$. Is $\\hat{\\sigma}^2_{MLE}$ biased? Explain why.",
  "answer": "$\\hat{\\mu}_{MLE}=\\bar{x}$. $\\hat{\\sigma}^2_{MLE}=\\frac{1}{n}\\sum(x_i-\\bar{x})^2$ — biased downward by $(n-1)/n$ because estimating $\\mu$ from the same data shrinks the residuals (uses one degree of freedom).",
  "steps": "(1) $\\ell(\\mu,\\sigma^2)=-\\frac{n}{2}\\log(2\\pi\\sigma^2)-\\frac{1}{2\\sigma^2}\\sum(x_i-\\mu)^2$. (2) $\\partial\\ell/\\partial\\mu=\\frac{1}{\\sigma^2}\\sum(x_i-\\mu)=0 \\Rightarrow \\hat{\\mu}=\\bar{x}$. (3) ... Bias: $E[\\hat{\\sigma}^2_{MLE}]=\\frac{n-1}{n}\\sigma^2$. Unbiased estimator (Bessel's correction): divide by $n-1$.",
  "tags": ["statistical-inference-mle", "distributions-gaussian", "role:mle", "role:ds", "role:research", "domain:statistics", "style:derivation", "style:problem-solving"],
  "source_nodes": ["statistical-inference-mle", "distributions-gaussian"],
  "level": "intermediate"
}
```
Notice: `answer` gives the final results plus the one-line intuition for the bias; `steps` is
the actual numbered derivation — a candidate could follow it as a proof sketch. No `hint`
(the first move — "write the log-likelihood" — is standard for this question type).

**Dense applied card with a table and a "[Junior]" framing** (`earth-observation.json`,
level `fundamental`):
```json
{
  "question": "[Junior] What is spatial resolution in satellite imagery and how do you choose between 10 m (Sentinel-2) and 30 m (Landsat)?",
  "answer": "Spatial resolution is the ground area represented by one pixel. At 10 m, each pixel covers a 10×10 m patch... The choice depends on your target object size and frequency of observations needed...",
  "steps": "**Resolution vs revisit trade-off:**\n\n| Satellite | Resolution | Revisit | History | Free? |\n|-----------|-----------|---------|---------|-------|\n| Sentinel-2 | 10 m (RGB/NIR) | 5 days | 2015+ | Yes |\n| Landsat 8/9 | 30 m | 16 days | 1972+ | Yes |\n\n**When to choose 10 m:** ... **Gotcha**: 'multispectral' means different resolutions for different bands... **Vault file**: `data/earth-observation-fundamentals.md`",
  "hint": "10 m = individual trees/fields. 30 m = landscape trends + 50-year history. Choose by object size and temporal depth needed.",
  "tags": ["spatial-resolution", "sentinel-2", "landsat", "earth-observation", "role:mle", "role:eo-specialist", "..."],
  "source_nodes": ["earth-observation-fundamentals"],
  "level": "fundamental"
}
```
Notice: `[Junior]` here doesn't mean "easy" in a dumbed-down sense — it's a real, substantive
question; it just frames a foundational topic the way an interviewer would pose it to someone
early-career. The `steps` field uses a Markdown table, bold call-outs, and even an explicit
pointer back to the vault file — a useful pattern for cards whose source concept has a lot of
reference detail worth signposting.

---

## 5. `source_nodes` — the bridge to the vault

- **Required on every card** — never an empty list.
- Each entry is a vault concept slug: the `.md` filename, no directory, no extension
  (`content/vault/self-supervised/knowledge-distillation.md` → `"knowledge-distillation"`).
- **Verify the slug exists** before writing it — check `content/vault/index.json` or
  `ls content/vault/**/<slug>.md`. A guessed slug that doesn't match a real file silently
  produces a broken "Further reading" link and an uncovered-concept gap in `card_index.json`.
- Cross-topic cards (comparisons spanning multiple concepts, "[Paper]" cards drawing on more
  than one theory) should list **all** genuinely relevant concepts — not just the primary one.
  See the PCA derivation example in §4-adjacent samples: it lists both
  `linear-algebra-fundamentals` and `eigenvalues-pca`.
- `source_nodes` drives three downstream systems — getting it right matters beyond the card
  itself:
  - `content/vault/card_index.json` (coverage report — which concepts have/lack cards)
  - the "Further reading" footer injected into the card back at build time
  - `tools/coverage.py` gap analysis (which concepts most need more cards)

---

## 6. Workflow & verification

After adding or editing cards in any section file:
```bash
python3 tools/validate_cards.py       # schema + quality check (source_nodes, level, tags, steps)
python3 tools/build_card_index.py     # regenerate content/vault/card_index.json
docker compose up                      # rebuild and serve the deck (never `pip install` on host —
                                        # all Python deps run inside Docker, per CLAUDE.md)
```

`validate_cards.py` must pass (0 FAIL) before committing. Warnings (empty steps, short answers) are advisory.

If you've done a tagging pass, also run:
```bash
python3 tools/migrate_tags.py          # reports missing namespaced tags + redundant level tags
```

To find which vault concepts most need new cards (useful before writing a batch from scratch):
```bash
python3 tools/coverage.py                              # table view
python3 tools/coverage.py --mode analyze --top 20      # priority ranking by gap score
```

---

## 7. Editorial judgment — what makes a card "good enough to ship"

- **The question must be something an interviewer would actually ask**, not a rephrased
  textbook heading. If you can't picture a person saying it out loud across a table, rewrite it.
- **The answer must be what a strong candidate says** — confident, correct, to the point. Not
  a hedge ("it depends, but generally..."), not an essay outline ("there are three things to
  consider...").
- **`steps` is where the teaching happens** — don't shortchange it. A thin `steps` field on a
  card whose `answer` already says everything is a sign the split between the two fields is
  wrong; push detail (derivations, tables, numerical examples, edge cases, "gotchas", paper
  references) down into `steps` and keep `answer` lean.
- **Don't pad `tags`** with near-duplicate plain tags or namespaced tags that don't really
  apply just to "fill the quota" (`role:` 1–3, `domain:` 1–3, `style:` 1–2 are *maximums*, not
  targets — a card that's clearly `domain:ml-core` only doesn't need a second, weaker `domain:`
  tag bolted on).
- **Match the existing density and voice** of the section you're adding to — some sections
  (e.g. Earth Observation) lean into dense reference tables in `steps`; others (e.g. core ML
  theory) lean into derivations. Read a few neighboring cards in the same file before writing
  new ones for it.

---

## 8. Quick checklist for one card

```
[ ] question — phrased as a real interview question; [Junior]/[Mid]/[Senior]/[Paper] prefix only if it genuinely frames the audience/format
[ ] answer — 2-4 sentences, what a strong candidate says, formula-first if applicable
[ ] steps — the actual depth: derivation / numerical example / comparison table / pitfalls / papers
[ ] hint — only if the first move is non-obvious; otherwise omit or ""
[ ] tags — plain content tags (kebab-case, specific, no umbrella terms) + role:/domain:/style: (within the 1-3/1-3/1-2 limits)
[ ] tags — no junior/mid-level/senior/level:* redundant tags
[ ] source_nodes — non-empty; every slug verified to exist; cross-topic cards list all relevant concepts
[ ] id — omit for new cards (let the generator assign it); never invent one
[ ] level — exactly one of fundamental / intermediate / advanced
[ ] after editing the file: python3 tools/validate_cards.py && python3 tools/build_card_index.py
```
