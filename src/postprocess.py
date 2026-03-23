# postprocess.py
# Cleans up common errors in the basic-pitch transcription before fretting.
# basic-pitch isn't perfect — it makes predictable mistakes on bass audio
# that we can catch and fix with simple rules.

import pretty_midi

BASS_MIDI_MIN = 28   # E1 — lowest note on a standard 4-string bass
BASS_MIDI_MAX = 67   # G4 — highest practical note (fret 24 on G string)
MIN_NOTE_GAP_MS = 80 # minimum gap between notes in milliseconds


def postprocess_midi(midi: pretty_midi.PrettyMIDI) -> pretty_midi.PrettyMIDI:
    """
    Runs all post-processing steps on the transcribed MIDI in order:
      1. Clamp octave errors
      2. Remove very short notes (noise)
      3. Merge consecutive same-pitch notes with tiny gaps
      4. Enforce minimum gap between notes (prevents game lag)
    """
    instrument = midi.instruments[0]
    instrument.notes = _fix_octave_errors(instrument.notes)
    instrument.notes = _remove_short_notes(instrument.notes)
    instrument.notes = _merge_repeated_notes(instrument.notes)
    instrument.notes = _enforce_minimum_gap(instrument.notes)

    print(f"    After postprocessing: {len(instrument.notes)} notes")
    return midi


def _fix_octave_errors(notes: list) -> list:
    """
    basic-pitch sometimes detects a note an octave too high or too low.
    If a pitch is outside the playable bass range, shift it by octaves
    until it lands in range.
    """
    fixed = []
    for note in notes:
        pitch = note.pitch
        while pitch > BASS_MIDI_MAX:
            pitch -= 12
        while pitch < BASS_MIDI_MIN:
            pitch += 12
        note.pitch = pitch
        fixed.append(note)
    return fixed


def _remove_short_notes(notes: list) -> list:
    """
    Remove notes shorter than 50ms — these are almost always
    transcription artifacts rather than intentional notes.
    """
    return [note for note in notes if (note.end - note.start) >= 0.05]


def _merge_repeated_notes(notes: list) -> list:
    """
    If the same pitch appears twice in a row with a gap smaller than 50ms,
    merge them into a single longer note. This fixes cases where basic-pitch
    splits one sustained note into two.
    """
    if not notes:
        return notes

    merged = [notes[0]]
    for current_note in notes[1:]:
        previous_note = merged[-1]
        gap_seconds = current_note.start - previous_note.end
        same_pitch   = current_note.pitch == previous_note.pitch

        if same_pitch and gap_seconds < 0.05:
            # Extend the previous note to cover the current one
            previous_note.end = current_note.end
        else:
            merged.append(current_note)

    return merged


def _enforce_minimum_gap(notes: list) -> list:
    """
    RS2014 can't handle more than ~12 notes per second without glitching.
    If two consecutive notes are closer than 80ms, drop the second one.
    This prevents the game from lagging on dense transcription sections.
    """
    if not notes:
        return notes

    filtered = [notes[0]]
    for current_note in notes[1:]:
        previous_note = filtered[-1]
        gap_ms = (current_note.start - previous_note.end) * 1000

        if gap_ms >= MIN_NOTE_GAP_MS:
            filtered.append(current_note)

    return filtered