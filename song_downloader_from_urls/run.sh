#!/usr/bin/env bash
# Run the URL-list downloader using the local venv when available.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
  PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"
else
  PYTHON="python3"
fi

exec "$PYTHON" "$SCRIPT_DIR/main.py" "$@"
