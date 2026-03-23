from src.transcribe import transcribe_bass
from src.postprocess import postprocess_midi
from src.fretting import find_optimal_fretting

if __name__ == "__main__":
    bass_wav  = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\htdemucs\PinkPantheress_-_Stateside__Zara_Larsson_(Official_Audio)\bass.wav"
    midi_path = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\bass.mid"

    # ── pipeline ─────────────────────────────────────────────
    midi  = transcribe_bass(bass_wav, midi_path)
    midi  = postprocess_midi(midi)

    notes   = midi.instruments[0].notes
    pitches = [note.pitch for note in notes]

    # ✅ now supports tuning param (optional)
    fretting = find_optimal_fretting(pitches, tuning="standard")

    # ── debug print ──────────────────────────────────────────
    string_names = ["E", "A", "D", "G"]

    print("\nFirst 20 notes:\n")

    for i, (note, position) in enumerate(zip(notes[:20], fretting[:20])):
        s, f = position
        print(
            f"{i+1:3} | MIDI {note.pitch:3} | "
            f"{string_names[s]} string | fret {f:2} | "
            f"t={note.start:.2f}s"
        )

    # ── quick sanity stats (NEW) ─────────────────────────────
    jumps = 0
    for i in range(1, len(fretting)):
        _, f1 = fretting[i - 1]
        _, f2 = fretting[i]
        if abs(f2 - f1) > 5:
            jumps += 1

    print(f"\nLarge jumps (>5 frets): {jumps}")