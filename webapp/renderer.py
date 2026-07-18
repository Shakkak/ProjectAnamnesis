"""Render Anki cards to standalone HTML using the real Memrise templates."""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "Anki-Card-Templates" / "Add-on" / "Source code"

sys.path.insert(0, str(PROJECT_ROOT / "generator"))
from generator import (
    _patch_front, _patch_back, _build_memrise_fields,
    _map_to_memrise_fields, _dollar_to_mathjax,
)

MATHJAX_CDN = """
<script>
MathJax = { tex: { inlineMath: [['\\\\(','\\\\)'],['$','$']], displayMath: [['\\\\[','\\\\]'],['$$','$$']] } };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
"""


# ---------------------------------------------------------------------------
# Anki mustache renderer
# ---------------------------------------------------------------------------

def _render_anki_template(html: str, fields: dict[str, str]) -> str:
    """Substitute Anki {{Field}}, {{#Field}}...{{/Field}}, {{^Field}}...{{/Field}}."""

    # Conditional blocks {{#F}}...{{/F}} — show if non-empty
    def _show_if(m: re.Match) -> str:
        name, body = m.group(1), m.group(2)
        return body if fields.get(name, "").strip() else ""

    # Inverse blocks {{^F}}...{{/F}} — show if empty
    def _hide_if(m: re.Match) -> str:
        name, body = m.group(1), m.group(2)
        return "" if fields.get(name, "").strip() else body

    html = re.sub(r"\{\{#(\w[\w ]*)\}\}(.*?)\{\{/\1\}\}", _show_if, html, flags=re.DOTALL)
    html = re.sub(r"\{\{\^(\w[\w ]*)\}\}(.*?)\{\{/\1\}\}", _hide_if, html, flags=re.DOTALL)

    # Plain {{Field}} substitution
    for name, value in fields.items():
        html = html.replace("{{" + name + "}}", value)

    # Remove any remaining unresolved tags
    html = re.sub(r"\{\{[^}]+\}\}", "", html)
    return html


# ---------------------------------------------------------------------------
# Public render functions
# ---------------------------------------------------------------------------

def _load(filename: str) -> str:
    return (TEMPLATE_DIR / filename).read_text(encoding="utf-8")


def _field_map(ct_def: dict, card: dict) -> dict[str, str]:
    """Build Anki field-name → value mapping for template substitution."""
    memrise_fields = _build_memrise_fields(ct_def)
    values = _map_to_memrise_fields(card, ct_def)
    return dict(zip(memrise_fields, values))


def _wrap_html(body_html: str, css: str, js: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>body{{margin:0;background:#1a1a2e;}}{css}</style>
{extra_head}
</head>
<body class="nightMode">
<div class="card">
{body_html}
</div>
{js}
</body>
</html>"""


def render_front(card: dict) -> str:
    ct_def = card.get("_ct_def", {})
    if not ct_def:
        return _fallback_front(card)

    tmpl = ct_def["templates"][0]
    mode = tmpl.get("mode", "typing")
    theme = tmpl.get("theme", "MemRise")
    latex = tmpl.get("latex", False)

    field_by_name = {fd["name"]: fd for fd in ct_def["fields"]}
    a_label = field_by_name[tmpl["answer_field"]].get("label", tmpl["answer_field"])

    front_html = _load("Template Front.html")
    front_js = _load("Template Front scripts.js")
    css = _load("Template Styling.css")

    front_html = _patch_front(front_html, mode=mode, theme=theme,
                              answer_label=a_label, latex=latex)
    fields = _field_map(ct_def, card)
    front_html = _render_anki_template(front_html, fields)

    extra_head = MATHJAX_CDN if latex else ""
    return _wrap_html(front_html, css, f"<script>{front_js}</script>", extra_head)


def render_back(card: dict) -> str:
    ct_def = card.get("_ct_def", {})
    if not ct_def:
        return _fallback_back(card)

    tmpl = ct_def["templates"][0]
    mode = tmpl.get("mode", "typing")
    theme = tmpl.get("theme", "MemRise")
    latex = tmpl.get("latex", False)

    field_by_name = {fd["name"]: fd for fd in ct_def["fields"]}
    q_label = field_by_name[tmpl["question_field"]].get("label", tmpl["question_field"])
    a_label = field_by_name[tmpl["answer_field"]].get("label", tmpl["answer_field"])
    extra_labels = [fd.get("label", fd["name"]) for fd in ct_def["fields"] if fd["role"] == "extra"]
    memrise_fields = _build_memrise_fields(ct_def)

    back_html = _load("Template Back.html")
    back_js = _load("Template Back scripts.js")
    css = _load("Template Styling.css")

    back_html = _patch_back(back_html, question_label=q_label, answer_label=a_label,
                            extra_labels=extra_labels, model_fields=memrise_fields)
    fields = _field_map(ct_def, card)
    # Include front side content for {{FrontSide}}
    fields["FrontSide"] = fields.get("Definition", "")
    back_html = _render_anki_template(back_html, fields)

    extra_head = MATHJAX_CDN if latex else ""
    return _wrap_html(back_html, css, f"<script>{back_js}</script>", extra_head)


# ---------------------------------------------------------------------------
# Fallback renderer (no card type definition available)
# ---------------------------------------------------------------------------

def _fallback_front(card: dict) -> str:
    q = _dollar_to_mathjax(str(card.get("question", "")))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:sans-serif;padding:2rem;background:#1a1a2e;color:#eee;}}
.q{{font-size:1.3rem;line-height:1.6;}}</style>{MATHJAX_CDN}</head>
<body><div class="q">{q}</div></body></html>"""


def _fallback_back(card: dict) -> str:
    q = _dollar_to_mathjax(str(card.get("question", "")))
    a = _dollar_to_mathjax(str(card.get("answer", "")))
    steps = _dollar_to_mathjax(str(card.get("steps", "")))
    hint = str(card.get("hint", ""))
    hint_html = f'<details><summary>Hint</summary><p>{hint}</p></details>' if hint else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:sans-serif;padding:2rem;background:#1a1a2e;color:#eee;}}
.q{{font-size:1.1rem;opacity:.7;border-bottom:1px solid #444;padding-bottom:1rem;margin-bottom:1rem;}}
.a{{font-size:1.2rem;margin-bottom:1rem;}}
.steps{{font-size:.95rem;opacity:.85;}}
details{{margin-top:1rem;font-size:.9rem;opacity:.7;}}</style>{MATHJAX_CDN}</head>
<body>
<div class="q">{q}</div>
<div class="a">{a}</div>
<div class="steps">{steps}</div>
{hint_html}
</body></html>"""
