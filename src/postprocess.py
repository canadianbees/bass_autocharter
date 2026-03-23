# postprocess.py
# Cleans up common errors in the aubio transcription before fretting.
#
# Input/output format: list of (start_sec, end_sec, midi_pitch) tuples
# This is the native format from transcribe.py — no pretty_midi dependency.

BASS_MIDI_MIN = 28    # E1  — lowest note on standard 4-string bass
BASS_MIDI_MAX = 55    # G3  — cap lower than before to kill octave errors
MIN_NOTE_SEC  = 0.08  # 80ms minimum note duration
MIN_GAP_SEC   = 0.04  # 40ms minimum gap between notes (supports sixteenth notes)
MERGE_GAP_SEC = 0.02  # 20ms — same-pitch notes closer than this get merged


def postprocess_notes(notes: list[tuple]) -> list[tuple]:
    """
    Runs all post-processing steps in order:
      1. Remove simultaneous notes    — keep lowest pitch only (bass is monophonic)
      2. Fix octave errors            — shift out-of-range notes into bass range
      3. Remove short notes           — kills ghost notes and artifacts
      4. Merge repeated notes         — fixes over-segmented sustained notes
      5. Enforce minimum gap          — prevents RS2014 note density glitches

    Input/output: list of (start_sec, end_sec, midi_pitch)
    """
    notes = sorted(notes, key=lambda n: n[0])
    notes = _remove_simultaneous(notes)
    notes = _fix_octave_errors(notes)
    notes = _remove_short_notes(notes)
    notes = _merge_repeated_notes(notes)
    notes = _enforce_minimum_gap(notes)

    print(f"    After postprocessing: {len(notes)} notes")
    return notes


# ── STEP 1: REMOVE SIMULTANEOUS NOTES ────────────────────────────────────────

def _remove_simultaneous(notes: list[tuple]) -> list[tuple]:
    """
    Bass is monophonic — only one note plays at a time.
    If two notes start within 30ms of each other, keep only the lowest pitch
    (most likely to be the real fundamental, not a harmonic).
    """
    if not notes:
        return notes

    result = []
    i = 0
    while i < len(notes):
        group = [notes[i]]
        j = i + 1
        while j < len(notes) and (notes[j][0] - notes[i][0]) < 0.03:
            group.append(notes[j])
            j += 1
        result.append(min(group, key=lambda n: n[2]))
        i = j

    return result


# ── STEP 2: FIX OCTAVE ERRORS ─────────────────────────────────────────────────

def _fix_octave_errors(notes: list[tuple]) -> list[tuple]:
    """
    Shift notes outside the bass range up or down by octaves until in range.
    BASS_MIDI_MAX is set conservatively (G3) to catch the common case where
    the detector picks up an overtone an octave above the real note.
    """
    fixed = []
    for start, end, pitch in notes:
        while pitch > BASS_MIDI_MAX:
            pitch -= 12
        while pitch < BASS_MIDI_MIN:
            pitch += 12
        fixed.append((start, end, pitch))
    return fixed


# ── STEP 3: REMOVE SHORT NOTES ────────────────────────────────────────────────

def _remove_short_notes(notes: list[tuple]) -> list[tuple]:
    """
    Remove notes shorter than MIN_NOTE_SEC.
    Anything under 80ms is almost certainly a detection artifact.
    """
    return [(s, e, p) for s, e, p in notes if (e - s) >= MIN_NOTE_SEC]


# ── STEP 4: MERGE REPEATED NOTES ──────────────────────────────────────────────

def _merge_repeated_notes(notes: list[tuple]) -> list[tuple]:
    """
    If the same pitch appears twice in a row with a gap smaller than 20ms,
    merge them into one longer note.
    Fixes over-segmented sustained notes without touching intentional repeats.
    """
    if not notes:
        return notes

    merged = [list(notes[0])]
    for start, end, pitch in notes[1:]:
        prev = merged[-1]
        gap  = start - prev[1]
        if pitch == prev[2] and gap < MERGE_GAP_SEC:
            prev[1] = end       # extend previous note's end time
        else:
            merged.append([start, end, pitch])

    return [tuple(n) for n in merged]


# ── STEP 5: ENFORCE MINIMUM GAP ───────────────────────────────────────────────

def _enforce_minimum_gap(notes: list[tuple]) -> list[tuple]:
    """
    RS2014 glitches with notes closer than ~40ms.
    If a note starts too soon after the previous one ends, drop it.
    40ms supports sixteenth notes up to ~375 BPM — well above any bass line.
    """
    if not notes:
        return notes

    filtered = [notes[0]]
    for start, end, pitch in notes[1:]:
        prev_end = filtered[-1][1]
        if (start - prev_end) >= MIN_GAP_SEC:
            filtered.append((start, end, pitch))

    return filtered