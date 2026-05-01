#!/usr/bin/env python3
"""YouTube Playlist / Video Downloader with rich progress tracking."""

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
    TaskID,
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
    url = os.getenv("PLAYLIST_URL", "").strip()
    save_path = os.getenv("SAVE_PATH", "./downloads").strip()
    audio_only = os.getenv("AUDIO_ONLY", "false").lower() == "true"
    video_quality = os.getenv("VIDEO_QUALITY", "best").strip()
    skip_existing = os.getenv("SKIP_EXISTING", "true").lower() == "true"

    if not url:
        console.print(
            Panel(
                "[bold red]PLAYLIST_URL is not set.[/]\n"
                "Edit [yellow].env[/] and set [cyan]PLAYLIST_URL[/] to a YouTube "
                "playlist or video URL.",
                title="[red]Configuration Error",
                border_style="red",
            )
        )
        sys.exit(1)

    return {
        "url": url,
        "save_path": save_path,
        "audio_only": audio_only,
        "video_quality": video_quality,
        "skip_existing": skip_existing,
    }


# ── Downloader ───────────────────────────────────────────────────────────────

class PlaylistDownloader:
    def __init__(self, cfg: dict):
        self.url = cfg["url"]
        self.save_path = Path(cfg["save_path"])
        self.audio_only = cfg["audio_only"]
        self.video_quality = cfg["video_quality"]
        self.skip_existing = cfg["skip_existing"]

        self.downloaded: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

        self._progress: Progress | None = None
        self._video_task: TaskID | None = None

    # ── Format string ──────────────────────────────────────────────────────

    def _ydl_format(self) -> str:
        if self.audio_only:
            return "bestaudio/best"
        if self.video_quality == "best":
            return "bestvideo+bestaudio/best"
        return (
            f"bestvideo[height<={self.video_quality}]"
            f"+bestaudio/best[height<={self.video_quality}]"
        )

    # ── yt-dlp progress hook ───────────────────────────────────────────────

    def _hook(self, d: dict):
        if self._progress is None or self._video_task is None:
            return

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            done = d.get("downloaded_bytes", 0)
            if total:
                self._progress.update(
                    self._video_task, completed=done, total=total)
        elif status == "finished":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            if total:
                self._progress.update(
                    self._video_task, completed=total, total=total)
        elif status == "error":
            self._progress.update(
                self._video_task,
                description="[red]Error during download",
            )

    # ── Main entry ────────────────────────────────────────────────────────

    def run(self):
        self.save_path.mkdir(parents=True, exist_ok=True)

        console.print(
            Panel(
                "[cyan]Fetching info from YouTube...[/]",
                title="[bold]YouTube Downloader",
                border_style="cyan",
            )
        )

        # Flat extraction to list videos without downloading
        flat_opts = {
            "quiet": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)

        if not info:
            console.print(
                "[bold red]Could not fetch info. Check the URL and try again.[/]")
            sys.exit(1)

        is_playlist = "entries" in info
        if is_playlist:
            entries = [e for e in info.get("entries", []) if e]
            playlist_title = info.get("title", "Unknown Playlist")
        else:
            entries = [info]
            playlist_title = info.get("title", "Single Video")

        total = len(entries)
        pad = len(str(total))  # digit width for zero-padding

        fmt_label = "Audio only (MP3)" if self.audio_only else f"Video ({self.video_quality}p)" if self.video_quality != "best" else "Video (best quality)"

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

        # ── Progress bars ─────────────────────────────────────────────────
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

            for idx, entry in enumerate(entries, start=1):
                video_id = entry.get("id", "")
                video_url = (
                    entry.get("url")
                    or (f"https://www.youtube.com/watch?v={video_id}" if video_id else None)
                )
                title = entry.get("title") or f"Video {idx}"
                short_title = title[:55] + "…" if len(title) > 55 else title

                if not video_url:
                    self.failed.append(title)
                    progress.advance(overall)
                    continue

                # Per-video progress task
                task_label = f"[{idx:>{pad}}/{total}] {short_title}"
                self._video_task = progress.add_task(task_label, total=100)

                # Output template
                if is_playlist:
                    outtmpl = str(
                        self.save_path /
                        f"%(playlist_index)0{pad}d - %(title)s.%(ext)s"
                    )
                else:
                    outtmpl = str(self.save_path / "%(title)s.%(ext)s")

                ydl_opts: dict = {
                    "format": self._ydl_format(),
                    "outtmpl": outtmpl,
                    "progress_hooks": [self._hook],
                    "quiet": True,
                    "no_warnings": True,
                    "ignoreerrors": False,
                    "nooverwrites": self.skip_existing,
                    "postprocessors": [],
                }

                if self.audio_only:
                    ydl_opts["postprocessors"].append(
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    )

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ret = ydl.download([video_url])

                    if ret == 0:
                        self.downloaded.append(title)
                        progress.update(
                            self._video_task,
                            description=f"[green]✓ [{idx:>{pad}}/{total}] {short_title}",
                        )
                    else:
                        # yt-dlp returned non-zero (e.g. already exists / skipped)
                        self.skipped.append(title)
                        progress.update(
                            self._video_task,
                            description=f"[yellow]⊘ [{idx:>{pad}}/{total}] {short_title}",
                        )

                except yt_dlp.utils.DownloadError as exc:
                    self.failed.append(title)
                    progress.update(
                        self._video_task,
                        description=f"[red]✗ [{idx:>{pad}}/{total}] {short_title}",
                    )
                    console.print(f"  [dim red]{exc}[/]")

                progress.update(
                    overall,
                    completed=idx,
                    description=f"[cyan]Overall  [white]{idx} / {total}",
                )

        self._show_summary(total)

    # ── Summary table ─────────────────────────────────────────────────────

    def _show_summary(self, total: int):
        table = Table(title="Download Summary",
                      border_style="bright_black", show_lines=True)
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


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    cfg = get_config()
    downloader = PlaylistDownloader(cfg)
    downloader.run()


if __name__ == "__main__":
    main()
