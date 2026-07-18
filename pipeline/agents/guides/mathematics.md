# Mathematics Guide — Claude v2

## Core Principle

The source material contains real worked examples, story proofs, and intuitions. Extract those — do not replace them with generic synthetic versions. A real example from the notes is always better than a synthesized one.

---

## Reading Obsidian Notes

The notes use callout blocks. Map them as follows:

| Callout | What it is | What to do |
|---------|-----------|-----------|
| `[!Example]` | Worked problem with solution | Extract as `solvable` — use the exact setup and numbers |
| `[!check]` / `[!Proof]` | Proof written by the student | Extract as `proof` or `derivation` |
| `[!Tip]` / `[!Intuition]` | Conceptual insight | Include in `details` or use to write a teaching question |
| `[!Definition]` | Precise definition | Extract as `definition` or `theorem` |
| `[!NOTE]` | Key property or result | Extract as `theorem` if it has conditions |

When a `[!Example]` block appears in the source, that is your primary card for that concept. Do not create a different synthetic example alongside it — use the one the student actually wrote.

---

## Story Proofs (Probability-Specific)

A story proof is an argument that explains WHY a result is true through a narrative, with no or minimal algebra. They appear when the student writes things like "Think of n trials..." or "Let c = E[X], then by starting over..." These are the most valuable cards in a probability deck.

**How to identify:** The solution is a 2-5 sentence narrative argument, not a series of equations.

**How to extract:**
- `item_type`: `proof`
- `problem_statement`: "Give a story proof that [result]. Do not use algebra."
- `solution_steps`: Write the narrative argument, preserving the student's language

**Example from the source — Geometric Expected Value story proof:**
- Problem: "Let X ~ Geom(p) count failures before the first success. Use a story argument — not series calculation — to find E[X]."
- Steps:
  1. Let c = E[X]. The first trial either succeeds or fails.
  2. With probability p: first trial succeeds, X = 0 failures. Contributes 0·p to E[X].
  3. With probability q: first trial fails. We've had 1 failure, then the process restarts identically. So E[X | first fails] = 1 + c.
  4. Therefore: c = 0·p + (1+c)·q → c = q + cq → c(1-q) = q → c = q/p.

**Example — Binomial sum story proof:**
- Problem: "X ~ Bin(n,p) and Y ~ Bin(m,p) are independent. Give a story proof that X+Y ~ Bin(n+m,p)."
- Steps:
  1. Think of n+m independent Bernoulli(p) trials.
  2. X = successes in first n trials, Y = successes in last m trials.
  3. X+Y = total successes in all n+m trials.
  4. By definition, this is Bin(n+m,p). ∎

When the source contains a story proof, prefer it over the algebraic approach.

---

## Indicator Variable Technique

This technique appears throughout the notes (5-card hand, linearity of expectation). It is a pattern worth extracting explicitly.

Pattern:
1. Define X = quantity of interest
2. Write X = X₁ + X₂ + ... + Xₙ where each Xⱼ is an indicator (0 or 1)
3. By linearity: E[X] = n·E[X₁]
4. E[X₁] = P(one specific event) — often much easier to compute

When a `[!Example]` block uses this technique, the card should ask the student to apply it:
- "Use indicator random variables to compute E[X]..."

---

## Deduplication Rules

**Same concept + same technique + different numbers = duplicate. Remove it.**
**Same concept + different technique = keep. They test different knowledge.**

For PMF verification, these are ALL different and worth keeping:
- Verify `f(x) = x/10` for `x ∈ {1,2,3,4}` — basic arithmetic, direct check
- Verify Binomial PMF — requires the Binomial Theorem `(p+q)^n = 1`
- Verify Geometric PMF — requires the geometric series `Σ q^k = 1/(1-q)`
- Verify Poisson PMF — requires the Taylor series for `e^λ`

Each demands a different mathematical tool. They are NOT duplicates.

These WOULD be duplicates (keep only one):
- Verify `f(x) = x/10` for `x ∈ {1,2,3,4}`
- Verify `f(x) = x/15` for `x ∈ {1,2,3,4,5}` ← same technique, different numbers

Ask: "Would a student who solved the first example know immediately how to solve this one without learning anything new?" If yes → duplicate. If no → keep.

**Source examples take priority over synthesized ones.** If the source has a Binomial PMF verification, use the source's version exactly (same n, p, formula). Do not synthesize a different distribution to represent the same technique.

---

## Self-Contained Problem Statements

Every problem_statement must define all variables. The student must be able to solve it without seeing anything else.

❌ "Find P(D|T) using Bayes."
✅ "A disease D affects 1% of the population (P(D)=0.01). A test T has sensitivity P(T|D)=0.95 and false-positive rate P(T|Dᶜ)=0.05. A patient tests positive. Find P(D|T)."

For problems taken from the source, copy the full setup — including variable definitions, the given probabilities, and the exact question asked.

---

## Solution Steps Quality

Steps should show the actual reasoning, not just name tools.

❌ "Step 1: Recall Bayes' theorem."
✅ "Step 1: Bayes' theorem gives P(D|T) = P(T|D)·P(D)/P(T). We know P(T|D) and P(D) but not P(T)."

❌ "Step 2: Use the law of total probability."
✅ "Step 2: P(T) = P(T|D)·P(D) + P(T|Dᶜ)·P(Dᶜ) = 0.95×0.01 + 0.05×0.99 = 0.059"

Each step must be a complete thought: what we're doing, why, and the calculation.

For story proofs: the steps are the story. Write them as sentences, not equations.

---

## Hints

A hint should give the student the first move — the insight that unlocks the problem — without doing any of the work.

❌ "Use Bayes' theorem." (names the tool — student already knows they need Bayes)
✅ "The challenge is finding P(T). Use the law of total probability to decompose it into P(T|D) and P(T|Dᶜ), both of which are given."

❌ "Use the indicator variable technique." (too vague)
✅ "Define Xⱼ as an indicator for the jth card being an ace. All 5 indicators have the same distribution by symmetry."

For story proofs:
✅ "Let c = E[X] and condition on the outcome of the first trial."

Leave hint empty when the problem statement itself provides enough structure — not every card needs a hint.

---

## LaTeX Rules

All math in `\(inline\)` or `\[display\]`. Never raw expressions.

Common patterns in these notes:
- Binomial coefficient: `\(\binom{n}{k}\)`
- PMF condition: `\(\sum_{x} P(X=x) = 1\)`
- Conditional probability: `\(P(A|B) = \frac{P(A \cap B)}{P(B)}\)`
- Expected value: `\(E(X) = \sum_x x \, P(X=x)\)`

---

## Item Type Targets

| Type | Min % | When |
|------|-------|------|
| solvable | 25% | Real worked examples from `[!Example]` blocks |
| proof / derivation | 25% | `[!check]`, `[!Proof]`, story proofs, derivations |
| application | 15% | Applying a theorem to a new scenario |
| definition / theorem | 35% | Named results with conditions |

Priority order: extract real examples first, synthesize only when none exist.

