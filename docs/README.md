# docs/

Developer documentation for ProjectAnamnesis. Read `CODEBASE.md` at the start of any coding session before touching modules.

## Reference docs

| Document | Read when |
|----------|-----------|
| [CODEBASE.md](CODEBASE.md) | Starting any coding session — one-paragraph description of every module, key functions, and how files relate |
| [CONTENT_STRUCTURE.md](CONTENT_STRUCTURE.md) | Writing vault concept files or Anki card JSON — covers file format, full card schema, `source_nodes` rules, namespaced tag convention, index systems, and post-change commands |
| [ROADMAP.md](ROADMAP.md) | Prioritised backlog — what exists, what is planned |

## Workflow / agent prompt docs

| Document | Purpose |
|----------|---------|
| [CARDS_AGENT_PROMPT.md](CARDS_AGENT_PROMPT.md) | Editorial guidance for writing or editing ML interview-prep cards — phrasing, field rules, tag conventions |
| [VAULT_AGENT_PROMPT.md](VAULT_AGENT_PROMPT.md) | Workflow for writing or auditing vault concept files with an AI agent |

## Planning / backlog

| Document | Purpose |
|----------|---------|
| [TODO_VAULT_ENHANCEMENT.md](TODO_VAULT_ENHANCEMENT.md) | Ongoing vault enhancement audit |
| [TODO_NEW_VAULT_FILES.md](TODO_NEW_VAULT_FILES.md) | New vault concept files to write |
| [TODO_REWRITES.md](TODO_REWRITES.md) | Card quality rewrite tracking |

## Example files

| Path | Purpose |
|------|---------|
| [example-deck/deck.json](example-deck/deck.json) | Minimal deck.json to copy from |
| [example-deck/section1.json](example-deck/section1.json) | Minimal section file with one card |

## Keep docs updated

If you add a module, rename a function, or significantly change behaviour, update the relevant entry in `CODEBASE.md` in the same commit. Small edits don't need it — use judgment.
