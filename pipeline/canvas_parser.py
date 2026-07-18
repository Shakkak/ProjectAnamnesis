"""
Obsidian Canvas parser.

Traverses the canvas graph in BFS order starting from root nodes
(nodes with no incoming content edges), reads referenced .md files,
and assembles everything into structured text for Agent 1.

Node types handled:
  file  — resolved against vault_path, read as markdown
  text  — inline LaTeX / notes used as-is
  group — visual container; its label becomes a section header
           (determined by bounding-box containment, smallest group wins)
"""
import json
import logging
import re
from collections import deque
from pathlib import Path

log = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff"}


# ---------------------------------------------------------------------------
# Internal: build graph structures from raw canvas JSON
# ---------------------------------------------------------------------------

def _build_graph(canvas_path: Path):
    """Parse canvas JSON and return (content_nodes, groups, adj, roots)."""
    raw     = json.loads(Path(canvas_path).read_text(encoding="utf-8"))
    nodes   = {n["id"]: n for n in raw.get("nodes", [])}
    edges   = raw.get("edges", [])

    groups  = sorted(
        [n for n in nodes.values() if n["type"] == "group"],
        key=lambda g: g["width"] * g["height"],
    )
    content = {nid: n for nid, n in nodes.items() if n["type"] != "group"}

    adj: dict[str, list[str]] = {nid: [] for nid in content}
    incoming: set[str]        = set()
    for edge in edges:
        src, dst = edge.get("fromNode"), edge.get("toNode")
        if src in content and dst in content:
            adj[src].append(dst)
            incoming.add(dst)

    roots = [nid for nid in content if nid not in incoming]
    if not roots:
        log.warning("Canvas: no root nodes found — falling back to all nodes")
        roots = list(content.keys())

    log.info(
        f"Canvas: {len(content)} content nodes, "
        f"{len(roots)} root(s), {len(edges)} edges, "
        f"{len(groups)} group(s)"
    )
    return content, groups, adj, roots


# ---------------------------------------------------------------------------
# Public: per-level generator (used by pipeline for per-level Agent 1 calls)
# ---------------------------------------------------------------------------

def parse_canvas_levels(canvas_path: Path, vault_path: Path):
    """
    Yield (level: int, text: str) for each BFS level of the canvas.
    Levels with no renderable text are skipped.
    Disconnected nodes are yielded as a final extra level.
    """
    canvas_path = Path(canvas_path)
    vault_path  = Path(vault_path)
    content, groups, adj, roots = _build_graph(canvas_path)

    visited: set[str] = set()
    # BFS — collect nodes per level
    level_buckets: dict[int, list[str]] = {}
    queue = deque((root, 0) for root in roots)

    while queue:
        nid, lvl = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        level_buckets.setdefault(lvl, []).append(nid)
        for nbr in adj.get(nid, []):
            if nbr not in visited:
                queue.append((nbr, lvl + 1))

    # Disconnected nodes → extra level after the last
    disconnected = [nid for nid in content if nid not in visited]
    if disconnected:
        next_level = max(level_buckets.keys(), default=-1) + 1
        level_buckets[next_level] = disconnected

    for lvl in sorted(level_buckets.keys()):
        nids  = level_buckets[lvl]
        parts = []
        current_section = None

        for nid in nids:
            node    = content[nid]
            section = _node_section(node, groups)
            if section and section != current_section:
                current_section = section
                parts.append(f"# Section: {section}")
            chunk = _render_node(node, vault_path)
            if chunk:
                parts.append(chunk)

        text = "\n\n".join(p.strip() for p in parts if p.strip())
        if text:
            yield lvl, text


# ---------------------------------------------------------------------------
# Public: single-string entry point (kept for non-canvas use and tests)
# ---------------------------------------------------------------------------

def parse_canvas(canvas_path: Path, vault_path: Path, checkpoint=None) -> str:
    """
    Parse a .canvas file and return all content as one assembled string.
    checkpoint: optional RunCheckpoint for metadata saves (no longer saves text here;
                text is saved per-level by the pipeline when using parse_canvas_levels).
    """
    parts = []
    for lvl, text in parse_canvas_levels(canvas_path, vault_path):
        if checkpoint:
            checkpoint.save_canvas_level(lvl, 0, text)
        parts.append(text)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_section(node: dict, groups: list[dict]) -> str | None:
    """Return the label of the smallest group that contains this node."""
    nx, ny = node["x"], node["y"]
    for g in groups:
        gx, gy = g["x"], g["y"]
        if gx <= nx <= gx + g["width"] and gy <= ny <= gy + g["height"]:
            return g.get("label")
    return None


def _render_node(node: dict, vault_path: Path) -> str:
    ntype = node["type"]

    if ntype == "text":
        text = node.get("text", "").strip()
        return _clean_md(text) if text else ""

    if ntype == "file":
        file_rel = node.get("file", "")
        if not file_rel:
            return ""

        suffix = Path(file_rel).suffix.lower()
        if suffix in _IMAGE_SUFFIXES:
            return ""

        # Strip leading vault-folder prefix if present (canvas sometimes stores
        # paths as "VaultName/file.md" while vault_path already points inside it)
        vault_prefix = vault_path.name + "/"
        if file_rel.startswith(vault_prefix):
            file_rel = file_rel[len(vault_prefix):]

        file_path = vault_path / file_rel
        if not file_path.exists():
            log.warning(f"Canvas: file not found: {file_path}")
            return ""

        try:
            raw     = file_path.read_text(encoding="utf-8")
            title   = Path(file_rel).stem
            cleaned = _clean_md(raw)
            return f"## {title}\n{cleaned}" if cleaned else ""
        except Exception as exc:
            log.warning(f"Canvas: could not read {file_path}: {exc}")
            return ""

    return ""


def _clean_md(text: str) -> str:
    """Strip Obsidian-specific syntax, keep content and LaTeX."""
    # YAML frontmatter
    text = re.sub(r"^---\n.*?\n---\n?", "", text, flags=re.DOTALL)
    # Embedded refs  ![[file]]
    text = re.sub(r"!\[\[[^\]]*\]\]", "", text)
    # Wikilinks  [[Page|alias]] → alias,  [[Page]] → Page
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    # Callout type markers  > [!info]
    text = re.sub(r"^> \[![^\]]+\]\s*", "", text, flags=re.MULTILINE)
    # Inline tags  #tag  (not # headings)
    text = re.sub(r"(?<!\n)#[a-zA-Z][a-zA-Z0-9_/]*", "", text)
    return text.strip()
