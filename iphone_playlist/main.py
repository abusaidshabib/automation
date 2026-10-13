#!/usr/bin/env python3
"""Download a YouTube playlist as Apple Lossless (or other formats) for iPhone playback.

Default path: best YouTube audio → ALAC (.m4a) with tags and artwork.
ALAC avoids a second lossy encode; the iPhone Music app plays it natively.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_URL_FILE = SCRIPT_DIR / "playlist_url.txt"
DEFAULT_SAVE = SCRIPT_DIR / "downloads"

OUTPUT_FORMATS = ("alac", "aac", "flac", "wav")
console = Console()


# ── Title / artist parsing (edit here to change cleanup behaviour) ──────────

_NOISE_TRAILERS = re.compile(
    r"(?i)\s*[\(\[]?\s*(?:"
    r"official(?:\s+(?:music\s+)?(?:video|audio))?|"
    r"lyric(?:al)?(?:\s+video)?|"
    r"music\s+video|"
    r"full\s+(?:video|song|audio)(?:\s+with\s+lyrics?)?|"
    r"full\s+song\s+with\s+lyrics?|"
    r"audio|"
    r"hd|4k|"
    r"visualizer|"
    r"slowed(?:\s*[&and]+\s*reverbed?)?|"
    r"title\s+(?:track|song)|"
    r"theme(?:\s+song)?"
    r")\s*[\)\]]?\s*$"
)
_NOISE_LEADERS = re.compile(
    r"(?i)^(?:official(?:\s+(?:music\s+)?(?:video|audio))?|"
    r"lyric(?:al)?(?:\s+video)?|"
    r"full(?:\s+(?:video|song|audio))?|"
    r"music\s+video)\s*[:\-–—]\s*"
)
_BRACKET_NOISE = re.compile(
    r"(?i)\s*[\(\[][^\)\]]*(?:"
    r"official|video|audio|lyric|full|song|music|hd|4k|visualizer|slowed|reverb"
    r")[^\)\]]*[\)\]]"
)
_FEAT_SUFFIX = re.compile(r"(?i)\s+[\(\[]?(?:feat\.?|ft\.?|featuring)\s+.+?[\)\]]?\s*$")
_PIPE_SPLIT = re.compile(r"\s*[｜|]\s*")
_ARTIST_SEP = re.compile(r"\s+[-–—]\s+")
_MULTI_SPACE = re.compile(r"\s+")


def parse_title(raw: str) -> tuple[str | None, str]:
    """Return (artist, title) from a YouTube title.

    Milder than rename_songs: drop leading/trailing labels, keep the song name,
    and treat a short ``Artist - Title`` prefix as the artist tag.
    """
    text = raw.strip()
    text = _PIPE_SPLIT.split(text, maxsplit=1)[0]
    text = _NOISE_LEADERS.sub("", text)
    text = _BRACKET_NOISE.sub("", text)
    text = _NOISE_TRAILERS.sub("", text)
    text = _FEAT_SUFFIX.sub("", text)
    text = _MULTI_SPACE.sub(" ", text).strip(" -–—")

    artist: str | None = None
    title = text
    parts = _ARTIST_SEP.split(text, maxsplit=1)
    if len(parts) == 2:
        left, right = parts[0].strip(), parts[1].strip()
        # Short left side looks like an artist name, not a long descriptive phrase.
        if left and right and len(left.split()) <= 4 and len(left) <= 40:
            artist, title = left, right

    title = _MULTI_SPACE.sub(" ", title).strip() or raw.strip()
    return artist, title


def sanitize_filename(name: str) -> str:
    """Remove characters that break filesystem paths."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = name.strip(" .")
    return name or "untitled"


# ── Env / config ────────────────────────────────────────────────────────────


def load_dotenv_files() -> None:
    """Load .env from the script folder, then the current working directory."""
    load_dotenv(SCRIPT_DIR / ".env")
    load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def first_value(*values: str | None) -> str | None:
    """Return the first non-empty string value."""
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def load_url(explicit: str | None) -> str:
    """Resolve playlist URL from flag, env, or playlist_url.txt."""
    load_dotenv_files()
    from_flag_or_env = first_value(explicit, os.getenv("PLAYLIST_URL"))
    if from_flag_or_env:
        return from_flag_or_env
    if DEFAULT_URL_FILE.is_file():
        for line in DEFAULT_URL_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    raise SystemExit(
        f"Pass --url, set PLAYLIST_URL in .env, or put a URL in {DEFAULT_URL_FILE}"
    )


# ── ffmpeg / JS runtime / cookies (same needs as the other YouTube tools) ───


def resolve_ffmpeg_location() -> str | None:
    """Return an ffmpeg binary path, including the bundled imageio-ffmpeg copy."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def require_ffmpeg() -> str:
    """Exit with a clear message when ffmpeg is missing."""
    location = resolve_ffmpeg_location()
    if location:
        return location
    console.print(
        Panel(
            "[bold red]ffmpeg is required for audio conversion.[/]\n"
            "Install it with [cyan]sudo apt install ffmpeg[/] or run:\n"
            "[cyan]uv sync[/] (bundles imageio-ffmpeg)",
            title="[red]Missing Dependency",
            border_style="red",
        )
    )
    sys.exit(1)


def _runtime_path(path: str | Path) -> Path | None:
    candidate = Path(path)
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _node_runtime_version(path: Path) -> tuple[int, int] | None:
    try:
        output = subprocess.check_output(
            [str(path), "--version"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.match(r"v?(\d+)\.(\d+)", output)
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2))
    if major > 20 or (major == 20 and minor >= 0):
        return major, minor
    return None


def find_js_runtime() -> tuple[str, str] | None:
    """Return the first supported JavaScript runtime for YouTube challenges."""
    candidates: list[tuple[str, Path | None]] = [
        ("deno", _runtime_path(shutil.which("deno") or "")),
        ("deno", _runtime_path(Path.home() / ".deno" / "bin" / "deno")),
        ("deno", _runtime_path(SCRIPT_DIR / ".bin" / "deno")),
        ("deno", _runtime_path(ROOT / "youtube_playlist_downloader" / ".bin" / "deno")),
        ("node", _runtime_path(shutil.which("node") or "")),
    ]
    for name, path in candidates:
        if not path:
            continue
        if name == "node" and not _node_runtime_version(path):
            continue
        return name, str(path)
    return None


def ensure_js_runtime(cookies_from_browser: str | None) -> None:
    if find_js_runtime():
        return
    cookie_note = (
        "\n[bold]Note:[/] Browser cookies force the web client, which needs a JS runtime."
        if cookies_from_browser
        else ""
    )
    console.print(
        Panel(
            "[bold red]No supported JavaScript runtime found for YouTube downloads.[/]\n"
            "Install Deno (recommended):\n"
            "[cyan]curl -fsSL https://deno.land/install.sh | sh[/]\n"
            "Then add [cyan]~/.deno/bin[/] to your PATH, or install Node.js 20+.\n"
            "See: [cyan]https://github.com/yt-dlp/yt-dlp/wiki/EJS[/]"
            f"{cookie_note}",
            title="[red]Missing Dependency",
            border_style="red",
        )
    )
    sys.exit(1)


def ensure_linux_cookie_deps(cookies_from_browser: str | None) -> None:
    if not cookies_from_browser or sys.platform != "linux":
        return
    try:
        import secretstorage  # noqa: F401
    except ImportError:
        console.print(
            Panel(
                "[bold red]Browser cookie extraction needs secretstorage on Linux.[/]\n"
                "Run [cyan]uv sync[/] from the repository root.",
                title="[red]Missing Dependency",
                border_style="red",
            )
        )
        sys.exit(1)


def apply_cookie_opts(
    opts: dict, cookies_from_browser: str | None, cookies_file: str | None
) -> dict:
    if cookies_file:
        opts["cookiefile"] = cookies_file
    elif cookies_from_browser:
        # Allow "chrome:Profile 1" style profile selectors from yt-dlp.
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def apply_ejs_opts(opts: dict) -> dict:
    runtime = find_js_runtime()
    if runtime:
        name, path = runtime
        opts["js_runtimes"] = {name: {"path": path}}
    return opts


def apply_network_opts(
    opts: dict, *, prefer_web_client: bool = False
) -> dict:
    opts.setdefault("retries", 10)
    opts.setdefault("fragment_retries", 10)
    opts.setdefault("file_access_retries", 3)
    opts.setdefault("extractor_retries", 3)
    opts.setdefault("socket_timeout", 60)
    opts.setdefault("sleep_interval_requests", 1)
    opts.setdefault("sleep_interval", 2)
    opts.setdefault("max_sleep_interval", 10)
    # Cookies only help the web client; put web first when authenticating.
    clients = ["web", "android"] if prefer_web_client else ["android", "web"]
    opts.setdefault(
        "extractor_args",
        {"youtube": {"player_client": clients}},
    )
    apply_ejs_opts(opts)
    return opts


_YOUTUBE_AUTH_COOKIE_NAMES = frozenset(
    {
        "LOGIN_INFO",
        "SID",
        "__Secure-1PSID",
        "__Secure-3PSID",
        "SAPISID",
        "__Secure-1PAPISID",
        "__Secure-3PAPISID",
    }
)


def inspect_youtube_cookies(
    cookies_from_browser: str | None, cookies_file: str | None
) -> tuple[int, int]:
    """Return (youtube_cookie_count, auth_cookie_count) for the chosen cookie source."""
    try:
        if cookies_file:
            from http.cookiejar import MozillaCookieJar

            jar = MozillaCookieJar(cookies_file)
            jar.load(ignore_discard=True, ignore_expires=True)
            cookies = list(jar)
        elif cookies_from_browser:
            from yt_dlp.cookies import extract_cookies_from_browser

            # "chrome:Profile 1" → browser="chrome", profile="Profile 1"
            parts = cookies_from_browser.split(":", 1)
            browser = parts[0]
            profile = parts[1] if len(parts) == 2 else None
            cookies = list(extract_cookies_from_browser(browser, profile=profile))
        else:
            return 0, 0
    except Exception as exc:
        console.print(
            Panel(
                f"[bold red]Could not read cookies:[/] {exc}\n"
                "Close the browser and retry, or export a [cyan]cookies.txt[/] file.",
                title="[red]Cookie error",
                border_style="red",
            )
        )
        sys.exit(1)

    youtube = [
        c
        for c in cookies
        if "youtube.com" in (getattr(c, "domain", None) or "")
    ]
    auth = [c for c in youtube if c.name in _YOUTUBE_AUTH_COOKIE_NAMES]
    # Google account cookies often live on .google.com and still authenticate YouTube.
    if not auth:
        auth = [
            c
            for c in cookies
            if c.name in _YOUTUBE_AUTH_COOKIE_NAMES
            and "google." in (getattr(c, "domain", None) or "")
        ]
    return len(youtube), len(auth)


def ensure_youtube_cookies(
    cookies_from_browser: str | None, cookies_file: str | None
) -> None:
    """Warn/exit when browser cookies were requested but YouTube login is missing."""
    if not cookies_from_browser and not cookies_file:
        return

    yt_count, auth_count = inspect_youtube_cookies(
        cookies_from_browser, cookies_file
    )
    source = (
        f"cookies file [cyan]{cookies_file}[/]"
        if cookies_file
        else f"browser [cyan]{cookies_from_browser}[/]"
    )

    if auth_count > 0:
        console.print(
            f"[dim]Cookies OK:[/] {yt_count} youtube.com cookie(s), "
            f"{auth_count} login cookie(s) from {source}"
        )
        return

    console.print(
        Panel(
            f"[bold red]No YouTube login cookies found in {source}.[/]\n\n"
            f"Loaded youtube.com cookies: [yellow]{yt_count}[/] "
            f"(login/auth cookies: [yellow]{auth_count}[/]).\n"
            "YouTube still treats the request as signed-out, so downloads fail "
            "with “Sign in to confirm you’re not a bot”.\n\n"
            "[bold]Fix (recommended):[/]\n"
            "1. Open YouTube in your browser and [bold]log in[/]\n"
            "2. Install a cookies export extension "
            "(e.g. “Get cookies.txt LOCALLY”)\n"
            "3. Export cookies while on youtube.com\n"
            "4. Run:\n"
            "[cyan]./iphone_playlist/run.sh --sample --cookies ~/Downloads/www.youtube.com_cookies.txt[/]\n\n"
            "Or log into YouTube in Chrome/Brave, fully quit the browser, then retry "
            "[cyan]--cookies-from-browser[/].",
            title="[red]YouTube login required",
            border_style="red",
        )
    )
    sys.exit(1)


RETRYABLE_ERROR_PATTERNS = (
    r"403",
    r"429",
    r"timed out",
    r"timeout",
    r"name or service not known",
    r"unable to download api page",
    r"connection reset",
    r"connection refused",
    r"network is unreachable",
    r"ssl:",
    r"unexpected EOF",
    r"http error",
)


def is_retryable_error(message: str) -> bool:
    lowered = message.lower()
    if "private video" in lowered or "sign in to confirm" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in RETRYABLE_ERROR_PATTERNS)


def cleanup_partial_files(directory: Path) -> None:
    for partial in directory.glob("*.part"):
        try:
            partial.unlink()
        except OSError:
            pass
    for thumb in directory.glob("*.webp"):
        try:
            thumb.unlink()
        except OSError:
            pass


# ── Output format → yt-dlp postprocessors ───────────────────────────────────


def audio_postprocessors(
    output_format: str,
    bit_depth: int,
    embed_metadata: bool,
    embed_art: bool,
) -> tuple[list[dict], dict]:
    """Build FFmpegExtractAudio (+ optional metadata/art) and extra ffmpeg args."""
    postprocessors: list[dict] = []
    pp_args: dict = {}

    fmt = output_format.lower()
    if fmt == "alac":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "alac",
            }
        )
        # Keep source sample rate; choose PCM sample format for ALAC bit depth.
        sample_fmt = "s32p" if bit_depth >= 24 else "s16p"
        pp_args["ExtractAudio+ffmpeg"] = ["-sample_fmt", sample_fmt]
    elif fmt == "aac":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "256",
            }
        )
    elif fmt == "flac":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "flac",
            }
        )
    elif fmt == "wav":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        )
    else:
        raise ValueError(f"Unsupported output format: {output_format}")

    if embed_metadata:
        postprocessors.append(
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
                "add_chapters": True,
            }
        )
    if embed_art and fmt in ("alac", "aac", "flac"):
        postprocessors.append({"key": "EmbedThumbnail"})

    return postprocessors, pp_args


def output_extension(output_format: str) -> str:
    mapping = {"alac": "m4a", "aac": "m4a", "flac": "flac", "wav": "wav"}
    return mapping[output_format.lower()]


# ── Download ────────────────────────────────────────────────────────────────


@dataclass
class Settings:
    url: str
    save_path: Path
    output_format: str
    source_format: str
    bit_depth: int
    skip_existing: bool
    clean_titles: bool
    embed_metadata: bool
    embed_art: bool
    cookies_from_browser: str | None
    cookies_file: str | None
    sample_limit: int | None = None


class PlaylistDownloader:
    """Download a playlist (or single video) as high-quality audio for iPhone."""

    MAX_RETRIES = 3

    def __init__(self, settings: Settings):
        self.s = settings
        self.downloaded: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []
        self._progress: Progress | None = None
        self._video_task: TaskID | None = None

    def _hook(self, data: dict) -> None:
        if self._progress is None or self._video_task is None:
            return
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate", 0)
            done = data.get("downloaded_bytes", 0)
            if total:
                self._progress.update(self._video_task, completed=done, total=total)
        elif status == "finished":
            total = data.get("total_bytes") or data.get("total_bytes_estimate", 0)
            if total:
                self._progress.update(self._video_task, completed=total, total=total)

    def _base_opts(self) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "skip_unavailable_fragments": True,
        }
        prefer_web = bool(self.s.cookies_from_browser or self.s.cookies_file)
        apply_network_opts(opts, prefer_web_client=prefer_web)
        apply_cookie_opts(opts, self.s.cookies_from_browser, self.s.cookies_file)
        return opts

    def _ydl_opts_for_item(
        self,
        outtmpl: str,
        playlist_title: str,
        index: int,
        total: int,
        artist: str | None,
        title: str,
    ) -> dict:
        ffmpeg = require_ffmpeg()
        postprocessors, pp_args = audio_postprocessors(
            self.s.output_format,
            self.s.bit_depth,
            self.s.embed_metadata,
            self.s.embed_art,
        )
        opts = self._base_opts()
        opts.update(
            {
                "ffmpeg_location": ffmpeg,
                "format": self.s.source_format,
                "outtmpl": outtmpl,
                "progress_hooks": [self._hook],
                "postprocessors": postprocessors,
                "postprocessor_args": pp_args,
                "nooverwrites": self.s.skip_existing,
                "writethumbnail": self.s.embed_art
                and self.s.output_format.lower() in ("alac", "aac", "flac"),
            }
        )
        if self.s.skip_existing:
            archive = self.s.save_path / ".download_archive"
            opts["download_archive"] = str(archive)

        # Force album / track / cleaned title into the container via ffmpeg.
        if self.s.embed_metadata:
            meta_args = [
                "-metadata",
                f"title={title}",
                "-metadata",
                f"album={playlist_title}",
                "-metadata",
                f"track={index}/{total}",
            ]
            if artist:
                meta_args.extend(["-metadata", f"artist={artist}"])
            existing = list(pp_args.get("FFmpegMetadata+ffmpeg", []))
            pp_args["FFmpegMetadata+ffmpeg"] = existing + meta_args
            opts["postprocessor_args"] = pp_args

        return opts

    def run(self) -> int:
        self.s.save_path.mkdir(parents=True, exist_ok=True)
        require_ffmpeg()

        console.print(
            Panel(
                "[cyan]Fetching playlist info...[/]",
                title="[bold]iPhone Playlist Audio",
                border_style="cyan",
            )
        )

        flat_opts = self._base_opts()
        flat_opts["extract_flat"] = "in_playlist"
        flat_opts["ignoreerrors"] = True

        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(self.s.url, download=False)

        if not info:
            console.print("[bold red]Could not read that URL.[/]")
            return 1

        is_playlist = "entries" in info
        if is_playlist:
            entries = [e for e in (info.get("entries") or []) if e]
            playlist_title = info.get("title") or "Playlist"
        else:
            entries = [info]
            playlist_title = info.get("title") or "Single Video"

        playlist_total = len(entries)
        sample_mode = self.s.sample_limit is not None and self.s.sample_limit > 0
        if sample_mode:
            entries = entries[: self.s.sample_limit]

        # Save into a subfolder named after the playlist.
        # Samples go under sample/ so a test listen never mixes with the full library.
        safe_album = sanitize_filename(playlist_title)
        if sample_mode:
            dest = self.s.save_path / "sample" / safe_album
        else:
            dest = self.s.save_path / safe_album
        dest.mkdir(parents=True, exist_ok=True)
        self.s.save_path = dest

        total = len(entries)
        pad = max(3, len(str(playlist_total if not sample_mode else total)))
        ext = output_extension(self.s.output_format)
        fmt_label = {
            "alac": f"ALAC (Apple Lossless, {self.s.bit_depth}-bit)",
            "aac": "AAC 256 kbps (smaller, second lossy encode)",
            "flac": "FLAC (lossless; needs a Files/third-party player)",
            "wav": "WAV (uncompressed)",
        }.get(self.s.output_format.lower(), self.s.output_format)

        tracks_line = (
            f"{total} of {playlist_total} (sample — listen before full download)"
            if sample_mode
            else str(total)
        )
        console.print(
            Panel(
                f"[bold green]Playlist:[/] {playlist_title}\n"
                f"[bold green]Tracks:[/]   {tracks_line}\n"
                f"[bold green]Save to:[/]  {dest.resolve()}\n"
                f"[bold green]Format:[/]   {fmt_label}\n"
                f"[bold green]Source:[/]   {self.s.source_format}\n"
                f"[bold green]Skip:[/]     {self.s.skip_existing}",
                title="[bold]Sample listen" if sample_mode else "[bold]Ready",
                border_style="yellow" if sample_mode else "green",
            )
        )

        with Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=None),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        ) as progress:
            self._progress = progress
            overall = progress.add_task(
                f"[cyan]Overall  [white]0 / {total}", total=total
            )
            try:
                for idx, entry in enumerate(entries, start=1):
                    video_id = entry.get("id") or ""
                    video_url = entry.get("url") or (
                        f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                    )
                    raw_title = (entry.get("title") or f"Track {idx}").strip()
                    artist, clean = (
                        parse_title(raw_title)
                        if self.s.clean_titles
                        else (None, raw_title)
                    )
                    display = clean[:55] + "…" if len(clean) > 55 else clean
                    file_stem = sanitize_filename(clean)
                    numbered = f"{idx:0{pad}d} - {file_stem}"

                    if not video_url:
                        self.failed.append(raw_title)
                        progress.advance(overall)
                        continue

                    expected = dest / f"{numbered}.{ext}"
                    if self.s.skip_existing and expected.exists():
                        self.skipped.append(raw_title)
                        task = progress.add_task(
                            f"[yellow]⊘ [{idx:>{pad}}/{total}] {display}",
                            total=1,
                            completed=1,
                        )
                        progress.remove_task(task)
                        progress.update(
                            overall,
                            completed=idx,
                            description=f"[cyan]Overall  [white]{idx} / {total}",
                        )
                        continue

                    self._video_task = progress.add_task(
                        f"[{idx:>{pad}}/{total}] {display}", total=100
                    )
                    outtmpl = str(dest / f"{numbered}.%(ext)s")
                    ydl_opts = self._ydl_opts_for_item(
                        outtmpl, playlist_title, idx, total, artist, clean
                    )

                    outcome = self._download_with_retries(ydl_opts, video_url)
                    if outcome == "downloaded":
                        self.downloaded.append(raw_title)
                        progress.update(
                            self._video_task,
                            description=f"[green]✓ [{idx:>{pad}}/{total}] {display}",
                        )
                    elif outcome == "skipped":
                        self.skipped.append(raw_title)
                        progress.update(
                            self._video_task,
                            description=f"[yellow]⊘ [{idx:>{pad}}/{total}] {display}",
                        )
                    else:
                        self.failed.append(raw_title)
                        cleanup_partial_files(dest)
                        progress.update(
                            self._video_task,
                            description=f"[red]✗ [{idx:>{pad}}/{total}] {display}",
                        )

                    progress.update(
                        overall,
                        completed=idx,
                        description=f"[cyan]Overall  [white]{idx} / {total}",
                    )
            except KeyboardInterrupt:
                console.print(
                    "\n[yellow]Interrupted. Re-run the same command — "
                    "finished tracks are skipped via the download archive.[/]"
                )
                cleanup_partial_files(dest)
                self._show_summary(total)
                return 1

        cleanup_partial_files(dest)
        self._show_summary(total)
        if sample_mode and not self.failed and self.downloaded:
            console.print(
                Panel(
                    "[bold]Listen to the sample on your phone (or locally), then:[/]\n"
                    "• Format / sound OK → run without [cyan]--sample[/] for the full playlist\n"
                    "• Prefer smaller files → [cyan]--format aac[/]\n"
                    "• Prefer different bit depth → [cyan]--bit-depth 16[/]\n\n"
                    f"[dim]Sample file(s) are in[/] [underline]{dest.resolve()}[/]\n"
                    "[dim]They do not affect the full-playlist download archive.[/]",
                    title="[bold yellow]Confirm quality",
                    border_style="yellow",
                )
            )
        return 1 if self.failed else 0

    def _download_with_retries(self, ydl_opts: dict, video_url: str) -> str:
        last_error: str | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    result = ydl.download([video_url])
                if result == 0:
                    return "downloaded"
                last_error = f"yt-dlp returned exit code {result}"
            except yt_dlp.utils.DownloadError as exc:
                last_error = str(exc)
            except OSError as exc:
                last_error = str(exc)

            if last_error and "already been downloaded" in last_error.lower():
                return "skipped"
            if last_error and is_retryable_error(last_error):
                if attempt < self.MAX_RETRIES:
                    wait = attempt * 3
                    console.print(
                        f"  [yellow]Retry {attempt}/{self.MAX_RETRIES - 1} "
                        f"in {wait}s...[/]"
                    )
                    time.sleep(wait)
                    continue
            break

        if last_error:
            console.print(f"  [dim red]{last_error}[/]")
        return "failed"

    def _show_summary(self, total: int) -> None:
        table = Table(
            title="Download Summary",
            border_style="bright_black",
            show_lines=True,
        )
        table.add_column("Status", style="bold", min_width=12)
        table.add_column("Count", justify="right", min_width=6)
        table.add_row("[green]Downloaded", str(len(self.downloaded)))
        table.add_row("[yellow]Skipped", str(len(self.skipped)))
        table.add_row("[red]Failed", str(len(self.failed)))
        table.add_row("Total", str(total))
        console.print()
        console.print(table)
        if self.failed:
            console.print("\n[bold red]Failed:[/]")
            for name in self.failed:
                console.print(f"  [red]•[/] {name}")
        console.print(
            f"\n[bold green]Saved to:[/] [underline]{self.s.save_path.resolve()}[/]"
        )


# ── --formats / --dry-run ───────────────────────────────────────────────────


class _QuietLogger:
    """Swallow yt-dlp console noise when we print our own errors."""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def report_youtube_auth_error(exc: BaseException, cookies: tuple[str | None, str | None]) -> None:
    """Print a short recovery hint when YouTube demands sign-in / cookies."""
    message = str(exc)
    cookies_from_browser, cookies_file = cookies
    has_cookies = bool(cookies_from_browser or cookies_file)
    bot = "sign in to confirm" in message.lower() or "not a bot" in message.lower()

    if bot and not has_cookies:
        console.print(
            Panel(
                "[bold red]YouTube is asking for a signed-in browser session.[/]\n\n"
                "Pass cookies from a browser where you are logged into YouTube:\n"
                "[cyan]./iphone_playlist/run.sh --formats --cookies-from-browser chrome[/]\n"
                "[cyan]./iphone_playlist/run.sh --formats --cookies /path/to/cookies.txt[/]\n\n"
                "Or set in [yellow]iphone_playlist/.env[/]:\n"
                "[cyan]COOKIES_FROM_BROWSER=chrome[/]\n\n"
                "Same flag is required for the real download.",
                title="[red]Authentication required",
                border_style="red",
            )
        )
        return

    if bot and has_cookies:
        console.print(
            Panel(
                "[bold red]YouTube still blocked the request with the cookies you provided.[/]\n"
                "Usually the browser profile is [bold]not logged into YouTube[/], "
                "or the cookies file is stale.\n\n"
                "1. Open [cyan]youtube.com[/] and confirm you see your avatar\n"
                "2. Export a fresh [cyan]cookies.txt[/] from that tab\n"
                "3. Retry with [cyan]--cookies /path/to/cookies.txt[/]",
                title="[red]Cookies rejected",
                border_style="red",
            )
        )
        return

    console.print(f"[bold red]Could not read that URL:[/] {message}")


def _resolve_first_video_url(url: str, cookies: tuple[str | None, str | None]) -> tuple[str, str] | None:
    """Return (video_url, label) for a single video or the first playlist entry."""
    cookies_from_browser, cookies_file = cookies
    flat_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "logger": _QuietLogger(),
    }
    prefer_web = bool(cookies_from_browser or cookies_file)
    apply_network_opts(flat_opts, prefer_web_client=prefer_web)
    apply_cookie_opts(flat_opts, cookies_from_browser, cookies_file)

    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return None

    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            return None
        first = entries[0]
        video_id = first.get("id") or ""
        video_url = first.get("url") or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        )
        if not video_url:
            return None
        label = (first.get("title") or video_id or "first track").strip()
        return video_url, label

    video_id = info.get("id") or ""
    video_url = info.get("webpage_url") or info.get("url") or url
    label = (info.get("title") or video_id or "video").strip()
    return video_url, label


def cmd_list_formats(url: str, source_format: str, cookies: tuple[str | None, str | None]) -> int:
    """Print audio streams YouTube offers and which format selector would pick."""
    cookies_from_browser, cookies_file = cookies
    resolved = _resolve_first_video_url(url, cookies)
    if not resolved:
        console.print("[bold red]Could not read that URL or playlist has no playable videos.[/]")
        return 1

    video_url, label = resolved
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "logger": _QuietLogger(),
    }
    prefer_web = bool(cookies_from_browser or cookies_file)
    apply_network_opts(opts, prefer_web_client=prefer_web)
    apply_cookie_opts(opts, cookies_from_browser, cookies_file)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        report_youtube_auth_error(exc, cookies)
        return 1

    if not info:
        console.print("[bold red]Could not load stream info for that video.[/]")
        return 1

    console.print(f"[dim]Showing streams for:[/] {info.get('title') or label}\n")

    formats = info.get("formats") or []
    audio_rows = []
    for fmt in formats:
        acodec = fmt.get("acodec") or "none"
        vcodec = fmt.get("vcodec") or "none"
        if acodec == "none":
            continue
        abr = fmt.get("abr") or fmt.get("tbr")
        audio_rows.append(
            {
                "id": fmt.get("format_id", ""),
                "ext": fmt.get("ext", ""),
                "acodec": acodec,
                "abr": abr,
                "asr": fmt.get("asr"),
                "note": fmt.get("format_note") or "",
                "audio_only": vcodec == "none",
            }
        )

    if not audio_rows:
        console.print(
            "[bold yellow]No audio streams listed.[/] "
            "YouTube may be blocking anonymous access — try "
            "[cyan]--cookies-from-browser chrome[/]."
        )
        return 1

    table = Table(title="Available audio streams", show_lines=False)
    table.add_column("ID")
    table.add_column("Ext")
    table.add_column("Codec")
    table.add_column("Bitrate", justify="right")
    table.add_column("Rate", justify="right")
    table.add_column("Note")
    table.add_column("Only?")

    audio_only = [r for r in audio_rows if r["audio_only"]]
    rows = audio_only or audio_rows
    for row in rows:
        abr = f"{row['abr']:.0f}k" if isinstance(row["abr"], (int, float)) else "—"
        asr = f"{row['asr']} Hz" if row["asr"] else "—"
        table.add_row(
            str(row["id"]),
            row["ext"],
            row["acodec"],
            abr,
            asr,
            row["note"],
            "yes" if row["audio_only"] else "muxed",
        )
    console.print(table)
    console.print(f"\n[bold]Source selector:[/] [cyan]{source_format}[/]")
    console.print(
        "[dim]yt-dlp will pick the best match for that selector "
        "(usually Opus ~160 kbps / 48 kHz when available).[/]"
    )
    return 0


def cmd_dry_run(url: str, cookies: tuple[str | None, str | None]) -> int:
    """List playlist tracks without downloading."""
    cookies_from_browser, cookies_file = cookies
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
    }
    prefer_web = bool(cookies_from_browser or cookies_file)
    apply_network_opts(opts, prefer_web_client=prefer_web)
    apply_cookie_opts(opts, cookies_from_browser, cookies_file)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        console.print("[bold red]Could not read that URL.[/]")
        return 1

    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        playlist_title = info.get("title") or "Playlist"
    else:
        entries = [info]
        playlist_title = info.get("title") or "Single Video"

    console.print(
        Panel(
            f"[bold]{playlist_title}[/]\n{len(entries)} track(s)",
            title="Dry run",
            border_style="cyan",
        )
    )
    pad = max(3, len(str(len(entries))))
    for idx, entry in enumerate(entries, start=1):
        raw = (entry.get("title") or "(untitled)").strip()
        artist, clean = parse_title(raw)
        artist_bit = f"  [dim]{artist}[/]" if artist else ""
        console.print(f"  {idx:0{pad}d}  {clean}{artist_bit}")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────


def resolve_settings(args: argparse.Namespace) -> Settings:
    load_dotenv_files()
    url = load_url(args.url)
    save_raw = first_value(args.output, os.getenv("SAVE_PATH"), str(DEFAULT_SAVE))
    save_path = Path(save_raw or DEFAULT_SAVE)
    if not save_path.is_absolute():
        save_path = Path.cwd() / save_path

    output_format = (
        first_value(args.format, os.getenv("OUTPUT_FORMAT"), "alac") or "alac"
    ).lower()
    if output_format not in OUTPUT_FORMATS:
        raise SystemExit(
            f"OUTPUT_FORMAT must be one of: {', '.join(OUTPUT_FORMATS)}"
        )

    source_format = (
        first_value(args.source, os.getenv("SOURCE_FORMAT"), "bestaudio/best")
        or "bestaudio/best"
    )

    bit_depth_raw = first_value(
        str(args.bit_depth) if args.bit_depth is not None else None,
        os.getenv("ALAC_BIT_DEPTH"),
        "24",
    )
    bit_depth = int(bit_depth_raw or "24")
    if bit_depth not in (16, 24):
        raise SystemExit("ALAC_BIT_DEPTH / --bit-depth must be 16 or 24")

    if args.no_skip_existing:
        skip_existing = False
    else:
        skip_existing = env_bool("SKIP_EXISTING", True)

    clean_titles = not args.no_clean_titles and env_bool("CLEAN_TITLES", True)
    if args.no_clean_titles:
        clean_titles = False

    embed_metadata = not args.no_metadata and env_bool("EMBED_METADATA", True)
    if args.no_metadata:
        embed_metadata = False

    embed_art = not args.no_art and env_bool("EMBED_ART", True)
    if args.no_art:
        embed_art = False

    cookies_from_browser = first_value(
        args.cookies_from_browser, os.getenv("COOKIES_FROM_BROWSER")
    )
    cookies_file = first_value(args.cookies, os.getenv("COOKIES_FILE"))

    sample_limit: int | None = None
    if getattr(args, "sample", None) is not None:
        sample_limit = int(args.sample)
        if sample_limit < 1:
            raise SystemExit("--sample must be at least 1")

    return Settings(
        url=url,
        save_path=save_path,
        output_format=output_format,
        source_format=source_format,
        bit_depth=bit_depth,
        skip_existing=skip_existing,
        clean_titles=clean_titles,
        embed_metadata=embed_metadata,
        embed_art=embed_art,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        sample_limit=sample_limit,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download a YouTube playlist as ALAC (default) for iPhone 15 Plus. "
            "CLI flags override .env."
        ),
    )
    parser.add_argument(
        "--url",
        help="Playlist or video URL (fallback: PLAYLIST_URL, then playlist_url.txt)",
    )
    parser.add_argument(
        "--output",
        help=f"Parent folder for downloads (fallback: SAVE_PATH, default {DEFAULT_SAVE})",
    )
    parser.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        help="Output codec: alac (default), aac, flac, wav",
    )
    parser.add_argument(
        "--source",
        help="yt-dlp format selector (fallback: SOURCE_FORMAT, default bestaudio/best)",
    )
    parser.add_argument(
        "--bit-depth",
        type=int,
        choices=(16, 24),
        help="ALAC sample bit depth (fallback: ALAC_BIT_DEPTH, default 24)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download even if the file or archive entry exists",
    )
    parser.add_argument(
        "--no-art",
        action="store_true",
        help="Do not embed thumbnails",
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not write title/artist/album/track tags",
    )
    parser.add_argument(
        "--no-clean-titles",
        action="store_true",
        help="Keep raw YouTube titles in filenames and tags",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Use cookies from a browser (chrome, firefox, brave, …)",
    )
    parser.add_argument(
        "--cookies",
        metavar="FILE",
        help="Path to a Netscape cookies.txt file",
    )
    parser.add_argument(
        "--formats",
        action="store_true",
        help="List available audio streams for the URL and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List playlist tracks without downloading",
    )
    parser.add_argument(
        "--sample",
        nargs="?",
        const=1,
        type=int,
        metavar="N",
        help=(
            "Download only the first track (or first N) into downloads/sample/ "
            "so you can check format and sound before the full playlist"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve URL early so --formats / --dry-run work without full settings.
    load_dotenv_files()
    url = load_url(args.url)
    cookies = (
        first_value(args.cookies_from_browser, os.getenv("COOKIES_FROM_BROWSER")),
        first_value(args.cookies, os.getenv("COOKIES_FILE")),
    )
    source = (
        first_value(args.source, os.getenv("SOURCE_FORMAT"), "bestaudio/best")
        or "bestaudio/best"
    )

    ensure_linux_cookie_deps(cookies[0])
    ensure_js_runtime(cookies[0])

    # dry-run only needs the playlist page; formats/download need a real YouTube login.
    if (cookies[0] or cookies[1]) and not args.dry_run:
        ensure_youtube_cookies(cookies[0], cookies[1])

    if args.formats:
        return cmd_list_formats(url, source, cookies)
    if args.dry_run:
        return cmd_dry_run(url, cookies)

    settings = resolve_settings(args)
    return PlaylistDownloader(settings).run()


if __name__ == "__main__":
    raise SystemExit(main())
