import hashlib
import logging
import random
import re
import unicodedata
from pathlib import Path

import genanki

log = logging.getLogger(__name__)

_BUNDLED_TEMPLATE_DIR = Path(__file__).parent / "templates"
_USER_TEMPLATE_DIR: Path | None = Path(__file__).parent.parent / "content" / "templates"
_THEMES_DIR = Path(__file__).parent / "themes"
_active_theme: str | None = None


def set_bank_path(bank: Path) -> None:
    """Override user template directory to an explicit external data root."""
    global _USER_TEMPLATE_DIR
    _USER_TEMPLATE_DIR = bank / "templates"


def set_theme(name: str | None) -> None:
    global _active_theme
    _active_theme = name


def _load_theme_css() -> str:
    if not _active_theme:
        return ""
    path = _THEMES_DIR / f"{_active_theme}.css"
    if not path.exists():
        available = sorted(p.stem for p in _THEMES_DIR.glob("*.css"))
        raise FileNotFoundError(
            f"Theme '{_active_theme}' not found. Available: {', '.join(available)}"
        )
    return path.read_text(encoding="utf-8")

# All implemented roles
_VALID_ROLES = {"question", "answer", "extra", "choices", "image", "audio_override", "cloze"}
_PLANNED_ROLES: set[str] = set()


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def _load_card_templates(type_id: str) -> tuple[str, str, str]:
    """Load front.html, back.html, style.css. Checks content/templates/ first, then generator/templates/."""
    candidates = []
    if _USER_TEMPLATE_DIR is not None:
        candidates.append(_USER_TEMPLATE_DIR / type_id)
    candidates.append(_BUNDLED_TEMPLATE_DIR / type_id)
    for d in candidates:
        if (d / "front.html").exists():
            return (
                (d / "front.html").read_text(encoding="utf-8"),
                (d / "back.html").read_text(encoding="utf-8"),
                (d / "style.css").read_text(encoding="utf-8"),
            )
    raise FileNotFoundError(f"No template found for card type '{type_id}' in {candidates}")


def _strip_unused_blocks(html: str, model_fields: list[str]) -> str:
    """Remove {{#Field}}...{{/Field}} blocks for fields not present in the model."""
    for m in re.findall(r'\{\{#([^}]+)\}\}', html):
        if m not in model_fields:
            html = re.sub(
                r'\{\{#' + re.escape(m) + r'\}\}.*?\{\{/' + re.escape(m) + r'\}\}',
                '', html, flags=re.DOTALL
            )
    return html


# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

def _stable_id(seed: str) -> int:
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


_QUESTION_FIELDS = ("question", "front", "text", "cloze")

_LEVEL_COLORS = {
    "fundamental":  "#2e7d32",
    "intermediate": "#1565c0",
    "advanced":     "#e65100",
    "cross-topic":  "#6a1b9a",
}


def _level_badge(level: str) -> str:
    color = _LEVEL_COLORS.get(level.lower(), "#555")
    return (
        f'<span style="display:inline-block;background:{color};color:#fff;'
        f'padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;'
        f'letter-spacing:0.5px;">{level.upper()}</span><br>'
    )


def _card_guid(section: str, card: dict) -> str:
    """Return the card's explicit id, or compute a stable one from section + question.

    Matches the formula in tools/stamp_card_ids.py so that cards stamped by
    that script produce the same GUID here even if the id field is absent.
    """
    if card.get("id"):
        return str(card["id"])
    question = ""
    for f in _QUESTION_FIELDS:
        question = str(card.get(f, "")).strip()
        if question:
            break
    seed = f"{section}|||{question[:120]}"
    return hashlib.md5(seed.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-model dynamic field lists
# ---------------------------------------------------------------------------

def _build_memrise_fields(ct_def: dict) -> list[str]:
    """
    [Learnable, Definition, Extra, Extra 2?, ..., Choices]
    Minimum one Extra slot regardless of defined extra fields.
    """
    n_extras = max(sum(1 for fd in ct_def["fields"] if fd["role"] == "extra"), 1)
    fields = ["Learnable", "Definition"]
    for i in range(n_extras):
        fields.append("Extra" if i == 0 else f"Extra {i + 1}")
    fields.append("Choices")
    return fields


def _build_cloze_fields(ct_def: dict) -> list[str]:
    """
    [Text, Extra?, Extra 2?, ..., Choices, Audio]
    """
    n_extras = sum(1 for fd in ct_def["fields"] if fd["role"] == "extra")
    fields = ["Text"]
    for i in range(n_extras):
        fields.append("Extra" if i == 0 else f"Extra {i + 1}")
    fields.extend(["Choices", "Audio"])
    return fields


# ---------------------------------------------------------------------------
# Cloze conversion
# ---------------------------------------------------------------------------

def _convert_cloze(text: str) -> str:
    """Convert {{word}} markers to Anki cloze syntax {{c1::word}}, {{c2::...}}.

    Uses a lookahead (?!}) so that a LaTeX closing brace that immediately
    precedes the cloze-close marker (e.g. {{\\frac{a}{b}}}) is not mistaken
    for the closing '}}'. Content may contain '{' and '}' (LaTeX braces).
    """
    ordinal = 0

    def replace(m: re.Match) -> str:
        nonlocal ordinal
        ordinal += 1
        return "{{" + f"c{ordinal}::{m.group(1)}" + "}}"

    return re.sub(r"\{\{(?!c\d+::)(.*?)\}\}(?!\})", replace, text, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

_PROVIDER_CACHE: dict = {}


def _resolve_provider(ct_def: dict):
    """Return the TTS provider function declared in the card type's tts.provider field."""
    provider_name = ct_def.get("tts", {}).get("provider", "kokoro")
    if provider_name not in _PROVIDER_CACHE:
        from tts.kokoro_provider import generate_audio as _fn
        _PROVIDER_CACHE[provider_name] = _fn
    return _PROVIDER_CACHE[provider_name]


def _audio_filename(text: str, field_name: str, lang: str) -> str:
    """Content-hash filename — same text+language always maps to the same file."""
    content_hash = hashlib.md5(f"{lang}:{text}".encode()).hexdigest()[:10]
    safe_field   = re.sub(r"[^a-z0-9]", "_", field_name.lower())[:20]
    return f"{safe_field}_{content_hash}.mp3"


def _primary_text(text: str) -> str:
    """Strip alternatives — return only the first answer option."""
    return text.split(" ; ")[0].strip()


def _field_tts_lang(fd: dict, ct_def: dict) -> str:
    return fd.get("tts_language") or ct_def.get("tts", {}).get("language", "en")


# ---------------------------------------------------------------------------
# genanki model builder
# ---------------------------------------------------------------------------

def _slug_filename(text: str) -> str:
    """Mirrors colab_build.py _word_audio_filename — must stay in sync."""
    w = unicodedata.normalize("NFD", text)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", w.strip().lower()).strip("_")
    return f"{slug}.mp3"


def _build_listen_fields() -> list[str]:
    return ["Sentence", "Audio"]


def _map_to_listen_fields(card: dict, ct_def: dict) -> list[str]:
    sentence = ""
    audio_fname = ""
    for fd in ct_def["fields"]:
        if fd["role"] == "answer":
            sentence = str(card.get(fd["name"], "")).strip()
        elif fd["role"] == "audio_override":
            audio_fname = str(card.get(fd["name"], "")).strip()
    if not audio_fname and sentence:
        audio_fname = _slug_filename(sentence)
    audio = f"[sound:{audio_fname}]" if audio_fname else ""
    return [sentence, audio]


def _build_model(type_id: str, ct_def: dict) -> genanki.Model:
    front, back, css = _load_card_templates(type_id)
    theme = _load_theme_css()
    if theme:
        css = css + "\n\n/* === theme override === */\n" + theme

    is_listen = any(t.get("mode") == "listen" for t in ct_def["templates"])
    if is_listen:
        return genanki.Model(
            model_id=_stable_id(f"model:{type_id}"),
            name=type_id,
            fields=[{"name": f} for f in _build_listen_fields()],
            templates=[{"name": "Listen & Repeat", "qfmt": front, "afmt": back}],
            css=css,
        )

    is_cloze = any(t.get("mode") == "cloze" for t in ct_def["templates"])
    if is_cloze:
        cloze_fields = _build_cloze_fields(ct_def)
        back_stripped = _strip_unused_blocks(back, cloze_fields)
        return genanki.Model(
            model_id=_stable_id(f"model:{type_id}"),
            name=type_id,
            fields=[{"name": f} for f in cloze_fields],
            templates=[{"name": "Cloze", "qfmt": front, "afmt": back_stripped}],
            css=css,
            model_type=genanki.Model.CLOZE,
        )

    # Standard typing / reveal model
    memrise_fields = _build_memrise_fields(ct_def)
    back_stripped  = _strip_unused_blocks(back, memrise_fields)
    templates = [
        {"name": tmpl["name"], "qfmt": front, "afmt": back_stripped}
        for tmpl in ct_def["templates"]
    ]
    return genanki.Model(
        model_id=_stable_id(f"model:{type_id}"),
        name=type_id,
        fields=[{"name": f} for f in memrise_fields],
        templates=templates,
        css=css,
    )


# ---------------------------------------------------------------------------
# Choices auto-fill pool
# ---------------------------------------------------------------------------

def _build_choices_pool(sections: list[dict], registry: dict) -> dict[str, list[str]]:
    """
    Collect primary answer values per section.
    Used to auto-fill the `choices` field when it is left empty on mchoice cards.
    """
    pool: dict[str, list[str]] = {}
    for section in sections:
        answers: list[str] = []
        for card in section["cards"]:
            ct_def = registry.get(card.get("card_type", ""), {})
            for fd in ct_def.get("fields", []):
                if fd["role"] == "answer":
                    raw = str(card.get(fd["name"], "")).strip()
                    if raw:
                        answers.append(_primary_text(raw))
        pool[section["name"]] = answers
    return pool


# ---------------------------------------------------------------------------
# Field mapping: card data → Memrise template slots
# ---------------------------------------------------------------------------

def _map_to_memrise_fields(
    card: dict,
    ct_def: dict,
    choices_pool: list[str] | None = None,
    n_choices: int = 5,
) -> list[str]:
    """
    Maps card data to Memrise template slots:
      [Learnable, Definition, Extra, ..., Choices]

    Role mapping:
      question       → Definition
      answer         → Learnable  (+ [sound:] tag if audio=true)
      extra          → Extra slots in definition order
      choices        → Choices    (auto-filled from pool if empty and mchoice exists)
      image          → prepended to Definition as <img>
      audio_override → [sound:filename] appended to Definition
    """
    memrise_fields = _build_memrise_fields(ct_def)
    n_extras       = len(memrise_fields) - 3  # Learnable + Definition + Choices = 3 fixed
    field_defs     = {fd["name"]: fd for fd in ct_def["fields"]}
    has_mchoice    = any(t.get("mode") == "mchoice" for t in ct_def["templates"])

    question       = ""
    answer         = ""
    answer_primary = ""
    extras: list[str] = []
    choices        = ""

    for field_name, fd in field_defs.items():
        role = fd["role"]
        raw  = str(card.get(field_name, "")).strip()
        if not raw:
            continue

        value = raw
        if fd.get("latex"):
            value = _dollar_to_mathjax(value)
        if role in ("question", "answer", "extra"):
            value = _markdown_to_html(value)
        if fd.get("audio") and role != "audio_override":
            tts_text = _primary_text(raw)
            lang     = _field_tts_lang(fd, ct_def)
            fname    = _audio_filename(tts_text, field_name, lang)
            value    = f"{value} [sound:{fname}]"

        if role == "question":
            question = value
        elif role == "answer":
            answer_primary = _primary_text(raw)
            answer         = value
        elif role == "extra":
            extras.append(value)
        elif role == "choices":
            choices = value
        elif role == "image":
            img_tag  = f'<img src="{raw}">'
            question = img_tag + (f"<br>{question}" if question else "")
        elif role == "audio_override":
            # autoplay:true (default) → sound in question field, plays on card front
            # autoplay:false          → sound in answer field, plays on back reveal
            sound_tag = f"[sound:{raw}]"
            if fd.get("autoplay", True):
                question = f"{question} {sound_tag}" if question else sound_tag
            else:
                answer = f"{answer} {sound_tag}" if answer else sound_tag

    # Auto-fill choices when: empty, mchoice template exists, and pool is available
    if not choices and has_mchoice and choices_pool and answer_primary:
        distractors = [p for p in choices_pool if p != answer_primary]
        sample_n    = min(n_choices, len(distractors))
        if sample_n >= 1:
            choices = "|".join(random.sample(distractors, sample_n))
            log.debug(f"  auto-filled {sample_n} choices")
        else:
            log.warning("  not enough sibling cards to auto-fill choices")

    if ct_def.get("level_badge"):
        level = str(card.get("level", "")).strip().lower()
        if level and level in _LEVEL_COLORS:
            question = _level_badge(level) + question

    while len(extras) < n_extras:
        extras.append("")

    return [answer, question] + extras[:n_extras] + [choices]


def _map_to_cloze_fields(
    card: dict,
    ct_def: dict,
    choices_pool: list[str] | None = None,
    n_choices: int = 5,
) -> list[str]:
    """
    Maps card data to cloze template slots:
      [Text, Extra?, ..., Choices, Audio]

    Role mapping:
      cloze          → Text  ({{word}} converted to {{c1::word}})
      extra          → Extra slots in definition order
      choices        → Choices
      audio_override → Audio as [sound:filename]
    """
    cloze_fields = _build_cloze_fields(ct_def)
    n_extras     = len(cloze_fields) - 3  # Text + Choices + Audio = 3 fixed

    text   = ""
    extras: list[str] = []
    choices = ""
    audio   = ""

    for fd in ct_def["fields"]:
        role = fd["role"]
        raw  = str(card.get(fd["name"], "")).strip()
        if not raw:
            continue

        if role == "cloze":
            text = _convert_cloze(raw)
        elif role == "extra":
            extras.append(_markdown_to_html(raw))
        elif role == "choices":
            choices = raw
        elif role == "audio_override":
            audio = f"[sound:{raw}]"

    if not choices and choices_pool:
        sample_n = min(n_choices, len(choices_pool))
        if sample_n >= 1:
            choices = "|".join(random.sample(choices_pool, sample_n))

    while len(extras) < n_extras:
        extras.append("")

    return [text] + extras[:n_extras] + [choices, audio]


# ---------------------------------------------------------------------------
# Audio generation pass
# ---------------------------------------------------------------------------

def generate_audio(
    sections: list[dict],
    registry: dict,
    tts_provider=None,
    audio_out_dir: Path = Path("output/audio"),
    force_regen: bool = False,
    voice_override: str | None = None,
) -> None:
    """
    Generate TTS audio for every field with audio=true.

    tts_provider: explicit callable to use for all card types.  When None
    (the default), the provider is resolved per card type from the card
    type definition's ``tts.provider`` field (e.g. "kokoro").
    """
    from tqdm import tqdm

    audio_out_dir.mkdir(parents=True, exist_ok=True)

    # Collect all (card, ct_def, field_def) triples that need synthesis so
    # we can show a single progress bar across all sections.
    work = []
    for section in sections:
        for card in section["cards"]:
            ct_def     = registry[card["card_type"]]
            field_defs = {fd["name"]: fd for fd in ct_def["fields"]}
            for field_name, fd in field_defs.items():
                if not fd.get("audio") or fd["role"] in _PLANNED_ROLES:
                    continue
                raw = str(card.get(field_name, "")).strip()
                if not raw:
                    continue
                tts_text = _primary_text(raw)
                lang     = _field_tts_lang(fd, ct_def)
                fname    = _audio_filename(tts_text, field_name, lang)
                out_path = audio_out_dir / fname
                if out_path.exists() and not force_regen:
                    continue
                work.append((card, ct_def, field_name, fd, tts_text, lang, fname, out_path))

    if not work:
        log.info("  audio: all files present, nothing to generate.")
        return

    bar = tqdm(work, unit="file", desc="Generating audio")
    for card, ct_def, field_name, fd, tts_text, lang, fname, out_path in bar:
        bar.set_postfix_str(fname[:40])
        provider = tts_provider if tts_provider is not None else _resolve_provider(ct_def)
        voice    = voice_override or ct_def.get("tts", {}).get("voice", "")
        extra    = {"voice": voice} if voice else {}
        provider(text=tts_text, output_path=str(out_path), lang=lang, **extra)


# ---------------------------------------------------------------------------

def _dollar_to_mathjax(text: str) -> str:
    """Convert $...$ and $$...$$ to Anki MathJax delimiters \(...\) and \[...\]."""
    # Display math first so the inner $ chars are already consumed
    text = re.sub(r'\$\$(.+?)\$\$', r'\\[\1\\]', text, flags=re.DOTALL)
    text = re.sub(r'\$([^$\n]+?)\$', r'\\(\1\\)', text)
    return text


def _markdown_to_html(text: str) -> str:
    """Convert markdown formatting to HTML for Anki field rendering.

    Handles: tables, bold/italic, bullet/numbered lists, code blocks, inline
    code, and blockquotes. Protects existing LaTeX delimiters \\[...\\] and
    \\(...\\) from markdown processing.
    """
    # ── 1. Protect LaTeX so the markdown passes don't mangle it ──────────────
    placeholders: list[str] = []

    def _save(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00LATEX{len(placeholders) - 1}\x00"

    text = re.sub(r'\\\[.+?\\\]', _save, text, flags=re.DOTALL)
    text = re.sub(r'\\\(.+?\\\)', _save, text)

    # ── 2. Fenced code blocks ─────────────────────────────────────────────────
    def _fenced_code(m: re.Match) -> str:
        code = m.group(2).rstrip()
        return f'<pre><code>{code}</code></pre>'

    text = re.sub(r'```(\w*)\n(.*?)```', _fenced_code, text, flags=re.DOTALL)

    # ── 3. Markdown tables ────────────────────────────────────────────────────
    def _table(m: re.Match) -> str:
        raw_lines = [l for l in m.group(0).strip().split('\n') if l.strip()]
        if len(raw_lines) < 2:
            return m.group(0)
        header_line = raw_lines[0]
        # raw_lines[1] is the separator (---|---), skip it
        body_lines = raw_lines[2:]

        cell_style = 'style="border:1px solid #888;padding:4px 8px;text-align:left;color:inherit"'
        th_style   = 'style="border:1px solid #888;padding:4px 8px;text-align:left;background:#4a4a4a;color:#ffffff"'

        def _cells(line: str, tag: str) -> str:
            style = th_style if tag == 'th' else cell_style
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            return '<tr>' + ''.join(f'<{tag} {style}>{c}</{tag}>' for c in cells) + '</tr>'

        html = '<table style="border-collapse:collapse;margin:6px 0;font-size:0.9em">'
        html += '<thead>' + _cells(header_line, 'th') + '</thead>'
        html += '<tbody>'
        for row in body_lines:
            if row.strip():
                html += _cells(row, 'td')
        html += '</tbody></table>'
        return html

    # Match a header row | ... | followed by a separator row |---|---| followed by data rows
    text = re.sub(
        r'(?m)^(\|.+\|\n\|[\s|:\-]+\|\n(?:\|.+\|?\n?)*)',
        _table,
        text,
    )

    # ── 4. Inline code ────────────────────────────────────────────────────────
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)

    # ── 5. Bold and italic ────────────────────────────────────────────────────
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', text)

    # ── 6. Bullet lists (lines starting with - or *) ──────────────────────────
    def _bullet_list(m: re.Match) -> str:
        items = re.findall(r'^[-*]\s+(.+)', m.group(0), re.MULTILINE)
        return '<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>'

    text = re.sub(r'(?m)(?:^[-*]\s+.+\n?)+', _bullet_list, text)

    # ── 7. Numbered lists ─────────────────────────────────────────────────────
    def _numbered_list(m: re.Match) -> str:
        items = re.findall(r'^\d+\.\s+(.+)', m.group(0), re.MULTILINE)
        return '<ol>' + ''.join(f'<li>{i}</li>' for i in items) + '</ol>'

    text = re.sub(r'(?m)(?:^\d+\.\s+.+\n?)+', _numbered_list, text)

    # ── 8. Blockquotes ────────────────────────────────────────────────────────
    text = re.sub(r'(?m)^>\s?(.+)', r'<blockquote>\1</blockquote>', text)

    # ── 9. Line breaks (must come after block-level conversions) ──────────────
    text = text.replace('\n\n', '<br><br>')
    text = text.replace('\n', '<br>')

    # ── 10. Restore LaTeX ────────────────────────────────────────────────────
    for i, block in enumerate(placeholders):
        text = text.replace(f'\x00LATEX{i}\x00', block)

    return text


# ---------------------------------------------------------------------------
# Vault reference footer injection (Track C)
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "and", "or", "but", "not",
    "it", "its", "this", "that", "with", "from", "how", "what", "why",
    "when", "do", "does", "can", "will", "which", "by", "as", "if",
}


def _keyword_overlap(question: str, section_header: str) -> int:
    def tokens(text):
        words = re.findall(r"[a-z]+", text.lower())
        return {w for w in words if w not in _STOPWORDS and len(w) > 2}

    return len(tokens(question) & tokens(section_header))


def _vault_footer(card: dict, vault_index: dict) -> str:
    """Return an HTML vault-ref footer string, or '' if no source_nodes."""
    slugs = card.get("source_nodes", [])
    if not slugs:
        return ""

    question = card.get("question", "")
    lines = []
    for slug in slugs:
        # Find vault path for slug
        path = next((p for p in vault_index if p.split("/")[-1].replace(".md", "") == slug), None)
        if path is None:
            continue
        sections = vault_index[path].get("sections", [])
        h2_sections = [s["header"] for s in sections]
        matched = [h for h in h2_sections if _keyword_overlap(question, h) >= 2]
        if not matched:
            matched = []  # fallback: just link file, no section
        section_str = " · ".join(f"§{h}" for h in matched[:3]) if matched else ""
        line = f"vault/{path}"
        if section_str:
            line += f" — {section_str}"
        lines.append(line)

    if not lines:
        return ""

    refs = "<br>".join(lines)
    return f'<div class="vault-ref">📖 <strong>Further reading:</strong><br>{refs}</div>'


# ---------------------------------------------------------------------------
# Deck build pass
# ---------------------------------------------------------------------------

def build_retired_deck(
    deck_config: dict,
    retired_ids: list[str],
    bank_path: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    """Build a minimal .apkg that tags each retired card with __retired.

    Import this into Anki, then search tag:__retired → select all → delete.
    Only works if the cards still exist in your Anki collection (same GUID).
    """
    if not retired_ids:
        log.info("No retired IDs — nothing to build.")
        return

    registry  = deck_config["_registry"]
    deck_name = deck_config["deck_name"]
    deck_dir  = Path(deck_config["_deck_dir"])

    out_field = deck_config["output"]
    if output_dir and not Path(out_field).parent.parts:
        # Filename-only (bank mode): resolve against output_dir
        main_output = (output_dir / out_field).resolve()
    else:
        # Relative path in deck.json (standalone mode): resolve against deck dir
        main_output = (deck_dir / out_field).resolve()
    output = main_output.with_name(main_output.stem + "-retired.apkg")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Use the first registered model — just needs to match the original card type
    ct_id  = next(iter(registry))
    ct_def = registry[ct_id]
    model  = _build_model(ct_id, ct_def)

    # Build placeholder fields for the model (all slots must be present)
    memrise_fields = _build_memrise_fields(ct_def)
    placeholder_fields = ["[RETIRED — safe to delete]"] + [""] * (len(memrise_fields) - 1)

    deck = genanki.Deck(deck_id=_stable_id(f"deck:{deck_name}::__retired"), name=f"{deck_name}::__retired")
    for rid in retired_ids:
        note = genanki.Note(
            model=model,
            fields=placeholder_fields,
            tags=["__retired"],
            guid=str(rid),
        )
        deck.add_note(note)

    pkg = genanki.Package([deck])
    pkg.write_to_file(str(output))
    log.info(f"✅ {len(retired_ids)} retired note(s) → {output}")
    log.info("Import into Anki, then: Browse → search 'tag:__retired' → select all → delete.")


def build_deck(
    deck_config: dict,
    sections: list[dict],
    audio_out_dir: Path = Path("output/audio"),
    bank_path: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    registry  = deck_config["_registry"]
    deck_name = deck_config["deck_name"]
    deck_dir  = Path(deck_config["_deck_dir"])
    sub_decks = deck_config.get("sub_decks", True)

    out_field = deck_config["output"]
    if output_dir and not Path(out_field).parent.parts:
        # Filename-only (bank mode): resolve against output_dir
        output = (output_dir / out_field).resolve()
    else:
        # Relative path in deck.json (standalone mode): resolve against deck dir
        output = (deck_dir / out_field).resolve()

    output.parent.mkdir(parents=True, exist_ok=True)

    # Load vault index once for reference footer injection
    if bank_path:
        vault_index_path = bank_path / "vault" / "index.json"
    else:
        vault_index_path = deck_dir.parent.parent / "vault" / "index.json"
    vault_index: dict = {}
    if vault_index_path.exists():
        import json as _json
        with open(vault_index_path) as _f:
            vault_index = _json.load(_f)
    else:
        log.warning("vault/index.json not found — vault reference footers disabled")

    # Build one genanki Model per card type — each loads its own template
    models: dict[str, genanki.Model] = {}
    for ct_id, ct_def in registry.items():
        models[ct_id] = _build_model(ct_id, ct_def)
        is_cloze  = any(t.get("mode") == "cloze"  for t in ct_def["templates"])
        is_listen = any(t.get("mode") == "listen" for t in ct_def["templates"])
        if is_listen:
            n_fields = len(_build_listen_fields())
            tag = " [listen]"
        elif is_cloze:
            n_fields = len(_build_cloze_fields(ct_def))
            tag = " [cloze]"
        else:
            n_fields = len(_build_memrise_fields(ct_def))
            tag = ""
        log.info(f"  model: {ct_id}  {len(ct_def['templates'])} template(s), {n_fields} field(s){tag}")

    # Pre-compute choices distractor pool per section
    choices_pool_by_section = _build_choices_pool(sections, registry)

    package     = genanki.Package([])
    media_files: list[str] = []
    total_notes = 0

    for section in sections:
        section_name = section["name"]
        cards        = section["cards"]
        section_pool = choices_pool_by_section.get(section_name, [])

        subdeck_name = f"{deck_name}::{section_name}" if sub_decks else deck_name
        subdeck      = genanki.Deck(
            deck_id=_stable_id(f"deck:{subdeck_name}"),
            name=subdeck_name,
        )

        for card in cards:
            ct_id  = card["card_type"]
            ct_def = registry[ct_id]
            model  = models[ct_id]

            # Inject vault reference footer into steps field
            if vault_index and card.get("source_nodes"):
                footer = _vault_footer(card, vault_index)
                if footer:
                    card = dict(card)  # shallow copy — don't mutate source
                    existing_steps = card.get("steps", "")
                    card["steps"] = (existing_steps + footer) if existing_steps else footer

            is_cloze  = any(t.get("mode") == "cloze"  for t in ct_def["templates"])
            is_listen = any(t.get("mode") == "listen" for t in ct_def["templates"])
            if is_listen:
                fields = _map_to_listen_fields(card, ct_def)
            elif is_cloze:
                fields = _map_to_cloze_fields(card, ct_def, choices_pool=section_pool)
            else:
                fields = _map_to_memrise_fields(card, ct_def, choices_pool=section_pool)

            # Validate field count matches model before creating Note
            expected = len(model.fields)
            if len(fields) != expected:
                log.error(
                    f"  field count mismatch for type '{ct_id}': "
                    f"got {len(fields)}, model expects {expected} — card skipped"
                )
                continue

            # Collect TTS audio media
            for fd in ct_def["fields"]:
                if not fd.get("audio") or fd["role"] == "audio_override":
                    continue
                raw = str(card.get(fd["name"], "")).strip()
                if not raw:
                    continue
                fname      = _audio_filename(_primary_text(raw), fd["name"], _field_tts_lang(fd, ct_def))
                audio_path = audio_out_dir / fname
                if audio_path.exists():
                    media_files.append(str(audio_path))

            # Collect image media
            for fd in ct_def["fields"]:
                if fd["role"] != "image":
                    continue
                img_file = str(card.get(fd["name"], "")).strip()
                if not img_file:
                    continue
                img_path = deck_dir / "media" / img_file
                if img_path.exists():
                    media_files.append(str(img_path))
                else:
                    log.warning(f"  image not found: {img_path}")

            # Collect audio_override media
            for fd in ct_def["fields"]:
                if fd["role"] != "audio_override":
                    continue
                audio_file = str(card.get(fd["name"], "")).strip()
                if not audio_file:
                    # Auto-slug from answer field (mirrors colab_build.py)
                    ans_fd = next((f for f in ct_def["fields"] if f["role"] == "answer"), None)
                    if ans_fd:
                        ans_text = str(card.get(ans_fd["name"], "")).strip().split(";")[0].strip()
                        if ans_text:
                            audio_file = _slug_filename(ans_text)
                if not audio_file:
                    continue
                audio_path = deck_dir / "media" / audio_file
                if audio_path.exists():
                    media_files.append(str(audio_path))
                else:
                    log.warning(f"  audio_override file not found: {audio_path}")

            note = genanki.Note(
                model=model,
                fields=fields,
                tags=card.get("tags", []),
                guid=_card_guid(section_name, card),
            )
            subdeck.add_note(note)
            total_notes += 1

        package.decks.append(subdeck)
        log.info(f"  subdeck '{subdeck_name}': {len(cards)} notes")

    package.media_files = list(set(media_files))
    package.write_to_file(str(output))
    log.info(f"✅ {total_notes} notes → {output}")
