#!/usr/bin/env python3
"""Compatibility entry point for URL-list downloads."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from youtube_playlist_downloader.main import main  # noqa: E402


def _argv_with_default_command(argv: list[str]) -> list[str]:
    """Default to download-list when this legacy entry point is used directly."""
    commands = {"download-url", "download-list", "rename"}
    if argv and argv[0] in commands:
        return argv
    return ["download-list", *argv]


if __name__ == "__main__":
    raise SystemExit(main(_argv_with_default_command(sys.argv[1:])))
