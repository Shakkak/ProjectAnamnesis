"""
Agent 0 — Clarification.
Interactive two-step agent that refines a vague request into a precise Deck Spec.

Step 1: Generate 0-5 targeted questions based on what's ambiguous in the request.
Step 2: After collecting user answers, synthesize a complete Deck Spec JSON.

The Deck Spec is the shared contract that all downstream agents read.
"""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.json"

_AVAILABLE_TEMPLATES = """
Available templates (pick the best fit, or "new" if none match):
  reveal-interview  — ML/CV/AI/NLP interview prep; dark navy; multi-field reveal cards
  reveal-stats      — Mathematics/statistics; slate blue; derivation left-border panels
  reveal-speaking   — Language speaking practice; coral/amber; sample response blocks
  toefl-email       — Email/essay writing tasks; green; email-paper layout
  toefl-fill        — Academic cloze/fill-in-blank; purple; highlighted blanks
  toefl-listen      — Listen and repeat; blue; audio-first (only when audio files exist)
  vocab             — Vocabulary learning; teal; typing input with diff, RTL support
"""

_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":      {"type": "string"},
                    "text":    {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "text"],
            },
        }
    },
    "required": ["questions"],
}

_AGENT_CHECKLISTS_SCHEMA = {
    "type": "object",
    "properties": {
        "extraction": {"type": "string"},
        "design":     {"type": "string"},
        "writing":    {"type": "string"},
        "review":     {"type": "string"},
    },
    "required": ["extraction", "design", "writing", "review"],
}

_DECK_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose":                   {"type": "string"},
        "audience_level":            {"type": "string"},
        "domain":                    {"type": "string"},
        "section_hints":             {"type": "array", "items": {"type": "string"}},
        "card_type":                 {"type": "string"},
        "audio_needed":              {"type": "boolean"},
        "target_card_count":         {"type": "integer"},
        "depth":                     {"type": "string"},
        "language":                  {"type": "string"},
        "bilingual_prompt_language": {},
        "source":                    {"type": "string"},
        "template_id":               {"type": "string"},
        "template_new":              {"type": "boolean"},
        "template_requirements":     {},
        "agent_checklists":          _AGENT_CHECKLISTS_SCHEMA,
    },
    "required": [
        "purpose", "audience_level", "domain", "section_hints",
        "card_type", "audio_needed", "target_card_count", "depth",
        "language", "source", "template_id", "template_new",
        "agent_checklists",
    ],
}


def _load_prompts() -> dict:
    return json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))


def _generate_questions(prompt_text: str, file_info: str, client) -> list[dict]:
    prompts = _load_prompts()
    system = prompts["question_generator"] + "\n\n" + _AVAILABLE_TEMPLATES
    user_msg = f"User request: {prompt_text}"
    if file_info:
        user_msg += f"\n\nFile provided: {file_info}"

    raw = client.generate_json(
        user_msg,
        system=system,
        schema=_QUESTIONS_SCHEMA,
        temperature=0.2,
        max_tokens=800,
    )
    return json.loads(raw).get("questions", [])


def _synthesize_spec(
    prompt_text: str,
    file_info: str,
    questions: list[dict],
    answers: dict[str, str],
    client,
) -> dict:
    prompts = _load_prompts()
    system = prompts["spec_synthesizer"] + "\n\n" + _AVAILABLE_TEMPLATES

    qa_block = ""
    for q in questions:
        answer = answers.get(q["id"], "(not answered)")
        qa_block += f"\nQ: {q['text']}\nA: {answer}\n"

    user_msg = f"Original request: {prompt_text}"
    if file_info:
        user_msg += f"\nFile provided: {file_info}"
    if qa_block:
        user_msg += f"\n\nClarification Q&A:{qa_block}"

    raw = client.generate_json(
        user_msg,
        system=system,
        schema=_DECK_SPEC_SCHEMA,
        temperature=0,
        max_tokens=1800,
    )
    return json.loads(raw)


def run_clarification(
    prompt_text: str,
    client,
    file_info: str = "",
) -> dict:
    """
    Run interactive clarification. Returns a complete Deck Spec dict.

    file_info: human-readable description of the input file, e.g. "notes.pdf (PDF, 340 KB)".
               Empty string when no file is provided.
    """
    log.info("Agent 0: generating clarification questions...")
    questions = _generate_questions(prompt_text, file_info, client)

    answers: dict[str, str] = {}

    if questions:
        print("\n── Deck Design ────────────────────────────────────────────")
        print(f"  {prompt_text[:120]}{'…' if len(prompt_text) > 120 else ''}\n")
        print("  A few questions before I start (press Enter to skip any):\n")

        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q['text']}")
            options = q.get("options") or []
            if options:
                for j, opt in enumerate(options, 1):
                    print(f"     {j}) {opt}")
                raw = input("  > ").strip()
                if raw.isdigit() and 1 <= int(raw) <= len(options):
                    answers[q["id"]] = options[int(raw) - 1]
                elif raw:
                    answers[q["id"]] = raw
            else:
                raw = input("  > ").strip()
                if raw:
                    answers[q["id"]] = raw
            print()

        print("────────────────────────────────────────────────────────────\n")
    else:
        log.info("Agent 0: request is specific enough — no questions needed")

    log.info("Agent 0: synthesizing Deck Spec...")
    deck_spec = _synthesize_spec(prompt_text, file_info, questions, answers, client)
    checklists = deck_spec.get("agent_checklists") or {}
    log.info(
        f"Agent 0: spec → domain={deck_spec.get('domain')}, "
        f"cards={deck_spec.get('target_card_count')}, "
        f"template={deck_spec.get('template_id')}, "
        f"audio={deck_spec.get('audio_needed')}, "
        f"source={deck_spec.get('source')}, "
        f"checklists={'yes' if checklists else 'missing'}"
    )
    return deck_spec
