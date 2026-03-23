# download.py
# Downloads audio from a URL (YouTube, SoundCloud, etc.) and converts it to MP3.
# If the input looks like a local file path rather than a URL, this stage is skipped.

import os
import yt_dlp
from pathlib import Path


def is_url(input_string: str) -> bool:
    """
    Returns True if the input looks like a URL rather than a local file path.
    Checks for common URL prefixes.
    """
    return input_string.startswith(("http://", "https://", "www."))


def download_audio(url: str, output_dir: str) -> tuple[str, str]:
    """
    Downloads audio from a URL and converts it to a 320kbps MP3.

    Returns a tuple of:
      - mp3_path: the full path to the downloaded MP3 file
      - song_title: the title detected from the video/track metadata

    Raises FileNotFoundError if yt-dlp did not produce an MP3 file.
    """
    download_options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "cookiesfrombrowser": ("edge",),  # or "firefox" if you use Firefox
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }],
    }

    with yt_dlp.YoutubeDL(download_options) as downloader:
        video_info = downloader.extract_info(url, download=True)
        song_title = video_info.get("title", "unknown_title")

    # yt-dlp renames the file after FFmpeg conversion — find the resulting MP3
    mp3_files = list(Path(output_dir).glob("*.mp3"))

    if not mp3_files:
        raise FileNotFoundError(
            f"yt-dlp did not produce an MP3 file in {output_dir}. "
            "Make sure FFmpeg is installed and accessible from your PATH."
        )

    mp3_path = str(mp3_files[0])
    return mp3_path, song_title