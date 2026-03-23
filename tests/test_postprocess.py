from src.transcribe import transcribe_bass
from src.postprocess import postprocess_midi

if __name__ == "__main__":
    bass_wav   = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\htdemucs\PinkPantheress_-_Stateside__Zara_Larsson_(Official_Audio)\bass.wav"
    midi_path  = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\bass.mid"

    # ── transcribe ───────────────────────────────────────────
    midi = transcribe_bass(bass_wav, midi_path)
    raw_notes = midi.instruments[0].notes

    print(f"Before: {len(raw_notes)} notes")

    # ── postprocess ──────────────────────────────────────────
    midi = postprocess_midi(midi)
    notes = midi.instruments[0].notes

    print(f"After:  {len(notes)} notes")

    # ── debug preview (NEW) ──────────────────────────────────
    print("\nFirst 15 notes:\n")
    for i, n in enumerate(notes[:15]):
        duration = n.end - n.start
        print(f"{i+1:3} | pitch={n.pitch:3} | t={n.start:.2f}s | dur={duration:.2f}s")

    # ── sanity checks (NEW) ──────────────────────────────────
    overlaps = 0
    for i in range(len(notes) - 1):
        if notes[i].end > notes[i + 1].start:
            overlaps += 1

    print(f"\nOverlapping notes: {overlaps}")

    short_notes = sum(1 for n in notes if (n.end - n.start) < 0.05)
    print(f"Very short notes (<50ms): {short_notes}")