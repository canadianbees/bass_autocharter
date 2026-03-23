from pathlib import Path

from src.separate import separate_bass
from src.transcribe import transcribe_bass
from src.postprocess import postprocess_midi
from src.fretting import find_optimal_fretting
from src.rs_xml import midi_to_rs_notes, generate_arrangement_xml

# OPTIONAL (only if you want packaging step)
# from src.package import package_psarc


if __name__ == "__main__":
    # ── INPUT ─────────────────────────────────────────────
    input_audio = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\PinkPantheress - Stateside  Zara Larsson (Official Audio).mp3"

    output_dir = Path(r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output")
    output_dir.mkdir(exist_ok=True)

    midi_path = output_dir / "bass.mid"
    xml_path  = output_dir / "arrangement.xml"

    song_name = "Stateside"
    artist    = "PinkPantheress"

    print("\n========== START PIPELINE ==========\n")

    # ── 1. SEPARATION ─────────────────────────────────────
    print("1. Separating bass...")
    bass_wav, preview_wav   = separate_bass(input_audio, str(output_dir))
    print(f"   Bass stem: {bass_wav}")
    print(f"   Preview stem: {preview_wav}")


    # ── 2. TRANSCRIPTION ──────────────────────────────────
    print("\n2. Transcribing...")
    midi = transcribe_bass(bass_wav, str(midi_path))
    print(f"   MIDI written: {midi_path}")

    # ── 3. POSTPROCESS ────────────────────────────────────
    print("\n3. Postprocessing...")
    midi = postprocess_midi(midi)
    notes = midi.instruments[0].notes
    print(f"   Notes after cleanup: {len(notes)}")

    # ── 4. FRETTING ───────────────────────────────────────
    print("\n4. Computing fretting...")
    pitches = [n.pitch for n in notes]
    fretting = find_optimal_fretting(pitches, tuning="standard")

    # Debug preview
    print("\n   First 10 fretted notes:")
    string_names = ["E", "A", "D", "G"]
    for i, (n, (s, f)) in enumerate(zip(notes[:10], fretting[:10])):
        print(f"   {i+1:2} | pitch={n.pitch} → {string_names[s]} fret {f}")

    # ── 5. RS NOTE CONVERSION ─────────────────────────────
    print("\n5. Converting to RS format...")
    rs_notes = midi_to_rs_notes(midi, fretting)

    # ── 6. XML GENERATION ─────────────────────────────────
    print("\n6. Generating XML...")
    generate_arrangement_xml(
        rs_notes,
        midi,
        song_name=song_name,
        artist=artist,
        output_path=str(xml_path),
    )
    print(f"   XML written: {xml_path}")

    # ── 7. OPTIONAL: PACKAGE ──────────────────────────────
    """
    print("\n7. Packaging...")
    psarc = package_psarc(
        arrangement_xml_path=str(xml_path),
        audio_wav_path=bass_wav,
        song_name=song_name,
        artist=artist,
        output_dir=str(output_dir),
        toolkit_path=r"C:\Path\To\RocksmithToolkitCLI.exe"
    )
    print(f"   PSARC: {psarc}")
    """

    print("\n========== DONE ==========\n")