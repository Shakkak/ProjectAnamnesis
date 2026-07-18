#!/usr/bin/env python3
"""
Generate vault/index.json — hierarchical header index for all vault concept files.

Each H2 section contains:
  - header, line, summary (first content sentence), subsections (H3 list)

Each H3 subsection contains:
  - header, line, summary

Use section summaries to decide which section to read, then use line numbers
for targeted offset/limit reads instead of loading the whole file.
"""

import argparse
import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent

_MD_NOISE = re.compile(
    r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"  # [[link]] or [[link|alias]] → link text
    r"|`[^`]*`"                          # inline code
    r"|\*\*([^*]+)\*\*"                  # **bold**
    r"|\*([^*]+)\*"                      # *italic*
    r"|^\s*[\|>].*"                      # tables / blockquotes
    r"|\$[^$]+\$"                        # inline math
)


def _clean(text: str) -> str:
    text = _MD_NOISE.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120] + ("…" if len(text) > 120 else "")


def _extract_summary(lines: list[str], from_line: int, end_line: int) -> str:
    """Return first non-trivial content sentence in [from_line, end_line)."""
    for line in lines[from_line:end_line]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s == "---" or s.startswith("```"):
            continue
        if re.match(r"^\s*[\|\+\-]{2,}", s):  # table / hr
            continue
        cleaned = _clean(s)
        if len(cleaned) >= 20:
            return cleaned
    return ""


def parse_file(path: Path) -> dict:
    lines = path.read_text().splitlines()

    title = ""
    tags: list[str] = []
    aliases: list[str] = []

    # --- frontmatter ---
    in_front = False
    front_end = 0
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == "---":
            in_front = True
            continue
        if in_front:
            if line.strip() == "---":
                front_end = i
                in_front = False
                break
            if line.startswith("title:"):
                title = line[6:].strip().strip('"')
            elif line.startswith("tags:"):
                tags = re.findall(r"[\w\-]+", line[5:])
            elif line.startswith("aliases:"):
                m = re.findall(r"[^\[\],]+", line[8:])
                aliases = [a.strip() for a in m if a.strip()]

    # --- collect all H2/H3 positions ---
    raw: list[tuple[int, int, str]] = []  # (line_1indexed, depth, header)
    for i, line in enumerate(lines):
        if i <= front_end:
            continue
        m = re.match(r"^(#{2,3})\s+(.+)", line)
        if m:
            raw.append((i + 1, len(m.group(1)), m.group(2).strip()))

    # --- build nested structure ---
    sections: list[dict] = []
    total = len(raw)
    for idx, (line_no, depth, header) in enumerate(raw):
        next_same_or_higher = next(
            (raw[j][0] for j in range(idx + 1, total) if raw[j][1] <= depth),
            len(lines) + 1,
        )
        content_start = line_no  # 1-indexed → lines[line_no] is line after header
        summary = _extract_summary(lines, content_start, next_same_or_higher - 1)

        if depth == 2:
            sections.append({"header": header, "line": line_no, "summary": summary, "subsections": []})
        elif depth == 3 and sections:
            sections[-1]["subsections"].append({"header": header, "line": line_no, "summary": summary})

    # Drop empty subsections lists for cleanliness
    for s in sections:
        if not s["subsections"]:
            del s["subsections"]

    return {"title": title, "tags": tags, "aliases": aliases, "sections": sections}


def main():
    parser = argparse.ArgumentParser(description="Build vault/index.json")
    parser.add_argument("--bank", metavar="PATH",
                        default=os.environ.get("BANK_PATH"),
                        help="External data root (default: content/ in this repo)")
    args = parser.parse_args()

    bank = Path(args.bank).resolve() if args.bank else _ROOT / "content"
    vault  = bank / "vault"
    output = vault / "index.json"

    index = {}
    for md in sorted(vault.rglob("*.md")):
        if md.name == "TODO.md":
            continue
        rel = str(md.relative_to(vault))
        index[rel] = parse_file(md)

    output.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    print(f"Wrote {output}  ({len(index)} files)")


if __name__ == "__main__":
    main()
