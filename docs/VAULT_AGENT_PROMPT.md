# Vault Markdown Agent Prompt

A self-contained prompt for any agent that needs to **create or edit** files in
`content/vault/`. Hand this file to the agent verbatim — following it should produce output
indistinguishable from a careful human pass over the vault.

Read `docs/CONTENT_STRUCTURE.md` first (per `CLAUDE.md`) for the schema this file builds on.
This document focuses on the *editorial* conventions — wikilinks, tips, footers, prose style —
that `CONTENT_STRUCTURE.md` does not cover in depth.

---

## 1. What the vault is

`content/vault/` is a set of Obsidian-compatible Markdown reference files (one file = one
concept = one slug = one filename without `.md`). They are read by humans in Obsidian (so
wikilinks and callouts render), indexed by `tools/build_vault_index.py` /
`tools/build_card_index.py`, and linked from Anki cards via `source_nodes`.

Every file you touch must remain valid on **three** axes simultaneously:
1. Obsidian rendering (wikilinks, callouts, LaTeX, tables)
2. The vault's structural schema (frontmatter, H2 sections, footer)
3. The machine indexes (rebuilt after every file)

---

## 2. File structure (required for every file, new or edited)

```markdown
---
title: "Human-readable title"
tags: [kebab-case-slug, another-slug]
aliases: [Alternative Name, another alias]
difficulty: 1            # 1 = fundamental, 2 = intermediate, 3 = advanced (rough overall pitch)
status: complete
related: [slug-one, slug-two, slug-three]
---

# Title

---

## Fundamental

Plain-language definition, the core mechanism, a worked numerical example where useful.

---

## Intermediate

Practical depth: comparisons, design tradeoffs, "when to use X vs Y" tables, common pitfalls.

---

## Advanced

Research-level depth: theoretical connections, recent papers, edge cases, surprising results.

---

*See also: [[slug-one]] · [[slug-two]] · [[slug-three]]*
```

Rules:
- **Filename = slug.** `knowledge-distillation.md` → slug `knowledge-distillation`. One concept,
  one slug, one file — never create a second file for a concept that already has a home.
- `tags` are kebab-case; never add umbrella tags (`machine-learning`, `deep-learning`,
  `statistics` — too broad to be useful for filtering).
- `related` lists slugs of closely-connected concepts (drives cross-navigation independent of
  inline links).
- `## ` (H2) headers are the only level that the index parses into `sections`. Use `### ` (H3)
  freely for subsections within Fundamental/Intermediate/Advanced.
- `---` horizontal rules separate the three major sections (and frontmatter from body).
- The `*See also:*` line is the **last line of the file**, links joined by ` · ` (U+00B7 middle
  dot, with spaces on both sides — not a hyphen or pipe).
- A new file must follow this exact three-section shape. Do not invent a different structure
  even if the concept seems to fit a different organization better — consistency across the
  vault matters more than a locally-optimal structure.

### Worked step-by-step examples — depth scales with the concept's importance

Some concepts are best understood by *running* them on small numbers, not by reading their
definition. **Whenever a concept is procedural — an algorithm, a recursive process, an
iterative update rule, a decision rule applied step by step — it needs at least one concrete,
small-scale numerical walkthrough that shows every step explicitly**, not just the formula in
the abstract. How *much* of that to build depends on how central the concept is — pick one of
four tiers:

**Tier 1 — Core/foundational concepts** (the kind that many *other* vault concepts are built
on top of — e.g. SVD, eigenvalues & eigenvectors, backpropagation, attention): give the
**full treatment**:
1. The general procedure stated for the general case (e.g. an arbitrary $M \times N$ matrix,
   an arbitrary-length sequence)
2. Pseudocode for that general procedure
3. A **trivial worked example** at the smallest meaningful scale (e.g. a $2\times2$ matrix),
   carried through every step explicitly
4. A **more complex worked example** one notch up (e.g. a $3\times3$ matrix, or a case that
   surfaces an edge case or pattern the trivial example was too small to show), also carried
   through every step explicitly

**Tier 2 — Moderately important procedural concepts**: one algorithm description + pseudocode,
plus **one** worked example at trivial-to-intermediate complexity, carried through step by
step. This is the "default" depth for a procedural concept — what `decision-trees.md`'s
Gini/information-gain walkthrough does (single worked split, no pseudocode needed because the
recursive procedure is simple enough to state in prose).

**Tier 3 — Minor procedural concepts**: skip the pseudocode — describe the algorithm in prose
(it's simple enough not to need a formal listing) and carry through **one trivial-scale**
worked example, step by step. This is the right depth for a small, self-contained procedure
that nothing else in the vault leans on — the reader needs to see it run once, but doesn't need
the scaffolding a more-leaned-on concept would justify.

**Tier 4 — Non-procedural concepts**: no worked-example requirement at all. Many vault concepts
(model calibration, generalization bounds, domain adaptation) are conceptual/comparative rather
than something you'd ever "run" step by step by hand — forcing an artificial walkthrough onto
these would be padding, not teaching.

**How to judge the tier:** look at how many *other* files lean on the concept (check its
appearances in other files' `related` fields and prose, or how often you'd expect to link to
it), not at how complicated its own math looks. SVD is Tier 1 not because the decomposition
is hard to write down, but because [[lora-quantization|LoRA]], [[eigenvalues-pca|PCA]],
[[kernel-methods|kernel methods]], and whitening all *presuppose* the reader understands it — a
gap there cascades into every file that assumes it. A moderately-leaned-on algorithm is Tier 2;
a small, narrowly-scoped procedure nothing else depends on is Tier 3 even if its own steps are
just as involved; a purely descriptive/comparative concept is Tier 4 regardless of how
important it is.

Illustration of the *step-by-step* requirement itself (Tier 2 depth — see `decision-trees.md`
for the full version in context):

```markdown
❌  Information gain measures how much a split reduces impurity.

✅  Node $S$ has 10 examples (6 positive, 4 negative) → Gini$(S) = 1-(0.6^2+0.4^2)=0.48$.
    A candidate split sends 5 examples (4 pos, 1 neg) left, 5 (2 pos, 3 neg) right:
    left Gini $=0.32$, right Gini $=0.48$ → weighted child impurity $=0.40$ →
    information gain $=0.48-0.40=0.08$. The tree compares this to every other candidate
    split at the node and keeps the largest gain.
```

The second version lets the reader *trace the algorithm's decision* with their own eyes — that
is what makes a procedural concept stick, at any tier. This is the same instinct behind the
numerical examples already present throughout the vault (see
`regularization-label-smoothing.md`'s smoothed-vs-hard-label loss comparison, or
`optimizer-lr-schedules.md`'s step-by-step warmup+cosine table).

Where it goes: the trivial example (Tier 1, Tier 3) or the single example (Tier 2) belongs in
**Fundamental**, right where the mechanism is first defined — so the reader never holds an
abstract rule in their head without an anchor. Tier 1's second, more-complex example and any
edge-case-revealing extensions belong in **Intermediate** or **Advanced**.

---

## 3. Inline `[[wikilink]]` rules

This is the part that requires judgment, not just mechanical application.

### 3.1 When to add a link

Add `[[slug]]` **on the first mention** of any concept that has its own dedicated vault file —
and only the first mention per file. Do not link the same slug twice in one file (the See-also
footer is the catch-all reference; repeated inline links clutter the prose).

Before adding a link, **verify the target file actually exists** — check
`content/vault/index.json` or `ls content/vault/**/<slug>.md`, don't guess from the concept
name. A confident-looking guess (`math-gaussian-cdf` when the real file is
`distributions-gaussian`) produces a broken link.

**If no file exists for a concept you're about to link, don't just move on — that's the
trigger, not a dead end.** A concept that a file leans on substantively (used to explain the
file's central mechanism, mentioned more than once, or referenced from several files) but has
no reference home of its own is exactly the gap §5 describes. Treat "no file to link to" as a
prompt to *evaluate whether one should exist*, not as permission to skip past it. (This is how
`decision-trees` ended up with no file despite `ensemble-methods.md` being built almost
entirely on top of it — three substantive mentions, zero link, because the absence was read as
"nothing to do" instead of "something to build.")

### 3.1.1 Finding missed links to *files that already exist*

The instruction above ("link on first mention of any concept that has its own file") quietly
assumes you already know, while reading a sentence, which concepts in the vault have dedicated
files — unrealistic across 103 files and growing. **Don't rely on memory; build the lookup
habit.** Keep `content/vault/index.json` (it has every file's `title` and `aliases`) open as
your concept roster, and when prose names something that *might* be a vault concept, check the
roster before deciding there's nothing to link. This is the mirror image of §3.1's main
rule — that one assumes you know the target exists; this one is for when you don't yet know
whether it does.

**The index itself can be stale or wrong — don't treat it as ground truth.** It's a generated
artifact (`tools/build_vault_index.py`), and a generated artifact only reflects reality as of
its last rebuild — any pass that skipped the rebuild step (§3.1.1's own reminder, or an earlier
session's) leaves it pointing at a vault that has since moved on. Cross-check anything the
index seems to be missing against the actual files on disk before concluding a concept has no
home:

```bash
find content/vault -name '*.md' | sort        # ground truth: what files actually exist
```

If a concept's title/alias doesn't appear in `index.json` but a plausibly-named file *does*
exist on disk (e.g. a slug you'd guess from the concept name), that's the index lying to you —
link to the real file, and rebuild the index (§6) so it stops lying to the next pass.

This lookup is mechanical enough to bootstrap with a script — but **its output is a candidate
list for you to triage, not an auto-linker**. A naive version flags effectively every file in
the vault, because common words that double as concept aliases (`normalization`, `bottleneck`,
`momentum`, `distributions`, `fine-tuning`) match constantly in contexts that have nothing to
do with the specific file they're an alias of. Note this script still uses `index.json` for
its alias roster — that's fine for *generating candidates fast*, but if you suspect the index
is stale, fall back to the `find` command above and the file's own frontmatter (`title`,
`aliases`) as the authoritative source for that file:

```bash
python3 - <<'EOF'
import json, re, glob, os
vault = "content/vault"
index = json.load(open(f"{vault}/index.json"))
alias_to_slug = {}
for relpath, meta in index.items():
    slug = os.path.splitext(os.path.basename(relpath))[0]
    for n in [meta.get("title", "")] + meta.get("aliases", []):
        n = n.strip().lower()
        if len(n) >= 6:                       # skip ultra-short aliases ("SFT", "ViT") — too noisy
            alias_to_slug.setdefault(n, []).append(slug)
names_sorted = sorted(alias_to_slug, key=len, reverse=True)   # longest first: "knowledge distillation" before "distillation"
for f in sorted(glob.glob(f"{vault}/**/*.md", recursive=True)):
    cur = os.path.splitext(os.path.basename(f))[0]
    text = open(f, encoding="utf-8").read()
    # strip existing wikilinks, code blocks, and LaTeX so we don't flag what's already linked
    # or match fragments of math/code that happen to look like words
    masked = re.sub(r'\[\[[^\]]*\]\]|```.*?```|\$\$.*?\$\$|\$[^$]*\$', '', text, flags=re.S).lower()
    hits = [(n, s) for n in names_sorted for s in alias_to_slug[n]
            if s != cur and re.search(r'\b' + re.escape(n) + r'\b', masked)]
    if hits:
        print(os.path.relpath(f, vault), '->', hits[:6])
EOF
```

**Triage every hit by hand** — the only question that matters: *is this prose actually
discussing the specific concept the candidate file covers, or just using the word in its
everyday/generic sense?*
- "Backpropagation" in a sentence about how gradients flow through a network → almost
  certainly [[backpropagation]].
- "Normalization" describing a generic preprocessing step in an Earth-observation file → very
  likely *not* [[feature-preprocessing]], which covers a specific, different technique — linking
  it would mislead the reader into expecting that file to be relevant here.

When in doubt, open the candidate target file and check whether *that's* the thing being
discussed. A wrong link is worse than no link — it sends the reader somewhere irrelevant and
erodes trust in every other link in the vault.

**Whether you added a brand-new file (§5) or just a missed inline link, the rule is the same:
finish the file, then immediately rebuild both indexes** (§6) — `build_vault_index.py` and
`build_card_index.py` — before moving to the next one. Don't let "it's just a link" become a
reason to skip the rebuild; line numbers shift the moment any text in the file changes.

### 3.2 Link forms

**Bare link** — when the visible text should be the slug-derived name:
```markdown
See [[knowledge-distillation]] for the full derivation.
```

**Aliased link** — when the natural prose wording differs from the slug (overwhelmingly the
common case in running text):
```markdown
Used in [[bert-mlm|BERT]], GPT, and [[vision-transformer|ViT]].
[[autoregressive-models|autoregressive transformers]] generate one token at a time.
```

**Escaped-pipe form — required inside Markdown table cells**, because a bare `|` is the table
column delimiter and will break the row:
```markdown
| [[knowledge-distillation\|Knowledge distillation]] | Soft targets (high $\tau$) |
| Image generation | FID | [[loss-kl-divergence\|KL divergence]] between real/fake distributions |
```
Note the backslash before the pipe: `[[slug\|Display text]]`. Forgetting the backslash silently
corrupts the table.

### 3.3 Two hard rules — these break rendering if violated

1. **Never place a `[[wikilink]]` inside a LaTeX block** — neither inline `$...$` nor display
   `$$...$$`. Obsidian's math renderer treats `[[`/`]]` as literal characters and the whole
   expression fails to render. Put the link in the surrounding prose instead:

   ```markdown
   ❌  minimize $D_{KL}(p \| [[loss-kl-divergence|q]])$
   ✅  minimize [[loss-kl-divergence|KL divergence]] $D_{KL}(p \| q)$ between the distributions
   ```

2. **Links inside fenced ` ``` ` code blocks are not clickable in Obsidian** — the renderer
   treats code-block content as plain text. Do not add wikilinks inside blocks containing real,
   runnable code (Python, bash, etc.). The exception is illustrative/narrative ASCII-art blocks
   that are not meant to be executed (e.g. a diagram of a pipeline using box-and-arrow text) —
   there, a wikilink can be a reasonable navigational aid; use judgment case-by-case and don't
   force it.

3. **Watch for false positives in broken-link checks**: double-bracket sequences that are
   actually LaTeX matrix/vector notation, e.g. `$\begin{bmatrix} 1 & 0.8 \\ 0.8 & 1 \end{bmatrix}$`
   rendered inline can produce text that *looks* like `[[1, 0.8]]` to a naive regex. These are
   not real links — confirm by reading context before "fixing" them.

---

## 4. Callouts — `[!tip]` and beyond

### 4.1 When to add one

Add a callout when the file's reasoning leans on background knowledge the reader has plausibly
forgotten — not every linkable concept needs one, only the ones where skipping the explanation
would make the next paragraph opaque. Canonical examples from this vault: the SVD factorisation
that underlies "matrix rank" claims, or *why* the harmonic mean (not arithmetic) is the right
tool for combining precision and recall into F1.

A good callout explains the **how/why mechanism**, not just a restatement of the linked
concept's name or a one-line definition the reader could infer from the inline link's display
text. The general principle behind this whole section: **if a callout would make the reader's
life noticeably easier at this exact spot, write it — don't wait to be asked.** The cost of a
well-placed one is a few lines; the cost of skipping it is the reader bouncing off the page to
go look something up that you could have answered in three lines right where they needed it.

Two situations come up often enough to call out by name:

**(a) "Out of nowhere, but simple."** Sometimes a sentence casually leans on a fact that's
trivial once stated but genuinely opaque if you don't already have it — the kind of thing that
stops a reader cold not because it's *hard*, but because the file never paused to say it. If
the surrounding prose would make a reader think "wait, why is that true?" and the answer is two
or three lines, that's exactly the gap a callout exists to close inline — cheaper than a link
roundtrip, and the reader doesn't lose their place in the argument they were following.

**(b) "Borrowed property from another concept."** Sometimes a file needs *one specific facet*
of a bigger concept that has (or deserves) its own file — not the whole thing, just the slice
that's load-bearing here. Rather than either (i) re-explaining the whole concept inline
(bloat — that's what the other file is for) or (ii) gesturing at it with a bare link and hoping
the reader already knows the relevant slice (the gap this section exists to close), write a
callout that states *just that slice* — concretely, with the specific property or step being
leaned on — and link to the fuller file alongside it for the reader who wants the complete
picture. The low-rank-factorisation example below is exactly this pattern: the file needs "SVD
truncation saves storage," not all of SVD, so the callout states that one consequence and links
to [[math-svd]] for the rest. **This generalizes far past SVD** — any time a file leans on one
property/step/consequence of a bigger concept (a specific theorem from convex optimization, one
failure mode of a regularizer, a single phase of an algorithm), the same move applies: state the
slice, link the whole.

### 4.2 The callout vocabulary — pick the type that names the role

Obsidian recognizes a family of callout types beyond `[!tip]` (and several spelling aliases —
e.g. `[!warning]`/`[!caution]`/`[!attention]` all render identically). Reach for whichever one's
*name* matches what the box is doing — it's a small signal to the reader about how to read what
follows, and it costs nothing to get right:

| Type | Use it for |
|---|---|
| `[!tip]` (alias `[!hint]`) | The default — a clarifying mechanism, the "borrowed slice" pattern (b) above, a useful-to-know consequence |
| `[!note]` / `[!info]` | A neutral aside — context that's good to know but isn't *required* to follow the argument (lower stakes than a tip) |
| `[!example]` | A worked numerical walkthrough that you want visually set apart from the main explanation (an alternative to inline presentation — see the worked-examples rule above; don't double up on the same example in both forms) |
| `[!warning]` / `[!caution]` | A common misconception, a place where intuition misleads, or a pitfall the reader is likely to hit in practice |
| `[!question]` / `[!faq]` | Anticipating the question a careful reader would ask at this exact point ("but doesn't that contradict X?") and answering it on the spot |
| `[!abstract]` / `[!summary]` / `[!tldr]` | A compressed recap of a dense passage — sparingly; most of this vault's files are concise enough not to need one |

Don't feel obligated to use the exotic ones — `[!tip]` covers the large majority of real cases
in this vault, including pattern (a) and (b) above. The point of naming the others is so that
when one of them is a noticeably *better* fit (a pitfall is much more naturally a `[!warning]`
than a `[!tip]`), you reach for it instead of forcing everything into the tip mold.

### 4.3 Format

```markdown
**Matrix rank** ([[linear-algebra-fundamentals]]): the rank of $A \in \mathbb{R}^{m \times n}$ is
the number of linearly independent rows/columns.

> [!tip] How low-rank factorisation works
> If rank $r < \min(m,n)$, SVD ([[math-svd]]) gives $A = U\Sigma V^\top$.
> Keeping only the top $r$ singular vectors: $A \approx U_r \Sigma_r V_r^\top = UV^T$
> where $U \in \mathbb{R}^{m \times r}$, $V \in \mathbb{R}^{n \times r}$.
> Storage drops from $mn$ to $(m+n)r$ — the core saving that LoRA exploits.
```

```markdown
**F1 uses harmonic mean** ([[math-means]]) — not arithmetic.

> [!tip] Why harmonic mean penalises near-zero components
> For P = 1.0, R = 0.01:
> - Arithmetic mean = (1.0 + 0.01)/2 = **0.505** — hides the failure
> - Harmonic mean = 2/(1/1.0 + 1/0.01) = 2/101 ≈ **0.020** — correctly low
>
> Key property: $\text{HM}(a,b) \leq \min(a,b)$ — the harmonic mean is always
> pulled toward the smaller value. This is why F1 stays near zero unless *both*
> P and R are high, not just one of them.
```

Notes:
- `> [!type] Title` on the first line (swap in whichever type from §4.2 fits — the body syntax
  is identical for all of them), every following line of the callout body prefixed with `> `.
- A blank `>` line is fine for paragraph breaks inside the callout (see second example).
- LaTeX, bullet lists, and bold work normally inside the callout body.
- Place the callout immediately after the sentence/definition it clarifies, not at the end of
  the section.

---

## 5. New-file decisions (the "Global Naming" rule)

### 5.0 Recognize the gap — don't wait for it to announce itself

This rule has two halves that must both be applied — a "don't speculate" half and a
"don't ignore a real gap" half. It's easy to internalize only the first and end up with
foundational concepts that are never given a home, because each individual editing pass
treats "no file exists" as "nothing to do here" rather than as a finding worth acting on.

A concept is a **real gap** — not speculation — when any of these hold:
- A file's central mechanism is *built on* the concept (e.g. `ensemble-methods.md` is, at its
  core, an essay about what you do with [[decision-trees|decision trees]] — bag them, boost
  them, grow them deep or shallow — yet for a long time the vault had no file explaining what
  a decision tree *is*)
- The concept recurs across multiple files' prose without ever being defined in place
- An Anki card already references the concept by name with an empty or missing `source_nodes`
  (a strong, mechanical signal — grep the deck for `"source_nodes": []` near a question whose
  topic is a single nameable concept; `bootstrap` and `cross-validation` are both in exactly
  this state as of this writing)

If you spot one of these, **stop and build the file** (§5.3) rather than filing it away as a
"maybe later." The TODO registry is for tracking *discovered* gaps across a long batch job —
it is not a substitute for creating the file when you're already standing in the room where the
gap is obvious.

The *speculative* failure mode this rule actually guards against looks different: inventing a
file for a concept that *isn't* load-bearing anywhere, or that's a near-duplicate of something
that already exists under a different name (`math-gaussian-cdf` turned out to be redundant with
`distributions-gaussian.md`, which already covers $\Phi$ and $\Phi^{-1}$ — a tip callout was
sufficient). Guarding against *that* doesn't require hesitating over concepts that are
obviously, repeatedly load-bearing — it requires checking for synonyms before you build (§5.1).

### 5.1–5.3 — How to act on a confirmed gap

1. **Check for a near-synonym before creating.** Search `content/vault/index.json` (or grep
   filenames/aliases) — the concept may already live under a different slug or be folded into
   a related file's scope. Only create a new file once you've ruled this out.
2. One concept → exactly one slug → exactly one file. If you're tracking multiple files'
   pending needs (e.g. via a TODO registry), record the new slug, its title, status, and which
   files need it — so duplicate files aren't accidentally created later.
3. Any new file must follow the **same Fundamental / Intermediate / Advanced** structure
   (§2) — frontmatter, three H2 sections, See-also footer. It then goes through the *same*
   review pass as an existing file: inline links on first mention, tips where useful, complete
   See-also footer.

---

## 6. Workflow & verification (run after every single file)

Do not batch these across multiple files — rebuild after each file so the index stays in sync,
since adding a `[!tip]` block or a paragraph shifts every line number below it.

```bash
python3 tools/build_vault_index.py
python3 tools/build_card_index.py
```

(`vault_validator.py` is also part of the documented post-change pipeline — see
`docs/CONTENT_STRUCTURE.md` §4 — for checking frontmatter/tags/links.)

### Broken-wikilink check

Run this whenever you've added new `[[slug]]` references, to catch typos before they ship:

```bash
python3 - <<'EOF'
import re, os, glob
vault = "content/vault"
all_slugs = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(f"{vault}/**/*.md", recursive=True)}
for f in glob.glob(f"{vault}/**/*.md", recursive=True):
    for link in re.findall(r'\[\[([a-z0-9-]+)\]\]', open(f).read()):
        if link not in all_slugs:
            print(f"MISSING [[{link}]]  ←  {os.path.relpath(f, vault)}")
EOF
```

A non-empty result means either a typo'd slug (fix the link) or a genuinely missing concept
(go to §5). Remember the LaTeX-matrix false-positive caveat from §3.3 — read the context of any
hit before treating it as a real broken link.

---

## 7. Editorial judgment — what "done" looks like

A fully-reviewed file (anchor example: `content/vault/adaptation/lora-quantization.md`) has:

- Inline `[[slug]]` on the first mention of every concept that has a dedicated vault file —
  not just concepts already present in the See-also footer.
- At least one callout (§4 — `[!tip]` or whichever type fits, including the "out of nowhere but
  simple" and "borrowed slice of another concept" patterns) wherever the file assumes background
  the reader may have forgotten.
- A complete `*See also:*` footer — every closely-related vault file is linked, joined by ` · `.

Do **not** force additions where they don't belong:
- A file that's already well-linked (links present at every relevant first mention, footer
  complete) needs no changes — skip it rather than padding it with redundant links.
- Don't add a callout just to have one; an unnecessary box interrupts reading flow more than it
  helps.
- Match the existing prose voice and density of the file you're editing — these are reference
  notes for an ML interview-prep audience (concise, technical, example-driven), not tutorials.

---

## 8. Quick checklist for one file pass

```
[ ] Read the file fully before editing (Edit tool requires a prior Read).
[ ] First mention of each linkable concept → [[slug]] or [[slug|alias]]
      - verify the target file exists (don't guess slugs)
      - table cells → escaped form [[slug\|alias]]
      - never inside $...$ / $$...$$ — link from surrounding prose instead
      - skip links inside real code blocks
[ ] Prose names something that *might* have its own vault file? → check it against
      content/vault/index.json (titles + aliases) before assuming there's nothing to link
      (§3.1.1) — don't rely on memory across 103+ files
[ ] Add callouts (§4 — `[!tip]`/`[!note]`/`[!warning]`/etc., whichever name fits) wherever
      background knowledge is assumed and non-obvious — including a quick aside for "simple
      but comes from nowhere" facts and a "borrowed slice" box when leaning on just one
      property of a bigger concept that has (or deserves) its own file
[ ] Procedural/algorithmic concept? → pick its tier (§2) and write the matching depth:
      Tier 1 (core, e.g. SVD/eigendecomposition) → general procedure + pseudocode +
        trivial worked example + a more complex one, both fully step-by-step
      Tier 2 (moderately important) → one algorithm + pseudocode + one trivial-to-
        intermediate worked example
      Tier 3 (minor, narrowly-scoped) → algorithm in prose (no pseudocode) + one
        trivial-scale worked example, step by step
      Tier 4 (non-procedural) → no worked example needed
[ ] Extend *See also:* footer with any newly-relevant slugs (· separated, no duplicates)
[ ] Concept with no file, but load-bearing / recurring / cards reference it with empty
      source_nodes? → that's a confirmed gap (§5.0), not a "skip" — check for synonyms,
      then build the full 3-section file
[ ] Rebuild both indexes the moment you finish THIS file — new file, edited prose, or just
      a missed link, doesn't matter — before moving to the next one:
      python3 tools/build_vault_index.py && python3 tools/build_card_index.py
[ ] Run the broken-wikilink check if you added any new [[slug]] references
```
