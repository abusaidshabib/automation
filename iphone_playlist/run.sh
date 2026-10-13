#!/usr/bin/env bash
# Download a playlist as ALAC (or other formats) for iPhone playback.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

exec uv run --project "$ROOT" python "$SCRIPT_DIR/main.py" "$@"
