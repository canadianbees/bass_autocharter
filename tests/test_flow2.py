# test_flow2.py
# GP file → Rocksmith 2014 arrangement XML
# Direct conversion, no audio processing, no postprocessing.

import sys
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

GP_FILE    = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_input\Ariana Grande-_don't wanna break up again_ (A MAJOR)-05-16-2025.gp"
OUTPUT_DIR = Path(r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output")
SONG_NAME  = "Don't Wanna Break Up Again"
ARTIST     = "Ariana Grande"
ALBUM      = "eternal sunshine"
YEAR       = 2024
BPM        = 97.0
TRACK_IDX  = 2   # 0=Guitar, 1=Guitar2, 2=Bass, 3=Drums

# ── END CONFIG ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from src.gp_input import load_gp_notes
    from src.rs_xml   import notes_to_rs, generate_arrangement_xml

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xml_path = OUTPUT_DIR / 'arrangement.xml'

    print('\n========== FLOW 2: GP → ROCKSMITH ==========\n')

    # 1. Load notes directly from GP file — no postprocessing
    notes, fretting, tuning = load_gp_notes(GP_FILE, track_index=TRACK_IDX)
    print(f'Loaded {len(notes)} notes  ({notes[0][0]:.2f}s — {notes[-1][1]:.2f}s)')

    # 2. Convert to RS format and write XML
    rs_notes = notes_to_rs(notes, fretting)

    song_length = max(e for s, e, p in notes) + 2.0

    generate_arrangement_xml(
        rs_notes    = rs_notes,
        song_length = song_length,
        avg_tempo   = BPM,
        song_name   = SONG_NAME,
        artist      = ARTIST,
        output_path = str(xml_path),
        album_name  = ALBUM,
        album_year  = YEAR,
    )

    print(f'XML written: {xml_path}')