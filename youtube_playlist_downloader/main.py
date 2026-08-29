#!/usr/bin/env python3
"""Unified CLI for downloading media and cleaning song filenames."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
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

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rename_songs import clean_title, rename_songs  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
console = Console()

AUDIO_FORMATS = ("mp3", "m4a", "wav", "opus", "vorbis")
VIDEO_QUALITIES = ("best", "1080", "720", "480", "360")


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


def load_urls(url_file: str | Path) -> list[str]:
    """Load URLs from a text file, one per line."""
    path = Path(url_file)
    if not path.is_file():
        console.print(f"[bold red]URL list file not found: {path}[/]")
        sys.exit(1)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        console.print(f"[bold red]Error reading URL list: {exc}[/]")
        sys.exit(1)

    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def resolve_ffmpeg_location() -> str | None:
    """Return an ffmpeg binary path for yt-dlp, including bundled fallbacks."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def require_ffmpeg() -> str:
    """Ensure ffmpeg is available before audio conversion."""
    ffmpeg_location = resolve_ffmpeg_location()
    if ffmpeg_location:
        return ffmpeg_location

    console.print(
        Panel(
            "[bold red]ffmpeg is required for audio downloads.[/]\n"
            "Install it with [cyan]sudo apt install ffmpeg[/] or run:\n"
            "[cyan]uv sync[/]",
            title="[red]Missing Dependency",
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
    """Return True when a download error looks transient."""
    lowered = message.lower()
    if "private video" in lowered or "sign in to confirm" in lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in RETRYABLE_ERROR_PATTERNS)


def apply_cookie_opts(opts: dict, cookies_from_browser: str | None, cookies_file: str | None) -> dict:
    """Add browser or file cookie settings to yt-dlp options."""
    if cookies_file:
        opts["cookiefile"] = cookies_file
    elif cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def _runtime_path(path: str | Path) -> Path | None:
    """Return the path when it points to an executable file."""
    candidate = Path(path)
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _node_runtime_version(path: Path) -> tuple[int, int] | None:
    """Return the major/minor Node version when it meets yt-dlp's minimum."""
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
    """Return the first supported JavaScript runtime available on this machine."""
    candidates: list[tuple[str, Path | None]] = [
        ("deno", _runtime_path(shutil.which("deno") or "")),
        ("deno", _runtime_path(Path.home() / ".deno" / "bin" / "deno")),
        ("deno", _runtime_path(SCRIPT_DIR / ".bin" / "deno")),
        ("node", _runtime_path(shutil.which("node") or "")),
    ]
    for name, path in candidates:
        if not path:
            continue
        if name == "node" and not _node_runtime_version(path):
            continue
        return name, str(path)
    return None


def ensure_linux_cookie_deps(cookies_from_browser: str | None) -> None:
    """Exit when browser cookies are requested on Linux without secretstorage."""
    if not cookies_from_browser or sys.platform != "linux":
        return
    try:
        import secretstorage  # noqa: F401
    except ImportError:
        console.print(
            Panel(
                "[bold red]Browser cookie extraction needs secretstorage on Linux.[/]\n"
                "Install it with:\n"
                "[cyan]uv add secretstorage[/]\n"
                "or reinstall dependencies from the repo root:\n"
                "[cyan]uv sync[/]",
                title="[red]Missing Dependency",
                border_style="red",
            )
        )
        sys.exit(1)


def ensure_js_runtime(cookies_from_browser: str | None) -> None:
    """Exit when YouTube downloads need a JS runtime but none is available."""
    if find_js_runtime():
        return

    cookie_note = (
        "\n[bold]Note:[/] With [cyan]--cookies-from-browser[/], yt-dlp must use the web "
        "client, which requires a JS runtime to solve YouTube challenges."
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


def apply_ejs_opts(opts: dict) -> dict:
    """Configure yt-dlp's YouTube challenge solver when a JS runtime is available."""
    runtime = find_js_runtime()
    if runtime:
        name, path = runtime
        opts["js_runtimes"] = {name: {"path": path}}
    return opts


def apply_network_opts(opts: dict) -> dict:
    """Add retry, timeout, and YouTube client settings to yt-dlp options."""
    opts.setdefault("retries", 10)
    opts.setdefault("fragment_retries", 10)
    opts.setdefault("file_access_retries", 3)
    opts.setdefault("extractor_retries", 3)
    opts.setdefault("socket_timeout", 60)
    opts.setdefault("sleep_interval_requests", 1)
    opts.setdefault("sleep_interval", 2)
    opts.setdefault("max_sleep_interval", 10)
    opts.setdefault(
        "extractor_args",
        {"youtube": {"player_client": ["android", "web"]}},
    )
    apply_ejs_opts(opts)
    return opts


def cleanup_partial_files(directory: Path) -> None:
    """Remove incomplete yt-dlp downloads (.part files)."""
    for partial in directory.glob("*.part"):
        try:
            partial.unlink()
        except OSError:
            pass


def audio_format_option(audio_format: str) -> str:
    """Map user-facing audio format names to yt-dlp codec values."""
    mapping = {
        "mp3": "mp3",
        "m4a": "m4a/bestaudio/best",
        "wav": "wav",
        "opus": "opus",
        "vorbis": "vorbis",
    }
    return mapping.get(audio_format.lower(), "mp3")


def create_audio_ydl_opts(
    save_path: str | Path,
    audio_format: str,
    skip_existing: bool,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> dict:
    """Build yt-dlp options for audio-only downloads."""
    extract_format = audio_format_option(audio_format)
    opts = {
        "ffmpeg_location": require_ffmpeg(),
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": extract_format,
                "preferredquality": "320",
            }
        ],
        "outtmpl": os.path.join(str(save_path), "%(title)s.%(ext)s"),
        "replace_in_metadata": [
            ["title", r"\s*[｜|].*$", ""],
            ["title", r"^[^\uff1a]+\uff1a\s*", ""],
            [
                "title",
                r"(?i)\s*[\(\[][^\)\]]*(?:official|video|audio|lyric|full|song|slowed|reverbed|music|title|track|theme)[^\)\]]*[\)\]].*$",
                "",
            ],
            ["title", r"\s*[\(\[][^\)\]]*[\)\]]", ""],
            [
                "title",
                r"(?i)\s+(?:Official\s+Music\s+Video|Official\s+(?:Video|Audio)|Lyric(?:al)?\s+Video|Full\s+(?:Video|Song)|Music\s+Video|Slowed(?:\s*[&]\s*Reverbed)?|Title\s+(?:Track|Song)|Lyric(?:al)?s?)(?=\s*[-\u2013\u2014]|\s|$)",
                "",
            ],
            ["title", r"(?i)\s+(?:Song|Video)\s*$", ""],
            ["title", r"(?i)\s+f(?:ea)?t\.?\s+.*$", ""],
            ["title", r"\s*[\u2013\u2014]\s+.*$", ""],
            ["title", r"\s+-\s+.*$", ""],
            ["title", r"(?i)-lyric(?:al)?s?\s*$", ""],
            ["title", r"\s*[-\u2013]\s*$", ""],
            ["title", r"\s+", " "],
        ],
        "quiet": False,
        "no_warnings": False,
        "skip_unavailable_fragments": True,
        "default_search": "auto",
        "nooverwrites": skip_existing,
        "no_post_overwrites": skip_existing,
    }
    apply_network_opts(opts)
    apply_cookie_opts(opts, cookies_from_browser, cookies_file)
    return opts


def ydl_video_format(audio_only: bool, video_quality: str) -> str:
    """Build the yt-dlp format string for video or audio downloads."""
    if audio_only:
        return "bestaudio/best"
    if video_quality == "best":
        return "bestvideo+bestaudio/best"
    return (
        f"bestvideo[height<={video_quality}]"
        f"+bestaudio/best[height<={video_quality}]"
    )


def maybe_rename_songs(save_path: Path, enabled: bool) -> None:
    """Rename downloaded MP3 files to clean song titles."""
    if not enabled:
        return

    console.print()
    console.print(
        Panel(
            "[cyan]Cleaning MP3 filenames...[/]",
            title="[bold]Rename Songs",
            border_style="cyan",
        )
    )
    rename_songs(save_path, dry_run=False)


def show_list_summary(successful: int, failed: int, failed_urls: list[tuple[str, str]]) -> None:
    """Print a summary for URL-list downloads."""
    total = successful + failed
    table = Table(title="[bold]Download Summary[/]", show_header=False)
    table.add_row("Total URLs", str(total))
    table.add_row("Successful", f"[green]{successful}[/]")
    table.add_row("Failed", f"[red]{failed}[/]")
    console.print()
    console.print(table)

    if failed_urls:
        console.print("\n[bold red]Failed URLs:[/]")
        for url, error in failed_urls:
            console.print(f"  [red]✗[/] {url}")
            console.print(f"     {error}\n")


class UrlDownloader:
    """Download one YouTube video or playlist URL."""

    MAX_DOWNLOAD_RETRIES = 3

    def __init__(
        self,
        url: str,
        save_path: Path,
        audio_only: bool,
        video_quality: str,
        skip_existing: bool,
        rename_after: bool,
        cookies_from_browser: str | None = None,
        cookies_file: str | None = None,
    ):
        self.url = url
        self.save_path = save_path
        self.audio_only = audio_only
        self.video_quality = video_quality
        self.skip_existing = skip_existing
        self.rename_after = rename_after
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.downloaded: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []
        self._progress: Progress | None = None
        self._video_task: TaskID | None = None

    def _hook(self, data: dict) -> None:
        """Update per-item progress from yt-dlp hooks."""
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
        elif status == "error":
            self._progress.update(
                self._video_task,
                description="[red]Error during download",
            )

    def run(self) -> int:
        """Fetch metadata and download the URL."""
        self.save_path.mkdir(parents=True, exist_ok=True)
        ffmpeg_location = require_ffmpeg() if self.audio_only else resolve_ffmpeg_location()

        console.print(
            Panel(
                "[cyan]Fetching info from YouTube...[/]",
                title="[bold]YouTube Downloader",
                border_style="cyan",
            )
        )

        flat_opts = apply_network_opts(
            apply_cookie_opts(
                {
                    "quiet": True,
                    "extract_flat": "in_playlist",
                    "ignoreerrors": True,
                },
                self.cookies_from_browser,
                self.cookies_file,
            )
        )
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)

        if not info:
            console.print(
                "[bold red]Could not fetch info. Check the URL and try again.[/]"
            )
            return 1

        is_playlist = "entries" in info
        if is_playlist:
            entries = [entry for entry in info.get("entries", []) if entry]
            playlist_title = info.get("title", "Unknown Playlist")
        else:
            entries = [info]
            playlist_title = info.get("title", "Single Video")

        total = len(entries)
        pad = len(str(total))
        if self.audio_only:
            fmt_label = "Audio only (MP3)"
        elif self.video_quality != "best":
            fmt_label = f"Video ({self.video_quality}p)"
        else:
            fmt_label = "Video (best quality)"

        console.print(
            Panel(
                f"[bold green]Title:[/]   {playlist_title}\n"
                f"[bold green]Videos:[/]  {total}\n"
                f"[bold green]Save to:[/] {self.save_path.resolve()}\n"
                f"[bold green]Format:[/]  {fmt_label}\n"
                f"[bold green]Skip existing:[/] {self.skip_existing}",
                title="[bold]Playlist Info",
                border_style="green",
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
                    video_id = entry.get("id", "")
                    video_url = entry.get("url") or (
                        f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                    )
                    title = entry.get("title") or f"Video {idx}"
                    short_title = title[:55] + "…" if len(title) > 55 else title

                    if not video_url:
                        self.failed.append(title)
                        progress.advance(overall)
                        continue

                    task_label = f"[{idx:>{pad}}/{total}] {short_title}"
                    self._video_task = progress.add_task(task_label, total=100)

                    if is_playlist:
                        outtmpl = str(
                            self.save_path / f"{idx:0{pad}d} - %(title)s.%(ext)s"
                        )
                    else:
                        outtmpl = str(self.save_path / "%(title)s.%(ext)s")

                    ydl_opts: dict = apply_network_opts(
                        apply_cookie_opts(
                            {
                                "format": ydl_video_format(
                                    self.audio_only, self.video_quality
                                ),
                                "outtmpl": outtmpl,
                                "progress_hooks": [self._hook],
                                "quiet": True,
                                "no_warnings": True,
                                "ignoreerrors": False,
                                "nooverwrites": self.skip_existing,
                                "postprocessors": [],
                            },
                            self.cookies_from_browser,
                            self.cookies_file,
                        )
                    )
                    if ffmpeg_location:
                        ydl_opts["ffmpeg_location"] = ffmpeg_location
                    if self.audio_only:
                        ydl_opts["postprocessors"].append(
                            {
                                "key": "FFmpegExtractAudio",
                                "preferredcodec": "mp3",
                                "preferredquality": "192",
                            }
                        )

                    outcome = self._download_with_retries(ydl_opts, video_url)
                    if outcome == "downloaded":
                        self.downloaded.append(title)
                        progress.update(
                            self._video_task,
                            description=f"[green]✓ [{idx:>{pad}}/{total}] {short_title}",
                        )
                    elif outcome == "skipped":
                        self.skipped.append(title)
                        progress.update(
                            self._video_task,
                            description=f"[yellow]⊘ [{idx:>{pad}}/{total}] {short_title}",
                        )
                    else:
                        self.failed.append(title)
                        cleanup_partial_files(self.save_path)
                        progress.update(
                            self._video_task,
                            description=f"[red]✗ [{idx:>{pad}}/{total}] {short_title}",
                        )

                    progress.update(
                        overall,
                        completed=idx,
                        description=f"[cyan]Overall  [white]{idx} / {total}",
                    )
            except KeyboardInterrupt:
                console.print(
                    "\n[yellow]Download interrupted. Re-run the same command to "
                    "continue — existing files are skipped.[/]"
                )
                cleanup_partial_files(self.save_path)
                self._show_summary(total)
                if self.audio_only:
                    maybe_rename_songs(self.save_path, self.rename_after)
                return 1

        self._show_summary(total)
        if self.audio_only:
            maybe_rename_songs(self.save_path, self.rename_after)
        return 1 if self.failed else 0

    def _download_with_retries(self, ydl_opts: dict, video_url: str) -> str:
        """Download one video, retrying transient failures."""
        last_error: str | None = None
        for attempt in range(1, self.MAX_DOWNLOAD_RETRIES + 1):
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

            if last_error and is_retryable_error(last_error):
                if attempt < self.MAX_DOWNLOAD_RETRIES:
                    wait = attempt * 3
                    console.print(
                        f"  [yellow]Retry {attempt}/{self.MAX_DOWNLOAD_RETRIES - 1} "
                        f"in {wait}s...[/]"
                    )
                    time.sleep(wait)
                    continue
            break

        if last_error:
            console.print(f"  [dim red]{last_error}[/]")
        if last_error and "already been downloaded" in last_error.lower():
            return "skipped"
        return "failed"

    def _show_summary(self, total: int) -> None:
        """Print the playlist download summary."""
        table = Table(title="Download Summary", border_style="bright_black", show_lines=True)
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
            f"\n[bold green]Saved to:[/] [underline]{self.save_path.resolve()}[/]"
        )


def download_url_list(
    urls: list[str],
    save_path: Path,
    audio_format: str,
    skip_existing: bool,
    rename_after: bool,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> int:
    """Download audio from a list of direct URLs."""
    save_path.mkdir(parents=True, exist_ok=True)
    ydl_opts = create_audio_ydl_opts(
        save_path,
        audio_format,
        skip_existing,
        cookies_from_browser,
        cookies_file,
    )

    successful = 0
    failed = 0
    failed_urls: list[tuple[str, str]] = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl, Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("[cyan]Downloading songs...", total=len(urls))

        for url in urls:
            try:
                progress.console.print(f"[yellow]→[/] {url}")
                info = ydl.extract_info(url, download=False)
                raw_title = info.get("title", url) if info else url
                title = clean_title(raw_title)
                expected_file = save_path / f"{title}.{audio_format.lower()}"

                if skip_existing and expected_file.exists():
                    progress.console.print(
                        f"[dim]⏭ Skipping (already exists): {title}[/]"
                    )
                    successful += 1
                    progress.advance(task)
                    continue

                ydl.download([url])
                successful += 1
                progress.advance(task)
            except Exception as exc:
                failed += 1
                failed_urls.append((url, str(exc)))
                progress.console.print(f"[red]✗ Failed: {exc}[/]")
                progress.advance(task)

    show_list_summary(successful, failed, failed_urls)
    if audio_format.lower() == "mp3":
        maybe_rename_songs(save_path, rename_after)
    return 1 if failed else 0


def resolve_rename_after(args: argparse.Namespace, default: bool) -> bool:
    """Resolve whether to rename MP3 files after download."""
    if args.rename is not None:
        return args.rename
    load_dotenv_files()
    return env_bool("RENAME_AFTER_DOWNLOAD", default)


def resolve_cookie_args(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve cookie settings from CLI flags and env fallbacks."""
    cookies_from_browser = first_value(
        getattr(args, "cookies_from_browser", None),
        os.getenv("COOKIES_FROM_BROWSER"),
    )
    cookies_file = first_value(
        getattr(args, "cookies", None),
        os.getenv("COOKIES_FILE"),
    )
    return cookies_from_browser, cookies_file


def resolve_download_url_args(
    args: argparse.Namespace,
) -> tuple[str, Path, bool, str, bool, bool, str | None, str | None]:
    """Resolve URL download settings from CLI flags and env fallbacks."""
    load_dotenv_files()
    url = first_value(args.url, os.getenv("PLAYLIST_URL"))
    if not url:
        console.print(
            Panel(
                "[bold red]No URL provided.[/]\n"
                "Use [cyan]--url[/] or set [yellow]PLAYLIST_URL[/] in .env.",
                title="[red]Missing Input",
                border_style="red",
            )
        )
        sys.exit(1)

    save_path = Path(
        first_value(args.output, os.getenv("SAVE_PATH"), "./downloads") or "./downloads"
    )
    audio_only = args.audio_only if args.audio_only is not None else env_bool(
        "AUDIO_ONLY", False
    )
    video_quality = first_value(args.quality, os.getenv("VIDEO_QUALITY"), "best") or "best"
    skip_existing = (
        not args.no_skip_existing
        if args.no_skip_existing
        else env_bool("SKIP_EXISTING", True)
    )
    rename_after = resolve_rename_after(args, default=audio_only)
    cookies_from_browser, cookies_file = resolve_cookie_args(args)
    return (
        url,
        save_path,
        audio_only,
        video_quality,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    )


def resolve_download_list_args(
    args: argparse.Namespace,
) -> tuple[list[str], Path, str, bool, bool, str | None, str | None]:
    """Resolve URL-list download settings from CLI flags and env fallbacks."""
    load_dotenv_files()
    url_file = first_value(args.file, os.getenv("URL_LIST_FILE"), "urls.txt") or "urls.txt"
    urls = load_urls(url_file)
    if not urls:
        console.print("[bold yellow]No URLs found in the list.[/]")
        sys.exit(0)

    save_path = Path(
        first_value(args.output, os.getenv("SAVE_PATH"), "./downloads") or "./downloads"
    )
    audio_format = (
        first_value(args.format, os.getenv("AUDIO_FORMAT"), "mp3") or "mp3"
    ).lower()
    skip_existing = (
        not args.no_skip_existing
        if args.no_skip_existing
        else env_bool("SKIP_EXISTING", True)
    )
    rename_after = resolve_rename_after(args, default=True)
    cookies_from_browser, cookies_file = resolve_cookie_args(args)
    return (
        urls,
        save_path,
        audio_format,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    )


def prepare_youtube_download(cookies_from_browser: str | None) -> None:
    """Validate dependencies needed for YouTube downloads."""
    ensure_linux_cookie_deps(cookies_from_browser)
    ensure_js_runtime(cookies_from_browser)


def cmd_download_url(args: argparse.Namespace) -> int:
    """Handle the download-url subcommand."""
    (
        url,
        save_path,
        audio_only,
        video_quality,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    ) = resolve_download_url_args(args)
    prepare_youtube_download(cookies_from_browser)
    console.print(
        Panel(
            "[bold cyan]Download URL[/]",
            border_style="cyan",
        )
    )
    downloader = UrlDownloader(
        url,
        save_path,
        audio_only,
        video_quality,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    )
    return downloader.run()


def cmd_download_list(args: argparse.Namespace) -> int:
    """Handle the download-list subcommand."""
    (
        urls,
        save_path,
        audio_format,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    ) = resolve_download_list_args(args)
    prepare_youtube_download(cookies_from_browser)
    console.print(
        Panel(
            "[bold cyan]Download URL List[/]",
            border_style="cyan",
        )
    )
    console.print(f"[cyan]Loaded {len(urls)} URL(s)[/]")
    console.print(f"[cyan]Saving to: [yellow]{save_path}[/]")
    console.print(f"[cyan]Format: [yellow]{audio_format.upper()}[/]\n")
    return download_url_list(
        urls,
        save_path,
        audio_format,
        skip_existing,
        rename_after,
        cookies_from_browser,
        cookies_file,
    )


def cmd_rename(args: argparse.Namespace) -> int:
    """Handle the rename subcommand."""
    directory = first_value(getattr(args, "dir", None), args.directory)
    if not directory:
        console.print("[bold red]Provide a folder with --dir.[/]")
        return 1
    rename_songs(directory, dry_run=not args.apply)
    return 0


def add_cookie_args(parser: argparse.ArgumentParser) -> None:
    """Add cookie-related CLI flags to a download subcommand parser."""
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Use cookies from a browser (e.g. chrome, firefox, brave)",
    )
    parser.add_argument(
        "--cookies",
        metavar="FILE",
        help="Path to a Netscape cookies.txt file",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the unified CLI parser."""
    parser = argparse.ArgumentParser(
        description="Download media from YouTube and clean MP3 filenames.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    url_parser = subparsers.add_parser(
        "download-url",
        help="Download one video or playlist URL",
    )
    url_parser.add_argument(
        "--url",
        help="YouTube video or playlist URL (fallback: PLAYLIST_URL in .env)",
    )
    url_parser.add_argument(
        "--output",
        help="Folder to save downloads (fallback: SAVE_PATH in .env)",
    )
    url_parser.add_argument(
        "--audio-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Download audio only as MP3",
    )
    url_parser.add_argument(
        "--quality",
        choices=VIDEO_QUALITIES,
        help="Video quality when not using --audio-only",
    )
    url_parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download files even if they already exist",
    )
    url_parser.add_argument(
        "--rename",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Rename MP3 files to song titles after download (default: on for --audio-only)",
    )
    add_cookie_args(url_parser)
    url_parser.set_defaults(func=cmd_download_url)

    list_parser = subparsers.add_parser(
        "download-list",
        help="Download audio from a text file of URLs",
    )
    list_parser.add_argument(
        "--file",
        help="Text file with one URL per line (fallback: URL_LIST_FILE in .env)",
    )
    list_parser.add_argument(
        "--output",
        help="Folder to save downloads (fallback: SAVE_PATH in .env)",
    )
    list_parser.add_argument(
        "--format",
        choices=AUDIO_FORMATS,
        help="Audio format (fallback: AUDIO_FORMAT in .env)",
    )
    list_parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-download files even if they already exist",
    )
    list_parser.add_argument(
        "--rename",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Rename MP3 files to song titles after download (default: on for MP3)",
    )
    add_cookie_args(list_parser)
    list_parser.set_defaults(func=cmd_download_list)

    rename_parser = subparsers.add_parser(
        "rename",
        help="Clean MP3 filenames to song titles only",
    )
    rename_parser.add_argument(
        "--dir",
        help="Folder containing MP3 files",
    )
    rename_parser.add_argument(
        "directory",
        nargs="?",
        help="Folder containing MP3 files",
    )
    rename_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files (default: dry run)",
    )
    rename_parser.set_defaults(func=cmd_rename)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the unified CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
