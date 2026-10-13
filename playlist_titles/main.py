#!/usr/bin/env python3
"""List titles from a YouTube playlist, with playlist position.

Similar names are placed in the same block so duplicates are easy to delete.
"tu hai kaha" and "Tu Hai Kahan" share a block. "Tu Hai Mera" stays in its own.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import yt_dlp

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_URL_FILE = SCRIPT_DIR / "playlist_url.txt"
DEFAULT_OUT_DIR = SCRIPT_DIR

# Words that describe the upload, not the song.
_NOISE_WORDS = (
    "official",
    "music",
    "video",
    "lyric",
    "lyrics",
    "lyrical",
    "full",
    "audio",
    "song",
    "title",
    "track",
    "hd",
    "4k",
    "slowed",
    "reverbed",
    "reverb",
    "remix",
    "cover",
    "visualizer",
    "theme",
)
_NOISE_RE = re.compile(r"\b(" + "|".join(_NOISE_WORDS) + r")\b", re.IGNORECASE)
_BY_RE = re.compile(
    r"\b(?:by|ft|feat|featuring)\b\s+[a-z0-9.'&]+(?:\s+[a-z0-9.'&]+){0,4}",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^a-z0-9\u0980-\u09ff\u0600-\u06ff\s]+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Track:
    position: int
    video_id: str
    title: str
    url: str
    core: str


def song_core(title: str) -> str:
    """Reduce a YouTube title to the song name used for comparison."""
    text = title.split("|", 1)[0]
    text = text.replace("’", "'")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = text.lower()
    text = _BY_RE.sub(" ", text)
    text = _NOISE_RE.sub(" ", text)
    text = _NON_WORD_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _one_token_spelling(left: str, right: str) -> bool:
    """True when the names differ by a single close spelling, like kaha/kahan."""
    left_words = left.split()
    right_words = right.split()
    if len(left_words) != len(right_words) or not left_words:
        return False
    changed = [(a, b) for a, b in zip(left_words, right_words) if a != b]
    if len(changed) != 1:
        return False
    a, b = changed[0]
    if min(len(a), len(b)) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def _artist_prefix(left: str, right: str) -> bool:
    """True when one name is the other plus a leading artist, like 'Bayaan Maand' / 'Maand'."""
    left_words = left.split()
    right_words = right.split()
    short, long = (left_words, right_words) if len(left_words) <= len(right_words) else (right_words, left_words)
    if len(short) != 1 or len(long) < 2:
        return False
    token = short[0]
    if len(token) < 6:
        return False
    return long[-1] == token


def same_song(left: str, right: str) -> bool:
    """Return whether two cores name the same song.

    Shared words are not enough. "tu hai kahan" matches "tu hai kaha".
    "tu hai kahan" does not match "tu hai mera".
    """
    if not left or not right:
        return False
    if left == right:
        return True
    if SequenceMatcher(None, left, right).ratio() >= 0.90:
        return True
    if _one_token_spelling(left, right):
        return True
    return _artist_prefix(left, right)


def cluster_tracks(tracks: list[Track]) -> list[list[Track]]:
    """Group tracks whose cores name the same song. Order inside a group follows position."""
    parent = list(range(len(tracks)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            if same_song(tracks[i].core, tracks[j].core):
                union(i, j)

    groups: dict[int, list[Track]] = {}
    for index, track in enumerate(tracks):
        groups.setdefault(find(index), []).append(track)
    clustered = [sorted(group, key=lambda track: track.position) for group in groups.values()]
    clustered.sort(key=lambda group: (group[0].core, group[0].position))
    return clustered


def fetch_tracks(url: str) -> tuple[str, int | None, list[Track]]:
    """Load playlist entries without downloading media. Returns title, listed count, tracks."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("Could not read that playlist URL.")

    raw_entries = info.get("entries")
    if raw_entries is None:
        raw_entries = [info]
        playlist_title = info.get("title") or "Video"
    else:
        playlist_title = info.get("title") or "Playlist"

    listed_count = info.get("playlist_count")
    tracks: list[Track] = []
    visible = 0
    for entry in raw_entries:
        if not entry:
            continue
        visible += 1
        title = (entry.get("title") or "").strip() or "(untitled)"
        video_id = entry.get("id") or ""
        position = entry.get("playlist_index") or visible
        watch_url = entry.get("url") or ""
        if video_id and not watch_url.startswith("http"):
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
        tracks.append(
            Track(
                position=int(position),
                video_id=video_id,
                title=title,
                url=watch_url,
                core=song_core(title),
            )
        )
    return playlist_title, listed_count if isinstance(listed_count, int) else None, tracks


def _write_report(
    path: Path,
    playlist_title: str,
    playlist_url: str,
    listed_count: int | None,
    groups: list[list[Track]],
) -> None:
    duplicates = [group for group in groups if len(group) > 1]
    lines: list[str] = [
        f"Playlist: {playlist_title}",
        f"URL: {playlist_url}",
        f"Playable videos: {sum(len(group) for group in groups)}",
    ]
    if listed_count and listed_count > sum(len(group) for group in groups):
        hidden = listed_count - sum(len(group) for group in groups)
        lines.append(f"YouTube lists {listed_count} videos. {hidden} unavailable videos are hidden.")
    lines.append("")
    lines.append("A block is one song. Positions are the playlist order, top to bottom.")
    lines.append('Names in one block match, including case and small spelling differences ("kaha" / "kahan").')
    lines.append('A blank line means a different song. "Tu Hai Kahan" is not grouped with "Tu Hai Mera".')
    lines.append("")
    lines.append(f"DUPLICATE SONGS ({len(duplicates)})")
    lines.append("=" * 72)
    if not duplicates:
        lines.append("No duplicate titles found.")
        lines.append("")
    for index, group in enumerate(duplicates, start=1):
        lines.append(f"[{index}] {group[0].core}  ({len(group)} copies)")
        for track in group:
            lines.append(f"  position {track.position:<4}  {track.title}")
            lines.append(f"             {track.url}")
        lines.append("")

    lines.append("ALL TITLES")
    lines.append("=" * 72)
    lines.append("Similar titles are in the same block. Blocks are alphabetical.")
    lines.append("")
    for group in groups:
        label = "DUPLICATE" if len(group) > 1 else ""
        for track in group:
            marker = f"{label:<9} " if label else "          "
            lines.append(f"{marker}{track.position:>4}  {track.title}")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_csv(path: Path, groups: list[list[Track]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["position", "copies", "duplicate", "song_key", "title", "url", "video_id"])
        for group in groups:
            copies = len(group)
            for track in group:
                writer.writerow(
                    [
                        track.position,
                        copies,
                        "yes" if copies > 1 else "",
                        track.core,
                        track.title,
                        track.url,
                        track.video_id,
                    ]
                )


def write_reports(
    out_dir: Path,
    playlist_title: str,
    playlist_url: str,
    listed_count: int | None,
    tracks: list[Track],
) -> tuple[Path, Path, list[list[Track]]]:
    groups = cluster_tracks(tracks)
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / "titles.txt"
    csv_path = out_dir / "titles.csv"
    _write_report(text_path, playlist_title, playlist_url, listed_count, groups)
    _write_csv(csv_path, groups)
    return text_path, csv_path, groups


def load_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    if DEFAULT_URL_FILE.is_file():
        for line in DEFAULT_URL_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    raise SystemExit(f"Pass --url or put a playlist URL in {DEFAULT_URL_FILE}")


def self_test() -> None:
    """Check the examples that decide whether two titles are the same song."""
    pairs = [
        ("tu hai kaha", "Tu Hai Kaha", True),
        ("tu hai kaha", "Tu Hai Kahan", True),
        ("Tu Hai Kahan by AUR | تو ہے کہاں feat. ZAYN (Official Music Video)", "Tu Hai Kahan by AUR | تو ہے کہاں (Official Music Video)", True),
        ("Tu Hai Kahan", "Tu Hai Mera", False),
        ("Main Agar Kahoon | Om Shanti Om", "Main Agar Lyric Video | Tubelight", False),
        ("Hai Dil Ye Mera Full Video Song | Hate Story 2", "Ae Dil Hai Mushkil (Title Track)", False),
        ("Hai Dil Ye Mera", "Tinka Tinka Dil Mera", False),
        ("Channa Mereya - Lyric Video | Ae Dil Hai Mushkil", "Channa Mereya", True),
        ("Ava Max - Sweet but Psycho [Official Music Video]", "Ava Max - So Am I [Official Music Video]", False),
        ("Ruth B. - Dandelions (Lyrics)", "Dandelions", True),
    ]
    failures: list[str] = []
    for left, right, expected in pairs:
        actual = same_song(song_core(left), song_core(right))
        if actual != expected:
            failures.append(f"{left!r} vs {right!r}: got {actual}, cores {song_core(left)!r} / {song_core(right)!r}")
    if failures:
        raise SystemExit("Similarity checks failed:\n" + "\n".join(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List playlist titles and group duplicate song names.")
    parser.add_argument("--url", help="YouTube playlist URL. Defaults to playlist_url.txt.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="Folder for titles.txt and titles.csv.")
    parser.add_argument("--self-test", action="store_true", help="Check similarity examples and exit.")
    args = parser.parse_args(argv)

    self_test()
    if args.self_test:
        print("Similarity checks passed.")
        return 0

    url = load_url(args.url)
    playlist_title, listed_count, tracks = fetch_tracks(url)
    if not tracks:
        print("No playable videos found.", file=sys.stderr)
        return 1
    text_path, csv_path, groups = write_reports(args.out, playlist_title, url, listed_count, tracks)
    duplicates = sum(1 for group in groups if len(group) > 1)
    print(f"{len(tracks)} titles")
    print(f"{duplicates} duplicate song groups")
    print(text_path)
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
