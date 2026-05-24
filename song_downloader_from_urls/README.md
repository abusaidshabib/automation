# 🎵 Song Downloader from URL List

A Python tool to download songs from a list of URLs (YouTube, SoundCloud, etc.) with rich progress tracking.

## Features

- ✨ Download songs from multiple URLs at once
- 🎶 Multiple audio format support (MP3, M4A, WAV, OPUS, VORBIS)
- 📊 Rich progress tracking with download speed and ETA
- 🔄 Skip existing files option
- 🎯 Simple URL list format (one URL per line)
- 📝 Comment support in URL list (#)

## Setup

1. **Clone or create the project directory**
   ```bash
   cd song_downloader_from_urls
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**
   - On Windows:
     ```bash
     .\.venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Install FFmpeg** (required for audio conversion)
   - **Windows (using Chocolatey):**
     ```bash
     choco install ffmpeg
     ```
   - **Windows (using winget):**
     ```bash
     winget install FFmpeg
     ```
   - **macOS:**
     ```bash
     brew install ffmpeg
     ```
   - **Linux (Ubuntu/Debian):**
     ```bash
     sudo apt-get install ffmpeg
     ```

## Configuration

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` to customize settings:**
   ```env
   URL_LIST_FILE=urls.txt          # Path to your URL list
   SAVE_PATH=./downloads            # Where to save songs
   AUDIO_FORMAT=mp3                 # Format: mp3, m4a, wav, opus, vorbis
   SKIP_EXISTING=true               # Skip already downloaded files
   ```

3. **Create your URL list:**
   ```bash
   cp urls.txt.example urls.txt
   ```

4. **Edit `urls.txt` and add your URLs:**
   ```
   https://www.youtube.com/watch?v=dQw4w9WgXcQ
   https://www.youtube.com/watch?v=oHg5SJYRHA0
   
   # Comments are supported with #
   https://www.youtube.com/watch?v=xfr64zoBTAQ
   ```

## Usage

### Using the shell script (macOS/Linux):
```bash
./run.sh
```

### Using Python directly:
```bash
python main.py
```

### With custom environment:
```bash
URL_LIST_FILE=my_songs.txt AUDIO_FORMAT=m4a python main.py
```

## Supported Platforms

- YouTube
- SoundCloud
- Spotify
- Apple Music
- And 1000+ other sites supported by yt-dlp

## Requirements

- Python 3.8+
- FFmpeg (for audio conversion)
- Internet connection

## Troubleshooting

### FFmpeg not found
Make sure FFmpeg is installed and available in your PATH.

### Download fails for specific URLs
Some videos may have restrictions. Check if the URL is publicly accessible and not geo-blocked.

### Permission denied (macOS/Linux)
Make `run.sh` executable:
```bash
chmod +x run.sh
```

## Dependencies

- **yt-dlp**: Download videos and audio from 1000+ sites
- **python-dotenv**: Load environment variables from `.env`
- **rich**: Beautiful terminal output with progress tracking

## License

MIT License - Use as you wish!
