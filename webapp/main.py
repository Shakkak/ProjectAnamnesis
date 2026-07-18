"""
ProjectAnamnesis — Card Review Web UI

Run:
    pip install fastapi uvicorn
    uvicorn webapp.main:app --reload --port 8080
Then open: http://localhost:8080
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from webapp import card_loader, feedback, renderer
from tools.anki_connect import AnkiConnect, AnkiConnectUnavailable

app = FastAPI(title="ProjectAnamnesis Review UI")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

_anki = AnkiConnect()


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "static" / "index.html").read_text()


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------

@app.get("/api/decks")
def get_decks():
    return card_loader.list_decks()


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@app.get("/api/cards/{deck}")
def get_cards(deck: str, filter: str = "all"):
    """Return cards for a deck with their review status.
    filter: all | pending | accepted | rejected
    """
    try:
        _, cards = card_loader.load_deck(deck)
    except FileNotFoundError:
        raise HTTPException(404, f"Deck '{deck}' not found")

    all_fb = feedback.get_all(deck)
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "skipped": 0}
    result = []
    for card in cards:
        cid = card["_id"]
        fb = all_fb.get(cid)
        s = fb["latest"] if fb else "pending"
        counts[s] = counts.get(s, 0) + 1
        if filter != "all" and s != filter:
            continue
        result.append({
            "id": cid,
            "section": card["_section"],
            "card_type": card.get("card_type", "reveal"),
            "question": str(card.get("question", ""))[:120],
            "tags": card.get("tags", []),
            "source_nodes": card.get("source_nodes", []),
            "status": s,
            "comment": fb["history"][-1].get("comment", "") if fb else "",
        })

    return {"cards": result, "counts": counts}


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

@app.get("/api/preview/{deck}/{card_id}/front", response_class=HTMLResponse)
def preview_front(deck: str, card_id: str):
    card = _get_card(deck, card_id)
    return renderer.render_front(card)


@app.get("/api/preview/{deck}/{card_id}/back", response_class=HTMLResponse)
def preview_back(deck: str, card_id: str):
    card = _get_card(deck, card_id)
    return renderer.render_back(card)


# ---------------------------------------------------------------------------
# Review actions
# ---------------------------------------------------------------------------

class ReviewBody(BaseModel):
    action: str   # accepted | rejected | skipped
    comment: str = ""


@app.post("/api/review/{deck}/{card_id}")
def review_card(deck: str, card_id: str, body: ReviewBody):
    if body.action not in ("accepted", "rejected", "skipped"):
        raise HTTPException(400, "action must be accepted | rejected | skipped")
    feedback.save(deck, card_id, body.action, body.comment)
    return {"ok": True, "card_id": card_id, "action": body.action}


# ---------------------------------------------------------------------------
# AnkiConnect
# ---------------------------------------------------------------------------

@app.get("/api/anki/status")
def anki_status():
    ok = _anki.ping()
    decks = []
    if ok:
        try:
            decks = _anki.deck_names()
        except Exception:
            pass
    return {"available": ok, "decks": decks}


@app.post("/api/anki/push/{deck}")
def push_to_anki(deck: str):
    """Push accepted cards to Anki via AnkiConnect.

    Note: this adds notes directly. For first import or model changes,
    use the .apkg file instead (preserves templates and styling).
    """
    if not _anki.ping():
        raise HTTPException(503, "AnkiConnect not available — open Anki first")

    try:
        _, cards = card_loader.load_deck(deck)
    except FileNotFoundError:
        raise HTTPException(404, f"Deck '{deck}' not found")

    all_fb = feedback.get_all(deck)
    to_push = [c for c in cards if all_fb.get(c["_id"], {}).get("latest") == "accepted"]

    if not to_push:
        return {"pushed": 0, "message": "No accepted cards to push"}

    # Group by card type (model name in Anki)
    pushed = 0
    errors = []
    for card in to_push:
        ct_def = card.get("_ct_def", {})
        model_name = ct_def.get("type_id", card.get("card_type", "reveal"))
        fields_list = renderer._map_to_memrise_fields(card, ct_def) if ct_def else []
        field_names = [f["name"] for f in ct_def.get("fields", [])] if ct_def else []
        fields_dict = dict(zip(field_names, fields_list)) if field_names else {
            "Question": str(card.get("question", "")),
            "Answer": str(card.get("answer", "")),
        }
        try:
            _anki.add_notes(deck, model_name, [{
                "fields": fields_dict,
                "tags": card.get("tags", []),
                "guid": card["_id"],
            }])
            pushed += 1
        except Exception as e:
            errors.append({"card_id": card["_id"], "error": str(e)})

    return {"pushed": pushed, "errors": errors}


# ---------------------------------------------------------------------------
# Graph API
# ---------------------------------------------------------------------------

CARD_INDEX = Path(__file__).parent.parent / "content" / "vault" / "card_index.json"
VAULT_INDEX = Path(__file__).parent.parent / "content" / "vault" / "index.json"
VAULT_DIR   = Path(__file__).parent.parent / "content" / "vault"


@app.get("/api/vault/{slug}")
def vault_info(slug: str):
    """Return title + excerpt for a vault file by slug (filename stem)."""
    index = json.loads(VAULT_INDEX.read_text())
    matched_path = next((p for p in index if Path(p).stem == slug), None)
    if not matched_path:
        raise HTTPException(404, f"Vault file '{slug}' not found")

    title = index[matched_path].get("title", slug)

    md_file = VAULT_DIR / matched_path
    excerpt = ""
    if md_file.exists():
        text = md_file.read_text()
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3:].lstrip()
        excerpt = text[:220].strip()
        if len(text) > 220:
            excerpt = excerpt.rstrip(".,;:") + "…"

    return {"title": title, "excerpt": excerpt, "slug": slug}


@app.get("/vault/{slug}", response_class=HTMLResponse)
def vault_page(slug: str):
    """Serve a vault markdown file as a minimal rendered page."""
    index = json.loads(VAULT_INDEX.read_text())
    matched_path = next((p for p in index if Path(p).stem == slug), None)
    if not matched_path:
        raise HTTPException(404, f"Vault file '{slug}' not found")

    md_file = VAULT_DIR / matched_path
    if not md_file.exists():
        raise HTTPException(404, "File not found on disk")

    content = md_file.read_text().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    title = index[matched_path].get("title", slug)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: 'Courier New', monospace; max-width: 820px; margin: 2rem auto;
         padding: 1rem 1.5rem; background: #141410; color: #e2d9c8; line-height: 1.65; font-size: 14px; }}
  pre  {{ white-space: pre-wrap; word-break: break-word; }}
  a    {{ color: #c4792a; }}
</style>
</head><body><pre>{content}</pre></body></html>"""


@app.get("/graph", response_class=HTMLResponse)
def graph_page():
    return (Path(__file__).parent / "static" / "graph.html").read_text()


@app.get("/api/graph/deck")
def graph_deck():
    data = json.loads(CARD_INDEX.read_text())
    by_concept = data.get("by_concept", {})

    nodes, links = [], []
    node_ids: set[str] = set()

    def add_node(nid: str, label: str, group: str, size: int = 1):
        if nid not in node_ids:
            nodes.append({"id": nid, "label": label, "group": group, "size": size})
            node_ids.add(nid)

    for concept, info in by_concept.items():
        add_node(f"c:{concept}", concept, "concept", max(1, info.get("card_count", 1)))
        for section in info.get("sections", []):
            sid = f"s:{section}"
            add_node(sid, section, "section", 6)
            links.append({"source": f"c:{concept}", "target": sid, "type": "member"})

    return {"nodes": nodes, "links": links}


@app.get("/api/graph/vault")
def graph_vault():
    data = json.loads(VAULT_INDEX.read_text())
    card_data = json.loads(CARD_INDEX.read_text())
    slug_to_sections = {
        slug: info.get("sections", [])
        for slug, info in card_data.get("by_concept", {}).items()
    }

    nodes, links = [], []
    node_ids: set[str] = set()
    file_tags: dict[str, set[str]] = {}

    def slug(path: str) -> str:
        return path.replace("/", "__").replace(".md", "")

    for path, info in data.items():
        nid = slug(path)
        subdir = path.split("/")[0] if "/" in path else "root"
        nodes.append({
            "id": nid,
            "label": info.get("title", path),
            "group": subdir,
            "size": 4,
        })
        node_ids.add(nid)
        file_tags[nid] = set(info.get("tags", []))

    # tag-sharing edges
    file_list = list(file_tags.items())
    for i, (a, ta) in enumerate(file_list):
        for b, tb in file_list[i + 1:]:
            shared = ta & tb
            if shared:
                links.append({"source": a, "target": b, "type": "tag", "weight": len(shared)})

    # coverage edges: vault slug → section node
    section_node_ids: set[str] = set()
    for vault_path in data:
        raw_slug = vault_path.replace("/", "/").replace(".md", "").split("/")[-1]
        sections = slug_to_sections.get(raw_slug, [])
        for section in sections:
            sid = f"sec:{section}"
            if sid not in section_node_ids:
                nodes.append({"id": sid, "label": section, "group": "section", "size": 6})
                section_node_ids.add(sid)
            links.append({"source": slug(vault_path), "target": sid, "type": "coverage"})

    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_card(deck: str, card_id: str) -> dict:
    try:
        _, cards = card_loader.load_deck(deck)
    except FileNotFoundError:
        raise HTTPException(404, f"Deck '{deck}' not found")
    for card in cards:
        if card["_id"] == card_id:
            return card
    raise HTTPException(404, f"Card '{card_id}' not found in deck '{deck}'")
