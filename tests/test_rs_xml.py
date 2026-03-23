from src.transcribe import transcribe_bass
from src.postprocess import postprocess_midi
from src.fretting import find_optimal_fretting
from src.rs_xml import midi_to_rs_notes, generate_arrangement_xml

if __name__ == "__main__":
    bass_wav   = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\htdemucs\PinkPantheress_-_Stateside__Zara_Larsson_(Official_Audio)\bass.wav"
    midi_path  = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\bass.mid"
    xml_path   = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\arrangement.xml"

    # ── pipeline ─────────────────────────────────────────────
    midi = transcribe_bass(bass_wav, midi_path)
    midi = postprocess_midi(midi)

    notes   = midi.instruments[0].notes
    pitches = [n.pitch for n in notes]

    fretting = find_optimal_fretting(pitches, tuning="standard")
    rs_notes = midi_to_rs_notes(midi, fretting)

    # ── debug preview ────────────────────────────────────────
    print("\nFirst 15 RS notes:\n")
    for i, n in enumerate(rs_notes[:15]):
        print(
            f"{i+1:3} | t={n.time:.2f}s | string={n.string} | fret={n.fret} | sustain={n.sustain:.2f}"
        )

    # ── generate XML ─────────────────────────────────────────
    generate_arrangement_xml(
        rs_notes,
        midi,
        song_name="Stateside",
        artist="PinkPantheress",
        output_path=xml_path,
    )

    print(f"\nXML written to: {xml_path}")

    # ── quick validation (NEW) ───────────────────────────────
    import xml.etree.ElementTree as ET

    tree = ET.parse(xml_path)
    root = tree.getroot()

    levels = root.find("levels")
    phrases = root.find("phrases")

    print("\nValidation:")
    print(f"Levels: {len(levels)}")
    print(f"Phrases: {phrases.get('count')}")