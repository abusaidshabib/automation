#!/usr/bin/env bash
# Run the song downloader using the local venv
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
exec "$SCRIPT_DIR/.venv/Scripts/python.exe" "$SCRIPT_DIR/main.py" "$@"
