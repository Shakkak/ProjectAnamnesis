# webapp/

FastAPI web app for reviewing generated cards and visualising concept-card coverage.

## Start

```bash
docker compose up webapp
# Open http://localhost:8080
```

## Pages

| URL | Purpose |
|-----|---------|
| `/` | Card review — browse, accept, reject, comment |
| `/graph` | Interactive D3 force-directed graph of concept ↔ card coverage |

## Card review workflow

1. Open `http://localhost:8080`
2. Select a deck and section from the sidebar
3. Review each card (rendered HTML with full template styling)
4. Accept, reject, or leave a comment
5. Feedback is written to `feedback/<deck-slug>/<section>.json`
6. On the next pipeline run, comments are injected into Agent 2's prompt so the model improves those cards

## Graph (`/graph`)

Two views:

- **Deck view** — cards as nodes, grouped by section; edges connect cards that share `source_nodes`
- **Vault view** — vault concepts as nodes; edges connect concepts linked via `depends_on` / `related`; cards appear as leaves

Node colour encodes coverage density. Click a node to see its cards or concept file.

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app; mounts routes and static files |
| `card_loader.py` | Loads card JSON from `content/decks/`; resolves section lists |
| `renderer.py` | Renders card fields to HTML for preview |
| `feedback.py` | Accept / reject / comment endpoints; writes to `feedback/` |
| `static/index.html` | Card review UI |
| `static/graph.html` | D3 graph visualisation |
| `static/app.js` | Client-side logic |
| `static/style.css` | Shared styles |

## Feedback format

```
feedback/
└── interview-prep/
    └── attention-mechanism.json   # [{"card_id": "...", "action": "reject", "comment": "..."}]
```

The pipeline reads this at startup via `tools/feedback_reader.py` and groups comments by section name. Rejected cards are flagged; comments are appended to the Agent 2 batch prompt.
