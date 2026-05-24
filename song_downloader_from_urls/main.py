#!/usr/bin/env python3
"""Song Downloader from URL List with rich progress tracking."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

load_dotenv()

console = Console()


# ── Config ──────────────────────────────────────────────────────────────────

def get_config() -> dict:
    url_list_file = os.getenv("URL_LIST_FILE", "urls.txt").strip()
    save_path = os.getenv("SAVE_PATH", "./downloads").strip()
    audio_format = os.getenv("AUDIO_FORMAT", "mp3").strip().lower()
    skip_existing = os.getenv("SKIP_EXISTING", "true").lower() == "true"

    if not Path(url_list_file).exists():
        console.print(
            Panel(
                f"[bold red]URL list file not found: {url_list_file}[/]\n"
                "Create a [yellow]urls.txt[/] file with one URL per line.",
                title="[red]File Not Found",
                border_style="red",
            )
        )
        sys.exit(1)

    return {
        "url_list_file": url_list_file,
        "save_path": save_path,
        "audio_format": audio_format,
        "skip_existing": skip_existing,
    }


# ── URL Loading ─────────────────────────────────────────────────────────────

def load_urls(url_list_file: str) -> list[str]:
    """Load URLs from a file, one per line."""
    try:
        with open(url_list_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()
                    and not line.startswith("#")]
        return urls
    except IOError as e:
        console.print(f"[bold red]Error reading URL list: {e}[/]")
        sys.exit(1)


# ── Title Cleaning ─────────────────────────────────────────────────────────

def clean_title(name: str) -> str:
    """Strip artist names, video labels, and movie names from a YouTube title."""
    import re
    name = re.split(r"\s*[｜|]\s*", name)[0]
    m = re.search(r'[\uff02"\u201c](.+?)[\uff02"\u201d]', name)
    if m:
        return m.group(1).strip()
    name = re.sub(r"^@\S+\s*[-\u2013\u2014\uff1a:]\s*", "", name)
    name = re.sub(r"^[^\uff1a]+\uff1a\s*", "", name)
    name = re.sub(
        r"(?i)\s*[\(\[][^\)\]]*(?:official|video|audio|lyric|full|song|slowed|reverbed|music|title|track|theme)[^\)\]]*[\)\]].*$",
        "", name,
    )
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    _np = (r"(?:Official\s+Music\s+Video|Official\s+(?:Video|Audio)|"
           r"Lyric(?:al)?\s+Video|Full\s+(?:Video|Song)|Music\s+Video|"
           r"Slowed(?:\s*[&]\s*Reverbed)?|Title\s+(?:Track|Song)|"
           r"Theme\s+Song|Lyric(?:al)?s?)")
    name = re.sub(rf"(?i)\s+{_np}(?=\s*[-\u2013\u2014]|\s|$)", "", name)
    name = re.sub(r"(?i)\s+(?:Song|Video)\s*$", "", name)
    name = re.sub(r"(?i)\s+f(?:ea)?t\.?\s+.*$", "", name)
    name = re.sub(r"\s*[\u2013\u2014]\s+.*$", "", name)
    name = re.sub(r"\s+-\s+.*$", "", name)
    name = re.sub(r"(?i)-lyric(?:al)?s?\s*$", "", name)
    name = re.sub(r"\s*[-\u2013]\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


# ── Download ────────────────────────────────────────────────────────────────

def create_ydl_opts(save_path: str, audio_format: str, skip_existing: bool) -> dict:
    """Create yt-dlp options for audio download."""
    audio_format_map = {
        "mp3": "mp3",
        "m4a": "m4a/bestaudio/best",
        "wav": "wav",
        "opus": "opus",
        "vorbis": "vorbis",
    }

    postprocessor_args = {}
    extract_audio_format = audio_format_map.get(audio_format, "mp3")

    return {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": extract_audio_format,
                "preferredquality": "320",
            }
        ],
        "outtmpl": os.path.join(save_path, "%(title)s.%(ext)s"),
        "replace_in_metadata": [
            ["title", r"\s*[｜|].*$", ""],
            ["title", r"^[^\uff1a]+\uff1a\s*", ""],
            ["title", r"(?i)\s*[\(\[][^\)\]]*(?:official|video|audio|lyric|full|song|slowed|reverbed|music|title|track|theme)[^\)\]]*[\)\]].*$", ""],
            ["title", r"\s*[\(\[][^\)\]]*[\)\]]", ""],
            ["title", r"(?i)\s+(?:Official\s+Music\s+Video|Official\s+(?:Video|Audio)|Lyric(?:al)?\s+Video|Full\s+(?:Video|Song)|Music\s+Video|Slowed(?:\s*[&]\s*Reverbed)?|Title\s+(?:Track|Song)|Lyric(?:al)?s?)(?=\s*[-\u2013\u2014]|\s|$)", ""],
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
        "socket_timeout": 30,
        "default_search": "auto",
        "nooverwrites": skip_existing,
        "no_post_overwrites": skip_existing,
    }


def download_songs(urls: list[str], config: dict, progress: Progress):
    """Download songs from the provided URLs."""
    ydl_opts = create_ydl_opts(
        config["save_path"],
        config["audio_format"],
        config["skip_existing"],
    )

    # Create save directory
    Path(config["save_path"]).mkdir(parents=True, exist_ok=True)

    successful = 0
    failed = 0
    failed_urls = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        task = progress.add_task(
            "[cyan]Downloading songs...", total=len(urls)
        )

        for url in urls:
            try:
                progress.console.print(f"[yellow]→[/] {url}")
                info = ydl.extract_info(url, download=False)
                raw_title = info.get("title", url) if info else url
                title = clean_title(raw_title)
                ext = config["audio_format"]
                expected_file = Path(config["save_path"]) / f"{title}.{ext}"

                if config["skip_existing"] and expected_file.exists():
                    progress.console.print(
                        f"[dim]⏭ Skipping (already exists): {title}[/]")
                    successful += 1
                    progress.advance(task)
                    continue

                ydl.download([url])
                successful += 1
                progress.advance(task)
            except Exception as e:
                failed += 1
                failed_urls.append((url, str(e)))
                progress.console.print(f"[red]✗ Failed: {e}[/]")
                progress.advance(task)

    return successful, failed, failed_urls


# ── Summary ─────────────────────────────────────────────────────────────────

def show_summary(successful: int, failed: int, failed_urls: list):
    """Display download summary."""
    total = successful + failed

    summary_table = Table(title="[bold]Download Summary[/]", show_header=False)
    summary_table.add_row("Total URLs", str(total))
    summary_table.add_row("Successful", f"[green]{successful}[/]")
    summary_table.add_row("Failed", f"[red]{failed}[/]")

    console.print()
    console.print(summary_table)

    if failed_urls:
        console.print("\n[bold red]Failed URLs:[/]")
        for url, error in failed_urls:
            console.print(f"  [red]✗[/] {url}")
            console.print(f"     {error}\n")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    console.print(
        Panel(
            "[bold cyan]🎵 Song Downloader from URL List[/]",
            border_style="cyan",
        )
    )

    config = get_config()
    urls = load_urls(config["url_list_file"])

    if not urls:
        console.print("[bold yellow]No URLs found in the list.[/]")
        sys.exit(0)

    console.print(
        f"[cyan]Loaded {len(urls)} URL(s) from [yellow]{config['url_list_file']}[/]")
    console.print(f"[cyan]Saving to: [yellow]{config['save_path']}[/]")
    console.print(
        f"[cyan]Format: [yellow]{config['audio_format'].upper()}[/]\n")

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        successful, failed, failed_urls = download_songs(
            urls, config, progress)

    show_summary(successful, failed, failed_urls)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
