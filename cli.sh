#!/usr/bin/env bash
# ProjectAnamnesis CLI — thin wrapper around docker compose run
#
# Usage:
#   ./cli.sh pipeline --input input/notes.md --deck-name "My Deck"
#   ./cli.sh pipeline --input input/notes.md --deck-name "My Deck" --section "Chapter 1"
#   ./cli.sh pipeline --input input/overview.canvas --vault input/my_vault/ --deck-name "Stats 110"
#   ./cli.sh pipeline --input input/notes.md --deck-name "My Deck" --save-intermediate
#   ./cli.sh pipeline --input input/notes.md --deck-name "My Deck" --skip-generate
#
#   ./cli.sh generate --deck handtool/decks/interview-prep/
#   ./cli.sh generate --deck handtool/decks/interview-prep/ --skip-audio
#   ./cli.sh generate --deck handtool/decks/interview-prep/ --dry-run
#
# For canvas files: copy your vault into input/ first.
#   cp -r ~/path/to/obsidian-vault input/my_vault/
#   cp ~/path/to/vault/overview.canvas input/
set -e

CMD="${1:-}"
shift || true

case "$CMD" in
  pipeline)
    docker compose run --rm app python pipeline/pipeline.py "$@"
    ;;
  generate)
    docker compose run --rm app python generator/main.py "$@"
    ;;
  *)
    echo "Usage: ./cli.sh <pipeline|generate> [args...]"
    echo ""
    echo "  pipeline  Run the full AI pipeline (raw input → card JSON → .apkg)"
    echo "  generate  Run the generator only (existing card JSON → .apkg)"
    exit 1
    ;;
esac
