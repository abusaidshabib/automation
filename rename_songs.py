#!/usr/bin/env python3
"""Rename MP3 files to clean song titles."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def clean_title(name: str) -> str:
    """Strip artist names, video labels, and movie names from a title."""
    name = re.sub(r"^\d+\s*-\s*", "", name.strip())
    name = re.split(r"\s*[｜|]\s*", name)[0]

    quoted = re.search(r'[＂"\u201c](.+?)[＂"\u201d]', name)
    if quoted:
        return quoted.group(1).strip()

    name = re.sub(r"^@\S+\s*[-–—：:]\s*", "", name)
    name = re.sub(r"^[^：]+：\s*", "", name)

    noise_kw = (
        r"(?:official|video|audio|lyric|full|song|slowed|reverbed|music|title|track|theme)"
    )
    name = re.sub(
        rf"(?i)\s*[\(\[][^\)\]]*{noise_kw}[^\)\]]*[\)\]].*$",
        "",
        name,
    )
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)

    noise_phrases = (
        r"(?:Official\s+Music\s+Video|Official\s+(?:Video|Audio)|"
        r"Lyric(?:al)?\s+Video|Full\s+(?:Video|Song)|Music\s+Video|"
        r"Slowed(?:\s*[&]\s*Reverbed)?|Title\s+(?:Track|Song)|"
        r"Theme\s+Song|Lyric(?:al)?s?)"
    )
    name = re.sub(rf"(?i)\s+{noise_phrases}(?=\s*[-–—]|\s|$)", "", name)
    name = re.sub(r"(?i)\s+(?:Song|Video)\s*$", "", name)
    name = re.sub(r"(?i)\s+f(?:ea)?t\.?\s+.*$", "", name)
    name = re.sub(r"\s*[–—]\s+.*$", "", name)
    name = re.sub(r"\s+-\s+.*$", "", name)
    name = re.sub(r"(?i)-lyric(?:al)?s?\s*$", "", name)
    name = re.sub(r"\s*[-–]\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def rename_songs(directory: str | Path, dry_run: bool = True) -> None:
    """Rename MP3 files in a folder using clean_title()."""
    folder = Path(directory)
    if not folder.is_dir():
        print(f"Directory not found: {directory}")
        return

    mp3_files = sorted(folder.glob("*.mp3"))
    if not mp3_files:
        print(f"No MP3 files found in {directory}")
        return

    print(f"Found {len(mp3_files)} MP3 file(s) in {folder}\n")
    to_rename, skipped, conflicts = 0, 0, 0

    for file in mp3_files:
        old_stem = file.stem
        new_stem = clean_title(old_stem)

        if old_stem == new_stem:
            skipped += 1
            continue

        new_path = file.with_name(new_stem + file.suffix)
        if new_path.exists() and new_path != file:
            print(f"  [CONFLICT] '{old_stem}'")
            print(f"          → '{new_stem}' already exists, skipping\n")
            conflicts += 1
            continue

        label = "DRY RUN" if dry_run else "RENAME"
        print(f"  [{label}]")
        print(f"    FROM: {old_stem}")
        print(f"    TO:   {new_stem}\n")

        if not dry_run:
            file.rename(new_path)
        to_rename += 1

    print("-" * 60)
    print(f"  To rename : {to_rename}")
    print(f"  Unchanged : {skipped}")
    print(f"  Conflicts : {conflicts}")
    if dry_run:
        print("\n  This was a DRY RUN. Add --apply to actually rename files.")


def main(argv: list[str] | None = None) -> int:
    """CLI wrapper that forwards to the unified rename command when possible."""
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if not argv or argv[0] in ("rename", "download-url", "download-list"):
        from youtube_playlist_downloader.main import main as unified_main

        if not argv or argv[0] != "rename":
            argv = ["rename", *argv]
        return unified_main(argv)

    parser = argparse.ArgumentParser(
        description="Clean up MP3 filenames — keep only the song title.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        help="Folder containing MP3 files",
    )
    parser.add_argument(
        "--dir",
        dest="directory_opt",
        help="Folder containing MP3 files",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files (default: dry run)",
    )
    args = parser.parse_args(argv)
    directory = args.directory_opt or args.directory
    if not directory:
        parser.error("Provide a folder path.")
    rename_songs(directory, dry_run=not args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
