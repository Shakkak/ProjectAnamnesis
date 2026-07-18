"""
Preview generator — renders 2 sample cards to a self-contained HTML file.

The HTML uses the actual template CSS from generator/templates/{type_id}/
so the preview is visually accurate. Users open the file in any browser,
give feedback, and the Card Writer incorporates it before writing the full deck.
"""
import re
from pathlib import Path

# Anki field name → card dict key
_FIELD_MAP = {
    "Definition": "question",
    "Learnable":  "answer",
    "Extra":      "steps",
    "Extra 2":    "hint",
    "Extra 3":    "details",
}


def _substitute_fields(html: str, card: dict) -> str:
    """Replace {{FieldName}} Anki placeholders with card data."""

    # Conditional blocks: {{#Field}}...{{/Field}} — render only when non-empty
    def _replace_conditional(m: re.Match) -> str:
        field_name = m.group(1)
        inner = m.group(2)
        key = _FIELD_MAP.get(field_name, "")
        value = card.get(key, "") or ""
        return inner if value.strip() else ""

    html = re.sub(
        r"\{\{#([^}]+)\}\}(.*?)\{\{/\1\}\}",
        _replace_conditional,
        html,
        flags=re.DOTALL,
    )

    # Plain field replacements
    for field_name, card_key in _FIELD_MAP.items():
        value = card.get(card_key, "") or ""
        html = html.replace(f"{{{{{field_name}}}}}", value)

    return html


def _load_template(template_dir: Path, template_id: str) -> tuple[str, str, str]:
    """Load front.html, back.html, style.css from the template directory."""
    tdir = template_dir / template_id
    if not tdir.is_dir():
        # Fall back to reveal-interview if template doesn't exist yet
        tdir = template_dir / "reveal-interview"
    front = (tdir / "front.html").read_text(encoding="utf-8")
    back  = (tdir / "back.html").read_text(encoding="utf-8")
    css   = (tdir / "style.css").read_text(encoding="utf-8")
    return front, back, css


def _load_generated_template(template_files: dict) -> tuple[str, str, str]:
    return (
        template_files["front_html"],
        template_files["back_html"],
        template_files["style_css"],
    )


def _card_html(front_tpl: str, back_tpl: str, card: dict, n: int) -> str:
    front = _substitute_fields(front_tpl, card)
    back  = _substitute_fields(back_tpl,  card)
    return f"""
    <div class="preview-card">
      <div class="preview-label">Card {n}</div>
      <div class="preview-side">
        <div class="side-label">Front</div>
        <div class="side-frame">{front}</div>
      </div>
      <div class="preview-side">
        <div class="side-label">Back</div>
        <div class="side-frame">{back}</div>
      </div>
    </div>
"""


_PAGE_SHELL = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Card Preview — {deck_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #f0f2f5; color: #222; padding: 24px; }}
    h1 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 6px; }}
    .meta {{ font-size: 0.82rem; color: #666; margin-bottom: 32px; }}
    .preview-card {{ margin-bottom: 48px; }}
    .preview-label {{ font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em;
                      text-transform: uppercase; color: #888; margin-bottom: 12px; }}
    .preview-side {{ margin-bottom: 12px; }}
    .side-label {{ font-size: 0.68rem; font-weight: 600; color: #aaa;
                   text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }}
    .side-frame {{ border: 1px solid #ddd; border-radius: 12px; overflow: hidden;
                   background: #fff; min-height: 200px; position: relative; }}
    /* Scope template styles inside .side-frame */
    .side-frame .watermark {{ position: absolute; }}
  </style>
  <!-- Scoped template CSS -->
  <style>
    .side-frame {{ all: revert; border: 1px solid #ddd; border-radius: 12px;
                   overflow: hidden; background: #fff; min-height: 200px; position: relative; }}
{card_css}
  </style>
</head>
<body>
  <h1>Preview — {deck_name}</h1>
  <p class="meta">These are 2 sample cards. Open your terminal and give feedback (or press Enter to proceed).</p>
{cards_html}
</body>
</html>
"""


def generate_preview(
    sample_cards: list[dict],
    blueprint: dict,
    template_dir: Path,
    output_path: Path,
    deck_name: str = "Deck",
) -> Path:
    """
    Render up to 2 sample cards to a self-contained HTML preview file.

    sample_cards: 1 or 2 card dicts (same schema as Card Writer output)
    blueprint:    Blueprint from Deck Designer (provides template_id / template_files)
    template_dir: path to generator/templates/
    output_path:  where to write the .html file
    Returns: output_path
    """
    template_id = blueprint.get("template_id", "reveal-interview")
    template_files = blueprint.get("template_files")

    if template_files:
        front_tpl, back_tpl, css = _load_generated_template(template_files)
    else:
        front_tpl, back_tpl, css = _load_template(template_dir, template_id)

    cards_html = "".join(
        _card_html(front_tpl, back_tpl, card, i + 1)
        for i, card in enumerate(sample_cards[:2])
    )

    html = _PAGE_SHELL.format(
        deck_name=deck_name,
        card_css=css,
        cards_html=cards_html,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
