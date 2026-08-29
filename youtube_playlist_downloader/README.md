# YouTube Playlist Downloader

Download a YouTube playlist or a single video as MP3 or video. Also download from a text file of URLs, and clean up MP3 filenames.

CLI flags override `.env`. If a flag is omitted, the matching `.env` value is used.

## Features

- Download an entire playlist or one video
- Audio-only MP3 (192 kbps, good for stories and spoken word) or video at a chosen quality
- Skip files that already exist (re-run to continue an interrupted playlist)
- Download from a text file of URLs (`mp3`, `m4a`, `wav`, `opus`, `vorbis`)
- Optional filename cleanup after download
- Browser cookies or a cookies.txt file for bot-check / age-restricted videos
- Bundled ffmpeg when system ffmpeg is missing
- Uses Deno or Node.js 20+ for YouTube's JavaScript challenges

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- Internet connection
- ffmpeg (system install or bundled via `imageio-ffmpeg`)
- Deno (recommended) or Node.js 20+ for YouTube downloads

## Install

```bash
git clone git@github.com:abusaidshabib/automation.git
cd automation
uv sync
chmod +x youtube_playlist_downloader/run.sh
```

HTTPS:

```bash
git clone https://github.com/abusaidshabib/automation.git
cd automation
uv sync
```

Install uv if needed:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

`uv sync` creates `.venv` at the repository root and installs dependencies from `pyproject.toml` / `uv.lock`.

### FFmpeg

Audio conversion needs ffmpeg.

- Bundled (default): `imageio-ffmpeg` from `uv sync`. Used automatically if system ffmpeg is missing.
- System install:
  - Linux: `sudo apt-get install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: `winget install FFmpeg`

### JavaScript runtime

YouTube downloads need Deno or Node.js 20+.

```bash
curl -fsSL https://deno.land/install.sh | sh
```

Then add `~/.deno/bin` to your PATH, or install Node.js 20+. See [yt-dlp EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## How to run

Run from the **repository root**. `run.sh` calls `uv run` for you.

```bash
./youtube_playlist_downloader/run.sh <command> [options]
```

No arguments defaults to `download-url` (uses `.env` if present):

```bash
./youtube_playlist_downloader/run.sh
```

Same thing with uv:

```bash
uv run python youtube_playlist_downloader/main.py <command> [options]
```

From `youtube_playlist_downloader/`:

```bash
uv run --project .. python main.py <command> [options]
```

Show help:

```bash
./youtube_playlist_downloader/run.sh --help
./youtube_playlist_downloader/run.sh download-url --help
./youtube_playlist_downloader/run.sh download-list --help
./youtube_playlist_downloader/run.sh rename --help
```

Windows (no `run.sh`):

```bash
uv run python youtube_playlist_downloader/main.py download-url --help
```

## Configure defaults with `.env`

```bash
cp youtube_playlist_downloader/.env.example youtube_playlist_downloader/.env
```

`.env` is loaded from `youtube_playlist_downloader/.env`, then from the current working directory. CLI flags always win.

| Variable | Used by | Default | Meaning |
|----------|---------|---------|---------|
| `PLAYLIST_URL` | `download-url` | (required unless `--url`) | Video or playlist URL |
| `SAVE_PATH` | `download-url`, `download-list` | `./downloads` | Output folder (absolute or relative to the current directory) |
| `AUDIO_ONLY` | `download-url` | `false` | `true` = MP3 only; `false` = video |
| `VIDEO_QUALITY` | `download-url` | `best` | `best`, `1080`, `720`, `480`, `360` (ignored when audio-only) |
| `SKIP_EXISTING` | `download-url`, `download-list` | `true` | Skip files that already exist |
| `RENAME_AFTER_DOWNLOAD` | `download-url`, `download-list` | on for audio-only / MP3 | Clean MP3 names after download |
| `URL_LIST_FILE` | `download-list` | `urls.txt` | Text file of URLs |
| `AUDIO_FORMAT` | `download-list` | `mp3` | `mp3`, `m4a`, `wav`, `opus`, `vorbis` |
| `COOKIES_FROM_BROWSER` | both download commands | unset | Browser name, e.g. `chrome`, `firefox`, `brave` |
| `COOKIES_FILE` | both download commands | unset | Path to a Netscape `cookies.txt` |

Booleans accept `true`, `1`, `yes`, or `on` (any case).

Example `.env` for audio-only downloads:

```env
PLAYLIST_URL=https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
SAVE_PATH=/home/lumen/Files/files/gmet
AUDIO_ONLY=true
VIDEO_QUALITY=best
SKIP_EXISTING=true
RENAME_AFTER_DOWNLOAD=true
```

Then:

```bash
./youtube_playlist_downloader/run.sh download-url
```

## Commands

### `download-url` — one video or playlist

```bash
./youtube_playlist_downloader/run.sh download-url [options]
```

| Option | `.env` fallback | Description |
|--------|-----------------|-------------|
| `--url URL` | `PLAYLIST_URL` | YouTube video or playlist URL |
| `--output DIR` | `SAVE_PATH` | Folder to save files (created if missing) |
| `--audio-only` / `--no-audio-only` | `AUDIO_ONLY` | MP3 only, or keep video |
| `--quality {best,1080,720,480,360}` | `VIDEO_QUALITY` | Video height cap when not audio-only |
| `--no-skip-existing` | `SKIP_EXISTING` | Re-download even if the file exists |
| `--rename` / `--no-rename` | `RENAME_AFTER_DOWNLOAD` | Clean MP3 names after download (default: on for `--audio-only`) |
| `--cookies-from-browser BROWSER` | `COOKIES_FROM_BROWSER` | Use cookies from Chrome, Firefox, Brave, etc. |
| `--cookies FILE` | `COOKIES_FILE` | Netscape `cookies.txt` path |

Audio-only MP3 is encoded at **192 kbps** from the best YouTube audio stream. That is clear for stories, lectures, and spoken word.

Playlist files are numbered: `01 - Title.mp3`, `02 - Title.mp3`, … Single videos use the title only.

**Playlist as MP3** (flags):

```bash
./youtube_playlist_downloader/run.sh download-url \
  --url "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
  --output "/home/lumen/Files/files/gmet" \
  --audio-only
```

**Same job from `.env`:**

```bash
./youtube_playlist_downloader/run.sh download-url
```

**Single video as MP3:**

```bash
./youtube_playlist_downloader/run.sh download-url \
  --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --output "downloads/songs" \
  --audio-only
```

**Playlist as 720p video:**

```bash
./youtube_playlist_downloader/run.sh download-url \
  --url "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
  --output "downloads/videos" \
  --no-audio-only \
  --quality 720
```

**Best video quality, keep original names:**

```bash
./youtube_playlist_downloader/run.sh download-url \
  --url "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
  --output "downloads/videos" \
  --no-audio-only \
  --quality best \
  --no-rename
```

**Force re-download:**

```bash
./youtube_playlist_downloader/run.sh download-url --no-skip-existing
```

**Pass cookies if YouTube blocks the download:**

```bash
./youtube_playlist_downloader/run.sh download-url --cookies-from-browser chrome
./youtube_playlist_downloader/run.sh download-url --cookies /path/to/cookies.txt
```

Interrupted runs can be started again with the same command. Existing files are skipped unless `--no-skip-existing` is set.

---

### `download-list` — URLs from a text file

Audio only. Default format is MP3 (320 kbps).

```bash
./youtube_playlist_downloader/run.sh download-list [options]
```

| Option | `.env` fallback | Description |
|--------|-----------------|-------------|
| `--file FILE` | `URL_LIST_FILE` | One URL per line (default: `urls.txt`) |
| `--output DIR` | `SAVE_PATH` | Folder to save files |
| `--format {mp3,m4a,wav,opus,vorbis}` | `AUDIO_FORMAT` | Output audio format |
| `--no-skip-existing` | `SKIP_EXISTING` | Re-download even if the file exists |
| `--rename` / `--no-rename` | `RENAME_AFTER_DOWNLOAD` | Clean MP3 names after download (default: on for MP3) |
| `--cookies-from-browser BROWSER` | `COOKIES_FROM_BROWSER` | Browser cookies |
| `--cookies FILE` | `COOKIES_FILE` | Netscape `cookies.txt` |

`urls.txt` format (blank lines and `#` comments are ignored):

```
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2

# ignored
https://www.youtube.com/watch?v=VIDEO_ID_3
```

**MP3 from a list:**

```bash
./youtube_playlist_downloader/run.sh download-list \
  --file youtube_playlist_downloader/urls.txt \
  --output "downloads/songs" \
  --format mp3
```

**M4A, no rename:**

```bash
./youtube_playlist_downloader/run.sh download-list \
  --file urls.txt \
  --output "downloads/songs" \
  --format m4a \
  --no-rename
```

There is also a convenience wrapper that defaults to `download-list`:

```bash
./song_downloader_from_urls/run.sh --file song_downloader_from_urls/urls.txt --output downloads/songs
```

---

### `rename` — clean MP3 filenames

Strips extra text such as “Official Video”, artist suffixes, and similar labels. Default is a **dry run** (prints what would change).

```bash
./youtube_playlist_downloader/run.sh rename --dir DIR [--apply]
./youtube_playlist_downloader/run.sh rename DIR [--apply]
```

| Option | Description |
|--------|-------------|
| `--dir DIR` or positional `DIR` | Folder of MP3 files |
| `--apply` | Actually rename (without this, only preview) |

**Preview:**

```bash
./youtube_playlist_downloader/run.sh rename --dir "/home/lumen/Files/files/gmet"
```

**Apply:**

```bash
./youtube_playlist_downloader/run.sh rename --dir "/home/lumen/Files/files/gmet" --apply
```

You can also run the standalone script:

```bash
uv run python rename_songs.py --dir "/home/lumen/Files/files/gmet" --apply
```

## Typical workflow

```bash
git clone https://github.com/abusaidshabib/automation.git
cd automation
uv sync
chmod +x youtube_playlist_downloader/run.sh

cp youtube_playlist_downloader/.env.example youtube_playlist_downloader/.env
# Edit PLAYLIST_URL, SAVE_PATH, set AUDIO_ONLY=true

./youtube_playlist_downloader/run.sh download-url

# Optional extra cleanup
./youtube_playlist_downloader/run.sh rename --dir "/path/to/output" --apply
```

## Troubleshooting

### `ffmpeg not found`

```bash
uv sync
```

Or install system ffmpeg (see Install).

### `No supported JavaScript runtime`

Install Deno and ensure `~/.deno/bin` is on PATH, or install Node.js 20+.

### YouTube bot check / “Sign in to confirm”

Pass cookies from a logged-in browser:

```bash
./youtube_playlist_downloader/run.sh download-url --cookies-from-browser chrome
```

On Linux, browser cookie extraction needs `secretstorage` (already in `uv sync`). If it is missing: `uv sync` from the repo root.

### Leftover `.webm` or `.part` files

A run failed before MP3 conversion, or was interrupted. Partial `.part` files are removed automatically. Delete leftover `.webm` files and re-run (existing MP3s are skipped):

```bash
rm /path/to/output/*.webm
./youtube_playlist_downloader/run.sh download-url
```

### Broken virtual environment

From the repository root:

```bash
rm -rf .venv
uv sync
```

### Permission denied on `run.sh`

```bash
chmod +x youtube_playlist_downloader/run.sh
```

### `uv: command not found`

Install uv, then open a new terminal.

### No URL provided

Set `PLAYLIST_URL` in `.env` or pass `--url`.

### URL list file not found

Pass `--file` with a real path, or set `URL_LIST_FILE` in `.env`. The default is `urls.txt` in the current directory.

## Dependencies

- **yt-dlp** — download from YouTube and 1000+ sites
- **python-dotenv** — load settings from `.env`
- **rich** — progress bars and formatted output
- **imageio-ffmpeg** — bundled ffmpeg for MP3 conversion
- **secretstorage** — Linux browser-cookie support
