from src.transcribe import transcribe_bass
from pathlib import Path


if __name__ == "__main__":
    bass_wav   = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\htdemucs\PinkPantheress_-_Stateside__Zara_Larsson_(Official_Audio)\bass.wav"
    midi_path  = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\bass.mid"

    print("Running transcription...\n")

    midi = transcribe_bass(bass_wav, midi_path)

    # ── validation (NEW) ─────────────────────────────────────
    if not Path(midi_path).exists():
        raise FileNotFoundError("MIDI file was not created")

    notes = midi.instruments[0].notes
    print(f"MIDI written to: {midi_path}")
    print(f"Detected notes: {len(notes)}")

    # ── debug preview (NEW) ──────────────────────────────────
    print("\nFirst 15 notes:\n")
    for i, n in enumerate(notes[:15]):
        dur = n.end - n.start
        print(f"{i+1:3} | pitch={n.pitch:3} | t={n.start:.2f}s | dur={dur:.2f}s")

    # ── sanity checks (NEW) ──────────────────────────────────
    short_notes = sum(1 for n in notes if (n.end - n.start) < 0.05)
    print(f"\nVery short notes (<50ms): {short_notes}")