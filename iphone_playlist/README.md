# iPhone Playlist Audio

Download a full YouTube playlist as **Apple Lossless (ALAC)** so an **iPhone 15 Plus** can play the best audio YouTube actually provides — without encoding to MP3 a second time.

The older [`youtube_playlist_downloader`](../youtube_playlist_downloader/) tool still targets 192 kbps MP3 (stories, small files). This project is for music you want on the phone at maximum fidelity.

## Why ALAC on iPhone 15 Plus

| Format | What it is | On this phone |
|--------|------------|---------------|
| **ALAC** (`.m4a`, default) | Lossless wrap of the decoded YouTube stream | Plays in **Music** and **Files**. No second lossy encode. |
| YouTube Opus | Usually the best stream (~160 kbps, 48 kHz) | Music app does not play Opus. |
| MP3 / AAC from that Opus | Second lossy encode | Smaller files; you throw away detail. |
| FLAC / WAV | Also lossless | FLAC needs Files or a third-party app; WAV is huge. |

“Best on this phone” means: **preserve the YouTube stream in a format the phone plays**. It cannot exceed what YouTube uploaded.

**Bluetooth** on iPhone always recompresses to AAC for the headphones. Prefer **USB-C** (Apple’s headphone adapter or a DAC) when you want to hear what is stored in the file.

**When to use AAC instead:** set `OUTPUT_FORMAT=aac` (256 kbps) if you care more about size or mostly listen over Bluetooth.

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- ffmpeg (system install, or bundled via `imageio-ffmpeg` from `uv sync`)
- Deno (recommended) or Node.js 20+ for YouTube’s JavaScript challenges

From the repository root:

```bash
uv sync
chmod +x iphone_playlist/run.sh
```

## Quick start

1. Put the playlist URL in [`playlist_url.txt`](playlist_url.txt) (already seeded), or set `PLAYLIST_URL` in `.env`, or pass `--url`.

2. Optional defaults:

```bash
cp iphone_playlist/.env.example iphone_playlist/.env
# edit SAVE_PATH, OUTPUT_FORMAT, etc.
```

3. Download:

```bash
./iphone_playlist/run.sh
```

Files land in `iphone_playlist/downloads/<Playlist Name>/` as `001 - Title.m4a`, `002 - Title.m4a`, …

Interrupted? Run the same command again. Finished tracks are skipped via a `.download_archive` in that folder.

## How to run

```bash
./iphone_playlist/run.sh [options]
```

Same thing with uv:

```bash
uv run python iphone_playlist/main.py [options]
```

Help:

```bash
./iphone_playlist/run.sh --help
```

### Useful commands

**Preview the playlist (no download):**

```bash
./iphone_playlist/run.sh --dry-run
```

**See which YouTube audio streams exist (and what `bestaudio` would pick):**

```bash
./iphone_playlist/run.sh --formats
```

**Download one sample track to test format and sound** (saves under `downloads/sample/`):

```bash
./iphone_playlist/run.sh --sample
# or with cookies if YouTube blocks anonymous downloads:
./iphone_playlist/run.sh --sample --cookies-from-browser chrome
# first 3 tracks:
./iphone_playlist/run.sh --sample 3
```

Listen on the phone (or locally). If it sounds right, run without `--sample` for the full playlist.

**Explicit ALAC download:**

```bash
./iphone_playlist/run.sh \
  --url "https://www.youtube.com/playlist?list=PLxxxxxxxx" \
  --output "/path/to/music" \
  --format alac
```

**Smaller AAC for Bluetooth-heavy listening:**

```bash
./iphone_playlist/run.sh --format aac
```

**Cookies if YouTube blocks anonymous downloads:**

```bash
./iphone_playlist/run.sh --cookies-from-browser chrome
./iphone_playlist/run.sh --cookies /path/to/cookies.txt
```

## Configuration

Priority: **CLI flags → `.env` → built-in defaults**.  
URL order: `--url` → `PLAYLIST_URL` → `playlist_url.txt`.

| Option | Env | Default | Meaning |
|--------|-----|---------|---------|
| `--url` | `PLAYLIST_URL` | first line of `playlist_url.txt` | Playlist or video URL |
| `--output` | `SAVE_PATH` | `iphone_playlist/downloads` | Parent folder (playlist-named subfolder is created) |
| `--format` | `OUTPUT_FORMAT` | `alac` | `alac`, `aac`, `flac`, `wav` |
| `--source` | `SOURCE_FORMAT` | `bestaudio/best` | yt-dlp stream selector |
| `--bit-depth` | `ALAC_BIT_DEPTH` | `24` | `24` or `16` (ALAC only); sample rate follows the source |
| `--no-skip-existing` | `SKIP_EXISTING=false` | skip on | Re-download everything |
| `--no-art` | `EMBED_ART=false` | embed on | Skip cover art |
| `--no-metadata` | `EMBED_METADATA=false` | embed on | Skip tags |
| `--no-clean-titles` | `CLEAN_TITLES=false` | clean on | Keep raw YouTube titles |
| `--cookies-from-browser` | `COOKIES_FROM_BROWSER` | unset | Browser cookies |
| `--cookies` | `COOKIES_FILE` | unset | Netscape `cookies.txt` |
| `--formats` | — | — | List streams and exit |
| `--dry-run` | — | — | List tracks and exit |
| `--sample [N]` | — | off | Download first track (or first N) into `downloads/sample/` for a quality check |

Booleans in `.env` accept `true`, `1`, `yes`, or `on`.

### What gets written into each file

- **Filename:** `001 - Cleaned Title.m4a` (playlist order)
- **Tags:** title, artist (when the title looks like `Artist - Song`), album = playlist name, track number
- **Cover:** video thumbnail (ALAC / AAC / FLAC)

Title cleanup lives in `parse_title()` at the top of [`main.py`](main.py). Edit that function to change how names are cleaned.

## Copy files to an iPhone 15 Plus

### Fast: Files app (USB-C or AirDrop)

1. Connect the phone with USB-C, or AirDrop the `.m4a` folder from a Mac.
2. Save into **On My iPhone → Files** (or iCloud Drive).
3. Open a track in **Files** or share it to **Music** / your player.

Playback works immediately. Tracks in Files are easy to browse as a folder.

### Music library (Mac)

1. Copy the folder to a Mac.
2. Open **Music** → File → Import (or drag the folder in).
3. Sync the library to the iPhone (Finder sync or iCloud Music Library, depending on how you manage the library).

ALAC stays lossless in the Music app. That is the path when you want these songs mixed with the rest of your library.

### Wired vs Bluetooth

- **USB-C headphones or DAC:** you hear the ALAC file as stored.
- **AirPods / Bluetooth:** the phone encodes AAC for the link. ALAC still avoids a second encode *into the file*; the wireless hop is separate.

## Typical workflow

```bash
cd automation
uv sync
chmod +x iphone_playlist/run.sh

# optional: copy and edit defaults
cp iphone_playlist/.env.example iphone_playlist/.env

./iphone_playlist/run.sh --dry-run
./iphone_playlist/run.sh --formats
./iphone_playlist/run.sh

# copy iphone_playlist/downloads/<Playlist>/ to the phone
```

## Troubleshooting

### `ffmpeg not found`

```bash
uv sync
# or: sudo apt install ffmpeg
```

### `No supported JavaScript runtime`

```bash
curl -fsSL https://deno.land/install.sh | sh
# ensure ~/.deno/bin is on PATH
```

### Bot check / “Sign in to confirm”

YouTube blocks anonymous downloads. **`--cookies-from-browser chrome` only works if that Chrome profile is logged into YouTube.** If Chrome has no YouTube login cookies, the tool now exits early and tells you.

**Recommended: export a cookies file**

1. Open [youtube.com](https://www.youtube.com) and log in (confirm your avatar is visible).
2. Install a cookies export extension such as **Get cookies.txt LOCALLY**.
3. Export while on youtube.com.
4. Run:

```bash
./iphone_playlist/run.sh --sample --cookies ~/Downloads/www.youtube.com_cookies.txt
```

Or set in `.env`:

```env
COOKIES_FILE=/home/lumen/Downloads/www.youtube.com_cookies.txt
```

**Browser cookies (after logging into YouTube in that browser):**

```bash
# Close the browser first on Linux, then:
./iphone_playlist/run.sh --sample --cookies-from-browser chrome
./iphone_playlist/run.sh --sample --cookies-from-browser brave
```

### Leftover `.webm` / `.part` / `.webp`

A run failed before conversion, or was interrupted. Re-run the same command; completed tracks stay skipped. You can delete stray intermediates:

```bash
rm -f iphone_playlist/downloads/*/*.{part,webp,webm}
./iphone_playlist/run.sh
```

### Permission denied on `run.sh`

```bash
chmod +x iphone_playlist/run.sh
```

## Dependencies

Same stack as the rest of this repo (`pyproject.toml` / `uv sync`):

- **yt-dlp** — fetch the best YouTube audio
- **python-dotenv** — `.env` defaults
- **rich** — progress UI
- **imageio-ffmpeg** — bundled ffmpeg fallback
- **secretstorage** — Linux browser-cookie support
