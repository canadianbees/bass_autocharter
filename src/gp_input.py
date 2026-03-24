# gp_input.py
# Parses Guitar Pro 7 (.gp) files — which are zip archives containing score.gpif (XML).
#
# GP7 format structure:
#   file.gp  (zip archive)
#   └── Content/
#       └── score.gpif  (XML — all note, rhythm, and track data)
#
# XML hierarchy for note data:
#   MasterTrack → tempo automation (BPM)
#   Tracks      → track definitions, name, tuning (open string pitches)
#   MasterBars  → one entry per bar, lists bar IDs per track
#   Bars        → maps bar id → voice ids
#   Voices      → maps voice id → beat ids (in order)
#   Beats       → rhythm reference (duration) + note id list
#   Notes       → midi pitch, string, fret, tie info, muted flag
#   Rhythms     → NoteValue (Whole/Half/Quarter/Eighth/16th/32nd) + optional dot
#
# String numbering in GP7 bass tracks (from the score.gpif we analyzed):
#   String 0 = lowest string (E on standard bass, open MIDI 28)
#   String 1 = A string (open MIDI 33)
#   String 2 = D string (open MIDI 38)
#   String 3 = G string (open MIDI 43, highest on 4-string bass)
# This matches our internal pipeline format (0=lowest) — no flipping needed.
#
# Tied notes: a note with tie origin=true starts a tie; the next note with
# the same pitch and tie destination=true extends the first note's duration
# rather than creating a new note. This is how long held notes are encoded.

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


# Maps GP7 NoteValue names to duration in beats (quarter note = 1 beat)
NOTE_VALUE_BEATS = {
    "Whole":   4.0,
    "Half":    2.0,
    "Quarter": 1.0,
    "Eighth":  0.5,
    "16th":    0.25,
    "32nd":    0.125,
    "64th":    0.0625,
}


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

def load_gp_notes(
    gp_path:     str,
    track_index: int = None,
) -> tuple:
    """
    Load a Guitar Pro 7 (.gp) file and return bass notes for the pipeline.

    Arguments:
        gp_path:     path to the .gp file (zip containing Content/score.gpif)
        track_index: which track to use (0-indexed). None = auto-detect bass.

    Returns (notes, fretting, tuning) where:
        notes:    list of (start_sec, end_sec, midi_pitch)
        fretting: list of (string_index, fret)  — same length as notes
        tuning:   string like "standard", "drop_d"
    """
    # Step 1 — open the zip and read score.gpif
    gp_path = Path(gp_path)
    with zipfile.ZipFile(gp_path, 'r') as zf:
        gpif_name = next(
            (name for name in zf.namelist() if name.endswith('score.gpif')),
            None
        )
        if gpif_name is None:
            raise ValueError(f"No score.gpif in {gp_path.name}. Files: {zf.namelist()}")
        with zf.open(gpif_name) as f:
            root = ET.fromstring(f.read())

    # Step 2 — parse all lookup tables
    bpm         = _parse_tempo(root)
    tracks      = _parse_tracks(root)
    rhythms     = _parse_rhythms(root)
    all_notes   = _parse_notes(root)
    all_beats   = _parse_beats(root, rhythms)
    all_voices  = _parse_voices(root)
    all_bars    = _parse_bars(root)
    master_bars = _parse_master_bars(root)

    # Step 3 — select track
    print(f"    Tempo: {bpm} BPM  |  Tracks: {len(tracks)}")
    for i, t in enumerate(tracks):
        print(f"      [{i}] '{t['name']}'  tuning: {t['tuning_name']}  "
              f"open pitches: {t['string_pitches']}")

    if track_index is None:
        track_index = _auto_detect_bass(tracks)
        print(f"    Auto-selected track {track_index} as bass")
    else:
        print(f"    Using track {track_index}")

    track          = tracks[track_index]
    string_pitches = track['string_pitches']
    tuning         = track['tuning_name']

    # Step 4 — walk bars in order, build note list
    seconds_per_beat = 60.0 / bpm
    current_time     = 0.0
    result_notes     = []
    result_fretting  = []

    # active_ties: midi_pitch → index in result_notes (for extending tied notes)
    active_ties: dict = {}

    for mbar in master_bars:
        bar_ids = mbar['bar_ids']

        if track_index >= len(bar_ids):
            # Track not present in this master bar — skip
            current_time += 4.0 * seconds_per_beat
            continue

        bar_id        = bar_ids[track_index]
        bar_voice_ids = all_bars.get(bar_id, [])

        if not bar_voice_ids:
            current_time += 4.0 * seconds_per_beat
            active_ties.clear()
            continue

        # Only process the first (primary) voice of the bar
        primary_voice = bar_voice_ids[0]
        beat_ids      = all_voices.get(primary_voice, [])

        for beat_id in beat_ids:
            beat = all_beats.get(beat_id)
            if beat is None:
                continue

            beat_dur = beat['duration_beats'] * seconds_per_beat

            for nid in beat['note_ids']:
                note = all_notes.get(nid)
                if note is None:
                    continue

                # Skip muted (dead) notes — they're percussive effects, not pitches
                if note['is_muted']:
                    continue

                pitch        = note['midi_pitch']
                string_index = note['string_index']
                fret         = note['fret']

                if note['is_tie_destination'] and pitch in active_ties:
                    # Extend the previously started note
                    prev_idx = active_ties[pitch]
                    ps, _, pp = result_notes[prev_idx]
                    result_notes[prev_idx] = (ps, current_time + beat_dur, pp)

                    # If this tied note also starts another tie, keep tracking
                    if not note['is_tie_origin']:
                        active_ties.pop(pitch, None)
                else:
                    # New note — record it
                    idx = len(result_notes)
                    result_notes.append((current_time, current_time + beat_dur, pitch))
                    result_fretting.append((string_index, fret))

                    if note['is_tie_origin']:
                        active_ties[pitch] = idx

            current_time += beat_dur

        # Clear ties at bar boundaries (GP7 ties don't cross bars)
        active_ties.clear()

    if not result_notes:
        raise ValueError(
            f"No notes found in track {track_index} ('{track['name']}'). "
            "Try setting track_index manually."
        )

    print(f"    Loaded {len(result_notes)} notes  "
          f"({result_notes[0][0]:.2f}s — {result_notes[-1][1]:.2f}s)")

    return result_notes, result_fretting, tuning


# ── PARSERS ───────────────────────────────────────────────────────────────────

def _parse_tempo(root: ET.Element) -> float:
    """Read BPM from MasterTrack tempo automation."""
    for auto in root.findall('.//MasterTrack/Automations/Automation'):
        if auto.findtext('Type') == 'Tempo':
            value = auto.findtext('Value', '120')
            return float(value.split()[0])
    return 120.0


def _parse_tracks(root: ET.Element) -> list:
    """Return list of track dicts: name, string_pitches, tuning_name."""
    tracks = []
    for track_el in root.findall('.//Tracks/Track'):
        name = track_el.findtext('Name', '').strip()

        pitches_text = track_el.findtext('.//Property[@name="Tuning"]/Pitches', '')
        if pitches_text.strip():
            string_pitches = [int(p) for p in pitches_text.strip().split()]
        else:
            string_pitches = []

        tracks.append({
            'name':          name,
            'string_pitches': string_pitches,
            'tuning_name':   _identify_tuning(string_pitches),
        })
    return tracks


def _identify_tuning(pitches: list) -> str:
    """Match open string pitches to a known tuning name."""
    if not pitches:
        return 'unknown'
    if len(pitches) == 5:
        return '5_string_bass'
    if len(pitches) == 6:
        return 'guitar'

    known = {
        'standard': [28, 33, 38, 43],
        'drop_d':   [26, 33, 38, 43],
        'eb':       [27, 32, 37, 42],
        'd_std':    [26, 31, 36, 41],
    }
    sorted_pitches = sorted(pitches)
    best, best_dist = 'standard', float('inf')
    for name, ref in known.items():
        if len(ref) != len(sorted_pitches):
            continue
        dist = sum(abs(a - b) for a, b in zip(sorted_pitches, ref))
        if dist < best_dist:
            best_dist = dist
            best      = name
    return best


def _auto_detect_bass(tracks: list) -> int:
    """Find bass track: first check name, then lowest average pitch."""
    for i, t in enumerate(tracks):
        if 'bass' in t['name'].lower():
            return i
    best, lowest = 0, float('inf')
    for i, t in enumerate(tracks):
        if not t['string_pitches']:
            continue
        avg = sum(t['string_pitches']) / len(t['string_pitches'])
        if avg < lowest:
            lowest, best = avg, i
    return best


def _parse_rhythms(root: ET.Element) -> dict:
    """Return {rhythm_id: duration_in_beats}. Handles dotted notes."""
    rhythms = {}
    for r in root.findall('.//Rhythms/Rhythm'):
        rid        = int(r.get('id', 0))
        note_val   = r.findtext('NoteValue', 'Eighth')
        base       = NOTE_VALUE_BEATS.get(note_val, 0.5)
        dot_el     = r.find('AugmentationDot')
        if dot_el is not None:
            # One dot adds half the base, two dots add half + quarter, etc.
            extra = base
            for _ in range(int(dot_el.get('count', 1))):
                extra /= 2
                base  += extra
        rhythms[rid] = base
    return rhythms


def _parse_notes(root: ET.Element) -> dict:
    """Return {note_id: note_dict} with pitch, string, fret, tie flags, muted."""
    notes = {}
    for n in root.findall('.//Notes/Note'):
        nid   = int(n.get('id', 0))
        pitch = int(n.findtext('.//Property[@name="Midi"]/Number', '-1'))
        fret  = int(n.findtext('.//Property[@name="Fret"]/Fret', '0'))

        string_raw = n.findtext('.//Property[@name="String"]/String', '0')
        try:
            string_index = int(float(string_raw))
        except (ValueError, TypeError):
            string_index = 0

        tie_el = n.find('Tie')
        is_origin = is_dest = False
        if tie_el is not None:
            is_origin = tie_el.get('origin',      'false').lower() == 'true'
            is_dest   = tie_el.get('destination', 'false').lower() == 'true'

        is_muted = n.find('.//Property[@name="Muted"]/Enable') is not None

        notes[nid] = {
            'midi_pitch':          pitch,
            'string_index':        string_index,
            'fret':                fret,
            'is_tie_origin':       is_origin,
            'is_tie_destination':  is_dest,
            'is_muted':            is_muted,
        }
    return notes


def _parse_beats(root: ET.Element, rhythms: dict) -> dict:
    """Return {beat_id: {duration_beats, note_ids, is_rest}}."""
    beats = {}
    for b in root.findall('.//Beats/Beat'):
        bid      = int(b.get('id', 0))
        rhythm_r = b.find('Rhythm')
        rref     = int(rhythm_r.get('ref', 0)) if rhythm_r is not None else 0
        dur      = rhythms.get(rref, 0.5)

        notes_text = b.findtext('Notes', '')
        note_ids   = [int(n) for n in notes_text.split()] if notes_text.strip() else []

        beats[bid] = {
            'duration_beats': dur,
            'note_ids':       note_ids,
            'is_rest':        len(note_ids) == 0,
        }
    return beats


def _parse_voices(root: ET.Element) -> dict:
    """Return {voice_id: [beat_id, ...]} in order."""
    voices = {}
    for v in root.findall('.//Voices/Voice'):
        vid        = int(v.get('id', 0))
        beats_text = v.findtext('Beats', '')
        beat_ids   = [int(b) for b in beats_text.split()] if beats_text.strip() else []
        voices[vid] = beat_ids
    return voices


def _parse_bars(root: ET.Element) -> dict:
    """Return {bar_id: [voice_id, ...]} (excludes -1 entries)."""
    bars = {}
    for b in root.findall('.//Bars/Bar'):
        bid         = int(b.get('id', 0))
        voices_text = b.findtext('Voices', '')
        voice_ids   = [
            int(v) for v in voices_text.split()
            if v.strip() and int(v) != -1
        ] if voices_text.strip() else []
        bars[bid] = voice_ids
    return bars


def _parse_master_bars(root: ET.Element) -> list:
    """Return list of {bar_ids: [bar_id_per_track]} in document order."""
    master_bars = []
    for mb in root.findall('.//MasterBars/MasterBar'):
        bars_text = mb.findtext('Bars', '')
        bar_ids   = [int(b) for b in bars_text.split()] if bars_text.strip() else []
        master_bars.append({'bar_ids': bar_ids})
    return master_bars