# separate.py

import subprocess
import librosa
from pathlib import Path
import sys


def _get_audio_dir(base_output_dir: str) -> Path:
    audio_dir = Path(base_output_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def normalize_wav(input_path: str, output_dir: str, filename: str = "audio.wav") -> str:
    """
    Convert audio into Wwise / Rocksmith-safe WAV:
      - PCM 16-bit, 44.1kHz, stereo

    filename param lets you produce full_mix.wav vs audio.wav without conflict.
    """
    audio_dir   = _get_audio_dir(output_dir)
    output_path = audio_dir / filename

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
        raise RuntimeError(f"ffmpeg failed normalizing {input_path}")

    return str(output_path)


def make_preview(input_path: str, output_dir: str) -> str:
    """
    Create a Wwise / Rocksmith-safe 30-second preview WAV.
    Starts at 30s in (or earlier for short songs).
    """
    audio_dir    = _get_audio_dir(output_dir)
    preview_path = audio_dir / "audio_preview.wav"

    # Fixed: librosa 0.10+ requires path= not filename=
    duration = librosa.get_duration(path=input_path)
    start    = min(30, max(0, duration - 30.0))

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
        raise RuntimeError("ffmpeg failed generating preview audio")

    return str(preview_path)


def separate_bass(input_path: str, output_dir: str) -> tuple[str, str]:
    """
    Runs Demucs on the input audio and returns:
      (normalized_bass_wav, preview_wav)
    """
    print("    Running Demucs — this takes 2-4 minutes on CPU...")
    print(f"    Python: {sys.executable}")

    sanitized_path = Path(input_path)
    sanitized_name = sanitized_path.stem

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

    fixed_bass_wav = normalize_wav(str(bass_wav_path), output_dir, filename="audio.wav")
    _validate_bass_stem(fixed_bass_wav)

    preview_wav = make_preview(fixed_bass_wav, output_dir)

    return fixed_bass_wav, preview_wav


def _validate_bass_stem(bass_wav_path: str):
    """Raise ValueError if the bass stem is nearly silent."""
    audio_samples, _ = librosa.load(bass_wav_path, sr=None, mono=True)
    rms_energy = librosa.feature.rms(y=audio_samples).mean()
    if rms_energy < 0.01:
        raise ValueError(
            f"Bass stem is nearly silent (RMS={rms_energy:.4f}). "
            "Song may have no detectable bass track."
        )