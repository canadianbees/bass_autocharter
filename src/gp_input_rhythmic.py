import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from src.rhythm_detector import get_rhythm, units_to_seconds

from src.gp_input import (
    _parse_tempo,
    _parse_tracks,
    _parse_rhythms,
    _parse_notes,
    _parse_beats,
    _parse_voices,
    _parse_bars,
    _parse_master_bars,
    _auto_detect_bass,
)


# ── GP RHYTHM → UNITS ─────────────────────────────────────────────

def gp_rhythm_to_units(rhythm):
    base_map = {
        "whole": 192,
        "half": 96,
        "quarter": 48,
        "eighth": 24,
        "16th": 12,
        "32nd": 6,
    }

    base = base_map[rhythm["value"]]

    # dots
    if rhythm["dots"] == 1:
        base *= 1.5
    elif rhythm["dots"] == 2:
        base *= 1.75

    # tuplets
    if rhythm["tuplet"]:
        num, den = rhythm["tuplet"]
        base *= den / num

    return float(base)


# ── MAIN LOADER ───────────────────────────────────────────────────

def load_gp_notes_units(
    gp_path: str,
    track_index: int = None,
    time_nom: int = 4,
    time_denom: int = 4,
):
    gp_path = Path(gp_path)

    with zipfile.ZipFile(gp_path, 'r') as zf:
        gpif_name = next(n for n in zf.namelist() if n.endswith('score.gpif'))
        with zf.open(gpif_name) as f:
            root = ET.fromstring(f.read())

    bpm = _parse_tempo(root)
    tracks = _parse_tracks(root)
    rhythms = _parse_rhythms(root)
    all_notes = _parse_notes(root)
    all_beats = _parse_beats(root, rhythms)
    all_voices = _parse_voices(root)
    all_bars = _parse_bars(root)
    master_bars = _parse_master_bars(root)

    if track_index is None:
        track_index = _auto_detect_bass(tracks)

    track = tracks[track_index]
    tuning = track["tuning_name"]

    quarter_note_sec = 60.0 / bpm

    result_notes = []
    result_fretting = []

    current_units = 0  # 🔑 NO SECONDS

    for mbar in master_bars:
        bar_ids = mbar["bar_ids"]

        if track_index >= len(bar_ids):
            current_units += time_nom * 48
            continue

        bar_id = bar_ids[track_index]
        bar_voice_ids = all_bars.get(bar_id, [])

        if not bar_voice_ids:
            current_units += time_nom * 48
            continue

        primary_voice = bar_voice_ids[0]
        beat_ids = all_voices.get(primary_voice, [])

        raw_units = []
        beat_note_map = []

        for beat_id in beat_ids:
            beat = all_beats.get(beat_id)
            if beat is None:
                continue

            if "rhythm" in beat:
                units = gp_rhythm_to_units(beat["rhythm"])
            else:
                # fallback using duration_beats
                units = beat["duration_beats"] * 48

            raw_units.append(units)
            beat_note_map.append(beat)

        if not raw_units:
            current_units += time_nom * 48
            continue

        # ── SNAP IN UNIT SPACE ───────────────────────────
        bar_duration = time_nom * 48
        beat_duration = 48 if time_denom == 4 else 24

        rhythm_values = get_rhythm(raw_units, bar_duration, beat_duration)

        beat_cursor_units = current_units

        for rv in rhythm_values:
            beat = beat_note_map[rv.note_index]
            dur_units = rv.duration_units

            if not beat["is_rest"]:
                for nid in beat["note_ids"]:
                    note = all_notes.get(nid)
                    if note is None or note["is_muted"]:
                        continue

                    pitch = note["midi_pitch"]
                    string_index = note["string_index"]
                    fret = note["fret"]

                    start_sec = beat_cursor_units / 48.0 * quarter_note_sec
                    end_sec = (beat_cursor_units + dur_units) / 48.0 * quarter_note_sec

                    result_notes.append((start_sec, end_sec, pitch))
                    result_fretting.append((string_index, fret))

            beat_cursor_units += dur_units

        # 🔑 PERFECT BAR ALIGNMENT (no drift)
        current_units += bar_duration

    return result_notes, result_fretting, tuning