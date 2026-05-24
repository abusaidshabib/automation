#!/usr/bin/env python3
"""Rename MP3 files to clean song titles — strips artist names, video labels, movie names, etc."""

import re
import argparse
from pathlib import Path


def clean_title(name: str) -> str:
    # 1. Strip everything after ｜ or | (YouTube pipe separator)
    name = re.split(r"\s*[｜|]\s*", name)[0]

    # 2. Extract text from full-width or typographic quotes, e.g. ＂Tum Hi Ho＂
    m = re.search(r'[＂"\u201c](.+?)[＂"\u201d]', name)
    if m:
        return m.group(1).strip()

    # 3. Strip @username prefix, e.g. @SaiAbhyankkar - Aasa Kooda
    name = re.sub(r"^@\S+\s*[-–—：:]\s*", "", name)

    # 4. Strip "Prefix：" at start (full-width colon only), e.g. Dunki： O Maahi / Full Video： Raanjhan
    name = re.sub(r"^[^：]+：\s*", "", name)

    # 5. Strip noise-keyword parens/brackets AND everything that follows them
    #    e.g. "(Full Video) Laal Singh Chaddha" → gone entirely
    _noise_kw = r"(?:official|video|audio|lyric|full|song|slowed|reverbed|music|title|track|theme)"
    name = re.sub(
        rf"(?i)\s*[\(\[][^\)\]]*{_noise_kw}[^\)\]]*[\)\]].*$",
        "",
        name,
    )

    # 6. Strip remaining plain parens/brackets, e.g. (এ কি প্রেম)
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)

    # 7. Strip noise phrases inline
    _noise_phrases = (
        r"(?:Official\s+Music\s+Video|Official\s+(?:Video|Audio)|"
        r"Lyric(?:al)?\s+Video|Full\s+(?:Video|Song)|Music\s+Video|"
        r"Slowed(?:\s*[&]\s*Reverbed)?|Title\s+(?:Track|Song)|"
        r"Theme\s+Song|Lyric(?:al)?s?)"
    )
    name = re.sub(rf"(?i)\s+{_noise_phrases}(?=\s*[-–—]|\s|$)", "", name)

    # 8. Strip trailing standalone "Song" or "Video", e.g. "Tujh Mein Rab Dikhta Hai Song"
    name = re.sub(r"(?i)\s+(?:Song|Video)\s*$", "", name)

    # 9. Strip "ft./feat. Artist" suffix
    name = re.sub(r"(?i)\s+f(?:ea)?t\.?\s+.*$", "", name)

    # 10. Strip after en-dash / em-dash (movie name separator), e.g. Janam Janam – Dilwale
    name = re.sub(r"\s*[–—]\s+.*$", "", name)

    # 11. Strip after " - " (movie/extra info after regular dash with spaces)
    name = re.sub(r"\s+-\s+.*$", "", name)

    # 12. Strip attached -Lyrical / -Lyrics with no space, e.g. Ei Ki Prem-Lyrical
    name = re.sub(r"(?i)-lyric(?:al)?s?\s*$", "", name)

    # 13. Strip trailing stray dash/hyphen
    name = re.sub(r"\s*[-–]\s*$", "", name)

    # 14. Normalize whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name


def rename_songs(directory: str, dry_run: bool = True) -> None:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean up MP3 filenames — keep only the song title."
    )
    parser.add_argument(
        "directory", help="Folder containing MP3 files, e.g. D:/Music")
    parser.add_argument(
        "--apply", action="store_true", help="Actually rename files (default: dry run)"
    )
    args = parser.parse_args()
    rename_songs(args.directory, dry_run=not args.apply)

# To rename files, run:
#   python rename_songs.py "D:/Music" --apply