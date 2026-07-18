# Programming / Computer Science Flashcard Guide

## Multiple Cards Per Concept

1. **Definition** (qa) — "What is a hash table?" — conceptual understanding
2. **Complexity** (mchoice) — "Time complexity of binary search?" → O(log n)
3. **Application** (qa) — "When would you use a heap instead of a sorted list?"
4. **Trace / Output** (qa or mchoice) — "What does this snippet output?" — include code in `details`
5. **API / Signature** (qa) — "What arguments does `sorted()` take?" — for library knowledge
6. **Distinction** (mchoice) — "Which is O(n log n): bubble sort, merge sort, or insertion sort?"

Generate complexity cards (mchoice) for every algorithm or data structure that has a non-trivial complexity.

## Code in Fields

- Put code snippets in `details` using Markdown code fences: ```python ... ```
- `core_fact` and `answer` should be plain text — no code blocks
- For "what does this output" cards: put the snippet in `details`, the output in `answer`

## Distractors for Complexity

Always use the standard Big-O options as distractors:
- O(1), O(log n), O(n), O(n log n), O(n²), O(2ⁿ), O(n!)
- Pick the ones a student would realistically confuse with the correct answer

## Algorithm Cards

- `core_fact`: what the algorithm does and its complexity
- `details`: step-by-step description or pseudocode
- `examples`: a small concrete trace (e.g., sorting [3,1,2])
- `common_mistakes`: off-by-one in bounds, forgetting base cases, mutating while iterating

## Difficulty

- **easy**: definition of a basic data structure, syntax of a common built-in
- **medium**: choosing the right data structure, reading a short snippet, O(n log n) vs O(n²)
- **hard**: amortized analysis, proving correctness, combining multiple concepts (e.g., Dijkstra's correctness proof)
