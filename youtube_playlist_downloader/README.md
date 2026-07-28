# YouTube Playlist Downloader

Download a full YouTube playlist (or a single video) as MP3 or video, with progress tracking and optional filename cleanup.

## Features

- Download an entire playlist or one video from a URL
- Audio-only mode (MP3) or video with quality options
- Skip files that already exist
- Download from a text file of URLs
- Clean up messy MP3 filenames after download
- Uses bundled ffmpeg when system ffmpeg is not installed

## Quick start

```bash
git clone git@github.com:abusaidshabib/automation.git
cd automation/youtube_playlist_downloader
python3 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
chmod +x run.sh

./run.sh download-url \
  --url "https://www.youtube.com/playlist?list=YOUR_PLAYLIST_ID" \
  --output "../downloads/songs" \
  --audio-only
```

## Setup (step by step)

### 1. Clone the repository

```bash
git clone git@github.com:abusaidshabib/automation.git
cd automation/youtube_playlist_downloader
```

HTTPS clone:

```bash
git clone https://github.com/abusaidshabib/automation.git
cd automation/youtube_playlist_downloader
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
```

- **Linux / macOS:**
  ```bash
  source .venv/bin/activate
  ```
- **Windows:**
  ```bash
  .\.venv\Scripts\activate
  ```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Make the run script executable (Linux / macOS)

```bash
chmod +x run.sh
```

### 5. FFmpeg

Audio downloads need ffmpeg to convert to MP3. You have two options:

**Option A — bundled (recommended, no sudo):**  
Already included via `imageio-ffmpeg` in `requirements.txt`. The tool uses it automatically if system ffmpeg is missing.

**Option B — system install:**

- **Linux (Ubuntu/Debian):**
  ```bash
  sudo apt-get install ffmpeg
  ```
- **macOS:**
  ```bash
  brew install ffmpeg
  ```
- **Windows:**
  ```bash
  winget install FFmpeg
  ```

### 6. Optional: configure defaults with `.env`

```bash
cp .env.example .env
```

Edit `.env`:

```env
PLAYLIST_URL=https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
SAVE_PATH=../downloads/songs
AUDIO_ONLY=true
VIDEO_QUALITY=best
SKIP_EXISTING=true
```

When `.env` is set, you can run `./run.sh download-url` without passing `--url` or `--output`.

## Usage

Run commands from the `youtube_playlist_downloader` folder.

### Using the shell script

```bash
./run.sh <command> [options]
```

If you run `./run.sh` with no arguments, it defaults to `download-url` (using `.env` values if present).

### Using Python directly

```bash
python main.py <command> [options]
```

## Commands

### `download-url` — download one video or playlist

| Option | Description |
|--------|-------------|
| `--url` | YouTube video or playlist URL |
| `--output` | Folder to save files |
| `--audio-only` / `--no-audio-only` | Download MP3 only (default: from `.env` or video) |
| `--quality` | Video quality: `best`, `1080`, `720`, `480`, `360` |
| `--no-skip-existing` | Re-download even if file already exists |

**Example — full playlist as MP3:**

```bash
./run.sh download-url \
  --url "https://youtube.com/playlist?list=PL1huvitKeyYbl-SqHT8eTRqw4ZDxIqwtH&si=G8bB2xcsaFpNEuUS" \
  --output "/home/lumen/Projects/automation/downloads/songs" \
  --audio-only
```

**Example — single video as MP3:**

```bash
./run.sh download-url \
  --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --output "../downloads/songs" \
  --audio-only
```

**Example — playlist as video (720p):**

```bash
./run.sh download-url \
  --url "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx" \
  --output "../downloads/videos" \
  --no-audio-only \
  --quality 720
```

**Example — using `.env` defaults:**

```bash
./run.sh download-url --audio-only
```

Playlist files are saved with numbered names, e.g. `01 - Song Title.mp3`.

### `download-list` — download from a text file of URLs

| Option | Description |
|--------|-------------|
| `--file` | Text file with one URL per line (default: `urls.txt`) |
| `--output` | Folder to save files |
| `--format` | Audio format: `mp3`, `m4a`, `wav`, `opus`, `vorbis` |
| `--no-skip-existing` | Re-download even if file already exists |

**Example:**

```bash
./run.sh download-list \
  --file urls.txt \
  --output "../downloads/songs" \
  --format mp3
```

`urls.txt` format:

```
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2

# Lines starting with # are ignored
https://www.youtube.com/watch?v=VIDEO_ID_3
```

### `rename` — clean MP3 filenames

Removes extra text from filenames (e.g. "Official Video", artist suffixes).

**Preview changes (dry run):**

```bash
./run.sh rename --dir "../downloads/songs"
```

**Apply renames:**

```bash
./run.sh rename --dir "../downloads/songs" --apply
```

## Full workflow example

From a fresh clone to a downloaded playlist:

```bash
# 1. Clone and enter the project
git clone https://github.com/abusaidshabib/automation.git
cd automation/youtube_playlist_downloader

# 2. Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run.sh

# 3. Create a folder for downloads (optional — the tool creates it too)
mkdir -p ../downloads/songs

# 4. Download the playlist as MP3
./run.sh download-url \
  --url "https://youtube.com/playlist?list=PL1huvitKeyYbl-SqHT8eTRqw4ZDxIqwtH" \
  --output "../downloads/songs" \
  --audio-only

# 5. Optional: clean up filenames
./run.sh rename --dir "../downloads/songs" --apply
```

## Requirements

- Python 3.8+
- Internet connection
- ffmpeg (system install or bundled via `imageio-ffmpeg`)

## Troubleshooting

### `ffmpeg not found`

Reinstall dependencies so the bundled ffmpeg is available:

```bash
pip install -r requirements.txt
```

Or install system ffmpeg (see Setup step 5).

### Leftover `.webm` files after a failed run

If a download failed before MP3 conversion, remove partial files and retry:

```bash
rm ../downloads/songs/*.webm
./run.sh download-url --url "YOUR_URL" --output "../downloads/songs" --audio-only
```

### Broken virtual environment after moving the project

Recreate the venv:

```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Permission denied on `run.sh`

```bash
chmod +x run.sh
```

## Dependencies

- **yt-dlp** — download from YouTube and 1000+ sites
- **python-dotenv** — load settings from `.env`
- **rich** — progress bars and formatted output
- **imageio-ffmpeg** — bundled ffmpeg for MP3 conversion
