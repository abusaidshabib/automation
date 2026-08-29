#!/usr/bin/env bash
# Run the unified downloader CLI with uv.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  exec uv run --project "$ROOT" python "$SCRIPT_DIR/main.py" download-url
else
  exec uv run --project "$ROOT" python "$SCRIPT_DIR/main.py" "$@"
fi
