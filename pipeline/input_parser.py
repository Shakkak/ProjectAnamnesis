"""
Converts any input file into clean text for Agent 1.

Supported formats:
  .md / .txt           — read directly; Obsidian syntax stripped for .md
  .pdf, .docx, .pptx,
  .xlsx, .html, .epub,
  .csv, .ipynb, ...    — converted via markitdown (available inside Docker)

For Obsidian canvas files (.canvas), use canvas_parser.py instead.
"""
import re
import subprocess
import sys
from pathlib import Path

# File types that require markitdown conversion (binary / rich formats)
_MARKITDOWN_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".xlsx", ".xls", ".csv",
    ".html", ".htm", ".epub",
    ".ipynb", ".msg",
}


def parse_file(path: Path) -> str:
    """Return clean plain text from any supported input file."""
    suffix = path.suffix.lower()

    if suffix in _MARKITDOWN_EXTENSIONS:
        return _via_markitdown(path)

    text = path.read_text(encoding="utf-8")
    if suffix in (".md", ".markdown"):
        return _clean_obsidian(text)
    return text.strip()


def _via_markitdown(path: Path) -> str:
    """Convert a binary/rich-format document to markdown text via markitdown."""
    result = subprocess.run(
        [sys.executable, "-c",
         "from markitdown import MarkItDown; "
         f"print(MarkItDown().convert('{path}').text_content)"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"markitdown failed for {path.name}:\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _clean_obsidian(text: str) -> str:
    # Strip YAML frontmatter
    text = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL)
    # Strip embedded file refs  ![[file.png]]
    text = re.sub(r"!\[\[[^\]]*\]\]", "", text)
    # Wikilinks: [[Page|alias]] → alias,  [[Page]] → Page
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # Callout markers  > [!info] Title  →  Title
    text = re.sub(r"^> \[![^\]]+\]\s*", "", text, flags=re.MULTILINE)
    # Inline Obsidian tags  #tag  (preserve # headings by requiring no newline before)
    text = re.sub(r"(?<!\n)#[a-zA-Z][a-zA-Z0-9_/]*", "", text)
    return text.strip()
