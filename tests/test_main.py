from pathlib import Path

from src.separate import separate_bass, normalize_wav
from src.transcribe import transcribe_bass
from src.postprocess import postprocess_notes
from src.fretting import filter_notes_to_fretting
from src.rs_xml import notes_to_rs, generate_arrangement_xml

# OPTIONAL (only if you want packaging step)
# from src.package import package_psarc

# Note name helper — no pretty_midi needed
_NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def _note_name(pitch): return f"{_NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


if __name__ == "__main__":
    # ── INPUT ──────────────────────────────────────────────────────────────
    input_audio = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\don't wanna break up again.mp3"

    output_dir = Path(r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output")
    output_dir.mkdir(exist_ok=True)

    midi_path = output_dir / "bass.mid"
    xml_path  = output_dir / "arrangement.xml"

    song_name  = "Don't Wanna Break Up Again"
    artist     = "Ariana Grande"
    album_name = "eternal sunshine"
    album_year = 2024
    avg_tempo  = 97.0   # BPM — confirmed from tab
    tuning     = "standard"

    print("\n========== START PIPELINE ==========\n")

    # ── 1. SEPARATION ──────────────────────────────────────────────────────
    print("1. Separating bass...")
    bass_wav, preview_wav = separate_bass(input_audio, str(output_dir))
    print(f"   Bass stem:    {bass_wav}")
    print(f"   Preview:      {preview_wav}")

    # ── 1b. FULL MIX FOR TOOLKIT ───────────────────────────────────────────
    # Toolkit needs the full song for in-game audio — not the isolated bass stem.
    print("\n1b. Normalizing full mix for toolkit...")
    full_mix_wav = normalize_wav(input_audio, str(output_dir), filename="full_mix.wav")
    print(f"   Full mix WAV: {full_mix_wav}")

    # ── 2. TRANSCRIPTION ───────────────────────────────────────────────────
    print("\n2. Transcribing with aubio...")
    # Returns list of (start_sec, end_sec, midi_pitch) tuples
    raw_notes = transcribe_bass(bass_wav, str(midi_path), full_mix_wav)
    print(f"   Raw notes detected: {len(raw_notes)}")

    # ── 3. POSTPROCESS ─────────────────────────────────────────────────────
    print("\n3. Postprocessing...")
    notes = postprocess_notes(raw_notes)
    print(f"   Notes after cleanup: {len(notes)}")

    if not notes:
        raise RuntimeError("No notes survived postprocessing — check bass stem quality.")

    # ── 4. FRETTING ────────────────────────────────────────────────────────
    print("\n4. Computing fretting...")
    pitches = [p for (s, e, p) in notes]

    # filter_notes_to_fretting guarantees notes and fretting are same length
    playable_notes, fretting = filter_notes_to_fretting(notes, pitches, tuning=tuning)
    print(f"   Playable notes: {len(playable_notes)}")

    # Debug preview
    print("\n   First 10 fretted notes:")
    STRING_NAMES = ["E", "A", "D", "G"]
    for i, ((start, end, pitch), (s, f)) in enumerate(zip(playable_notes[:10], fretting[:10])):
        print(f"   {i+1:2} | t={start:.2f}s  {_note_name(pitch):4s} (MIDI {pitch:2d}) → {STRING_NAMES[s]} str fret {f}")

    # ── 5. RS NOTE CONVERSION ──────────────────────────────────────────────
    print("\n5. Converting to RS format...")
    rs_notes = notes_to_rs(playable_notes, fretting)
    print(f"   RS notes: {len(rs_notes)}")

    # ── 6. XML GENERATION ──────────────────────────────────────────────────
    print("\n6. Generating XML...")
    song_length = max(e for (s, e, p) in playable_notes) + 1.0

    generate_arrangement_xml(
        rs_notes    = rs_notes,
        song_length = song_length,
        avg_tempo   = avg_tempo,
        song_name   = song_name,
        artist      = artist,
        output_path = str(xml_path),
        album_name  = album_name,
        album_year  = album_year,
    )
    print(f"   XML written: {xml_path}")

    # ── SUMMARY ────────────────────────────────────────────────────────────
    print(f"""
========== DONE ==========

  Bass stem:    {bass_wav}
  Full mix WAV: {full_mix_wav}
  MIDI:         {midi_path}
  XML:          {xml_path}

Next steps:
  1. Open RocksmithToolkitGUI.exe AS ADMINISTRATOR
  2. Arrangement XML → {xml_path}
  3. Audio file      → {full_mix_wav}
  4. Generate package
""")

    # ── OPTIONAL: PACKAGE ──────────────────────────────────────────────────
    """
    print("\\n7. Packaging...")
    psarc = package_psarc(
        arrangement_xml_path = str(xml_path),
        audio_wav_path       = full_mix_wav,
        song_name            = song_name,
        artist               = artist,
        output_dir           = str(output_dir),
        toolkit_path         = r"C:\\Users\\Celina Alzenor\\Desktop\\RocksmithToolkit"
    )
    print(f"   PSARC: {psarc}")
    """