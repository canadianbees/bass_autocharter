from src.separate import separate_bass
from pathlib import Path


if __name__ == '__main__':

    input_mp3  = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\PinkPantheress - Stateside  Zara Larsson (Official Audio).mp3"
    output_dir = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output"

    print("Running source separation...\n")

    bass_wav = separate_bass(input_mp3, output_dir)

    # ── validation (NEW) ─────────────────────────────────────
    if not bass_wav or not Path(bass_wav).exists():
        raise FileNotFoundError("Bass stem was not generated correctly")

    print(f"\nBass stem: {bass_wav}")

    # ── debug info (NEW) ─────────────────────────────────────
    file_size = Path(bass_wav).stat().st_size / (1024 * 1024)
    print(f"File size: {file_size:.2f} MB")

    if file_size < 1:
        print("⚠️ Warning: bass stem seems very small — separation may have failed")