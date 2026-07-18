# Language Learning Flashcard Guide

## Multiple Cards Per Word/Concept

Vocabulary benefits from multiple angles:
1. **L1 → L2** (qa) — "English word for 'Schadenfreude'?" — tests production
2. **L2 → L1** (qa) — "What does 'Schadenfreude' mean?" — tests recognition
3. **In-context** (cloze) — fill the word into a natural sentence
4. **Grammar form** (qa or cloze) — conjugation, plural, gender, case

Generate both directions (L1→L2 and L2→L1) for every vocabulary item.

## RTL / LTR Direction

For decks where a field contains **right-to-left script** (Persian, Arabic, Hebrew, Urdu):

- Add `"direction": "rtl"` to that field's definition in the card type JSON. The generator automatically wraps the rendered value in `<bdi dir="rtl" style="display:block;text-align:right;">`. No change to card data is needed.
- For **inline** RTL text appearing inside a field that is otherwise LTR (e.g., a Persian word embedded in an English `details` string), wrap only that portion with `<bdi dir="rtl">` in the card JSON value:
  ```
  🇮🇷  <bdi dir="rtl">متن فارسی</bdi>
  ```
- Use `"direction": "ltr"` to explicitly force left-to-right in an otherwise RTL context.
- Full reference: `docs/CONTENT_STRUCTURE.md §2.6`.

## Audio

If a field has audio enabled, the `core_fact` or `answer` should contain the word in isolation (no extra punctuation) so TTS speaks it cleanly.

## Word Entries

- `core_fact`: the translation or definition — keep it concise
- `details`: gender/article (for gendered languages), register (formal/informal), etymology if memorable
- `examples`: 1–2 natural sentences using the word in context
- `common_mistakes`: false friends, words with similar spelling but different meaning, common mispronunciation
- `hints`: etymology, mnemonic, or sound-alike in L1
- `distractors`: words with similar form, sound, or meaning — not random vocabulary

## Grammar Rules

- Use cloze cards for conjugation patterns: "Ich {{gehe}} jeden Tag spazieren."
- State the rule in `core_fact`, give an example in `examples`, and list exceptions in `details`
- For irregular forms: one card per irregularity is better than one card listing all

## Difficulty

- **easy**: high-frequency vocabulary (top 500 words), basic greetings, numbers
- **medium**: common vocabulary, regular grammar patterns
- **hard**: idiomatic expressions, irregular forms, register distinctions, false friends
