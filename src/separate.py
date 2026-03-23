# separate.py

from src.utils.path_utils import normalize_path

import subprocess
import librosa
import shutil
from pathlib import Path
import sys

def _get_audio_dir(base_output_dir: str) -> Path:
    audio_dir = Path(base_output_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir

def normalize_wav(input_path: str, output_dir: str) -> str:
    """
    Convert Demucs output into Wwise / Rocksmith-safe WAV:
    - PCM 16-bit
    - 44.1 kHz
    - stereo
    - simple output path
    """
    audio_dir = _get_audio_dir(output_dir)
    output_path = audio_dir / "audio.wav"

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "-f", "wav",
        str(output_path)
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("ffmpeg failed while normalizing bass stem")

    return str(output_path)


def make_preview(input_path: str,  output_dir: str) -> str:
    """
    Create a Wwise / Rocksmith-safe preview WAV.
    """
    audio_dir = _get_audio_dir(output_dir)
    preview_path = audio_dir / "audio_preview.wav"

    # get duration
    duration = librosa.get_duration(filename=input_path)

    # choose safe start time
    start = min(30, max(0, duration - 30.0))

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", str(start),
        "-t", "30",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "-f", "wav",
        str(preview_path)
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("ffmpeg failed while generating preview audio")

    return str(preview_path)


def separate_bass(input_path: str, output_dir: str) -> tuple[str, str]:
    """
    Runs Demucs on the input audio file and returns the path to the
    normalized isolated bass stem WAV file.
    """
    print("    Running Demucs — this takes 2-4 minutes on CPU...")

    sanitized_path = Path(input_path)
    sanitized_name = sanitized_path.stem

    print(f"Python being used: {sys.executable}")

    subprocess.run([
        sys.executable, "-m", "demucs",
        "--two-stems", "bass",
        "-n", "htdemucs",
        "-o", output_dir,
        str(sanitized_path)
    ], check=True)

    bass_wav_path = Path(output_dir) / "htdemucs" / sanitized_name / "bass.wav"

    if not bass_wav_path.exists():
        raise FileNotFoundError(
            f"Demucs did not produce a bass stem at {bass_wav_path}. "
            "Check that the input file is valid."
        )

    _validate_bass_stem(str(bass_wav_path))

    fixed_bass_wav = normalize_wav(str(bass_wav_path), output_dir)
    _validate_bass_stem(fixed_bass_wav)

    preview_wav = make_preview(fixed_bass_wav, output_dir)

    return fixed_bass_wav, preview_wav


def _validate_bass_stem(bass_wav_path: str):
    """
    Checks that the bass stem has actual audio content.
    """
    audio_samples, _ = librosa.load(bass_wav_path, sr=None, mono=True)
    rms_energy = librosa.feature.rms(y=audio_samples).mean()

    if rms_energy < 0.01:
        raise ValueError(
            f"Bass stem is nearly silent (RMS energy = {rms_energy:.4f}). "
            "This song may have no bass track, or the bass is too quiet to separate."
        )