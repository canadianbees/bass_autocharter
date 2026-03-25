# rhythm_detector.py
#
# Python port of RocksmithToTab's rhythm detection system (2016, C#).
# Original: RocksmithToTabLib/RhythmDetector.cs + Score.cs (Bar.GetDuration)
#
# ── WHAT THIS SOLVES ──────────────────────────────────────────────────────────
#
# The core problem in GP→XML conversion is that Guitar Pro stores rhythm
# information explicitly (NoteValue + dots = exact duration), but Rocksmith
# stores notes as absolute timestamps in seconds. When you read a GP file and
# emit RS XML, the note *pitches* are correct, but the *timing* can be off
# because floating-point beat math accumulates error and does not snap to
# the musical grid the way Rocksmith expects.
#
# RocksmithToTab solved this for the RS→GP direction. We reverse-engineer
# their algorithm for our GP→RS direction.
#
# ── THE ALGORITHM ─────────────────────────────────────────────────────────────
#
# Duration unit: multiples of 1/48th of a quarter note.
#   48 = quarter note
#   24 = eighth note
#   16 = eighth-note triplet  (48 * 2/3)
#   12 = sixteenth note
#    8 = sixteenth-note triplet
#    6 = thirty-second note
#    3 = thirty-second-note triplet
#    2 = sixty-fourth note
#   etc.
#
# One measure of 4/4 = 4 beats × 48 units = 192 units total.
# One measure of 3/4 = 3 beats × 48 units = 144 units total.
#
# Step 1  get_bar_duration(time_nominator, time_denominator)
#         Returns total bar duration in units (e.g. 192 for 4/4).
#
# Step 2  get_beat_duration(time_denominator)
#         Returns one beat's duration in units (48 for /4, 24 for /8).
#
# Step 3  convert_seconds_to_units(note_durations_sec, bar_start_beat_times, time_denominator)
#         Converts a list of note durations (in seconds) to units, using the
#         ebeat sub-beat times to compensate for tempo micro-variation.
#         This is a port of Bar.GetDuration() from Score.cs.
#
# Step 4  get_rhythm(note_durations_units, bar_duration, beat_duration)
#         Snaps those floating-point unit values to a valid musical grid by
#         recursively finding the best beat-boundary match.
#         Returns a list of RhythmValue(duration_units, note_index).
#         This is a port of RhythmDetector.GetRhythm / MatchRhythm / SplitDurations.
#
# ── USAGE ─────────────────────────────────────────────────────────────────────
#
# In gp_input.py you already read beats as (start_sec, duration_sec).
# In rs_xml.py you already emit ebeats from a fixed BPM grid.
#
# Replace the naive "just use the GP beat duration directly" approach with:
#
#   from rhythm_detector import snap_bar_to_grid, units_to_seconds
#
#   for each bar:
#       note_durations_sec = [beat_dur_sec for each note in bar]
#       beat_times = ebeat times for this bar (from ebeats list)
#       time_nom, time_denom = bar time signature (4, 4 for most songs)
#
#       rhythm_values = snap_bar_to_grid(
#           note_durations_sec, beat_times, time_nom, time_denom
#       )
#       # rhythm_values[i].duration_units is the snapped duration in 1/48ths
#       # rhythm_values[i].note_index tells you which original note this maps to
#       #   (can be >1 entry per original note if a note was split)
#
#       quarter_note_sec = 60.0 / bpm
#       for rv in rhythm_values:
#           duration_sec = units_to_seconds(rv.duration_units, time_nom, time_denom, quarter_note_sec)
#
# ── PRINTABLE DURATIONS ───────────────────────────────────────────────────────
#
# Only these unit values correspond to a note value that can actually be
# written in standard notation. Any other value must be split.
#
#   2  = 64th note
#   3  = 64th-note triplet
#   4  = 32nd note
#   6  = 32nd-note triplet  / dotted 64th
#   8  = 16th note
#   9  = dotted 32nd note
#  12  = 16th-note triplet  / dotted 32nd
#  16  = eighth note
#  18  = dotted quarter triplet (unusual)
#  24  = eighth-note triplet   / dotted 16th note? no — dotted eighth = 24
#        actually: dotted eighth = 8 + 4 = 12... wait:
#        dotted quarter = 48 + 24 = 72 — but 72 is not printable alone,
#        it's expressed as quarter + eighth tied.
#        The set below matches the C# original exactly.
#  32  = quarter note
#  36  = (unusual — skip unless you need it)
#  48  = quarter note   ← standard reference
#  72  = dotted quarter (48+24)
#  96  = half note
# 144  = dotted half
# 192  = whole note
#
# (The C# list: {2,3,4,6,8,9,12,16,18,24,32,36,48,72,96,144,192})

from __future__ import annotations
from dataclasses import dataclass


# ── DATA TYPES ────────────────────────────────────────────────────────────────

@dataclass
class RhythmValue:
    """
    One snapped note duration.

    duration_units : int
        Duration in 1/48ths of a quarter note.
    note_index : int
        Which original note this belongs to.
        If the same note_index appears twice consecutively, the original note
        was split — you should tie the two resulting RS notes together.
    """
    duration_units: int
    note_index:     int


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

# All note values that can be written as a single note (no ties needed).
# Matches RhythmDetector.PrintableDurations in the C# source.
PRINTABLE_DURATIONS: frozenset[int] = frozenset(
    [2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36, 48, 72, 96, 144, 192]
)


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def get_bar_duration(time_nominator: int, time_denominator: int) -> int:
    """
    Total bar duration in 1/48th-quarter-note units.

    Examples:
        4/4  →  4 * 48  = 192
        3/4  →  3 * 48  = 144
        6/8  →  6 * 24  = 144  (same length, different feel)
        5/4  →  5 * 48  = 240
    """
    return get_beat_duration(time_denominator) * time_nominator


def get_beat_duration(time_denominator: int) -> int:
    """
    One beat's duration in 1/48th-quarter-note units.

    /4 time → 48 units per beat (quarter note)
    /8 time → 24 units per beat (eighth note)

    Only /4 and /8 are considered (matching the C# original).
    """
    return 24 if time_denominator == 8 else 48


def convert_seconds_to_units(
    note_durations_sec: list[float],
    beat_times_sec:     list[float],
    time_denominator:   int,
) -> list[float]:
    """
    Convert a list of note durations (in seconds) to 1/48th-quarter-note units,
    using the actual ebeat times to compensate for tempo variation within the bar.

    This is a Python port of Bar.GetDuration() in Score.cs.

    Args:
        note_durations_sec:
            Duration in seconds for each note in the bar, in order.
            These are "note i runs from its start time to the start of note i+1
            (or the bar end for the last note)".

        beat_times_sec:
            Absolute times of each ebeat (sub-beat) boundary within the bar,
            including the bar's start and the first beat of the NEXT bar.
            In RS, ebeats with measure >= 0 are downbeats; ebeats with -1 are
            sub-beats. The BeatTimes list in the C# includes both, plus the
            next-bar start as the final sentinel.

            For a steady 4/4 bar at 120 BPM:
                [0.0, 0.5, 1.0, 1.5, 2.0]  (bar start + 3 sub-beats + next bar start)

        time_denominator:
            4 for /4 time, 8 for /8 time.

    Returns:
        List of float durations in units (not yet rounded to grid).
    """
    # Build cumulative note start/end times from durations
    note_starts: list[float] = []
    t = beat_times_sec[0] if beat_times_sec else 0.0
    for dur in note_durations_sec:
        note_starts.append(t)
        t += dur

    units_list: list[float] = []
    for i, (start, dur_sec) in enumerate(zip(note_starts, note_durations_sec)):
        end = start + dur_sec
        duration_units = _get_duration_units(
            start, end, beat_times_sec, time_denominator
        )
        units_list.append(duration_units)

    return units_list


def snap_bar_to_grid(
    note_durations_sec: list[float],
    beat_times_sec:     list[float],
    time_nominator:     int,
    time_denominator:   int,
) -> list[RhythmValue]:
    """
    Convert raw note durations (seconds) to snapped, printable rhythm values.

    This combines convert_seconds_to_units + get_rhythm in one call.

    Args:
        note_durations_sec:
            Raw note durations in seconds for one bar (same as above).
        beat_times_sec:
            Ebeat boundary times for this bar (same as above).
        time_nominator:
            Number of beats in the bar (4 for 4/4, 3 for 3/4, etc.).
        time_denominator:
            Beat unit (4 for /4, 8 for /8).

    Returns:
        List of RhythmValue. May be longer than the input if any notes were split.
        Use note_index to map back to the original notes.
    """
    units = convert_seconds_to_units(
        note_durations_sec, beat_times_sec, time_denominator
    )
    bar_dur  = get_bar_duration(time_nominator, time_denominator)
    beat_dur = get_beat_duration(time_denominator)
    return get_rhythm(units, bar_dur, beat_dur)


def get_rhythm(
    note_durations_units: list[float],
    bar_duration:         int,
    beat_duration:        int,
) -> list[RhythmValue]:
    """
    Snap a list of floating-point unit durations to valid musical grid positions.

    Port of RhythmDetector.GetRhythm() from the C# source.

    Args:
        note_durations_units:
            Floating-point note durations in 1/48th-quarter-note units.
            These don't have to sum exactly to bar_duration; they will be scaled.
        bar_duration:
            Total bar size in units (e.g. 192 for 4/4).
        beat_duration:
            One beat in units (48 for /4, 24 for /8).

    Returns:
        List of RhythmValue with integer durations that sum to bar_duration.
    """
    if not note_durations_units:
        return []

    durations = list(note_durations_units)  # copy

    # Scale all durations so they sum exactly to bar_duration
    total = sum(durations)
    if total <= 0:
        # Degenerate: put everything in a single whole-bar note
        return [RhythmValue(bar_duration, 0)]

    scaling = bar_duration / total
    durations = [d * scaling for d in durations]

    # Build cumulative note-end positions
    note_ends: list[float] = []
    running = 0.0
    for d in durations:
        running += d
        note_ends.append(running)

    # Recursively snap note ends to beat grid
    _match_rhythm(note_ends, 0, len(note_ends), 0.0, float(bar_duration), beat_duration)

    # Convert cumulative ends back to individual durations
    result: list[RhythmValue] = []
    prev_end = 0.0
    for i, end in enumerate(note_ends):
        dur = int(round(end - prev_end))
        result.append(RhythmValue(duration_units=dur, note_index=i))
        prev_end = end

    # Split any durations that can't be represented as a single note value
    _split_durations(result, bar_duration, beat_duration)

    return result


def units_to_seconds(
    duration_units:    int,
    time_nominator:    int,
    time_denominator:  int,
    quarter_note_sec:  float,
) -> float:
    """
    Convert a snapped duration (in 1/48th-quarter-note units) back to seconds.

    Args:
        duration_units:   value from RhythmValue.duration_units
        time_nominator:   beats per bar
        time_denominator: beat unit (4 or 8)
        quarter_note_sec: length of one quarter note in seconds = 60 / BPM
    """
    return duration_units / 48.0 * quarter_note_sec


# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────

def _get_duration_units(
    start:            float,
    end:              float,
    beat_times_sec:   list[float],
    time_denominator: int,
) -> float:
    """
    Port of Bar.GetDuration() from Score.cs.

    Converts the real-time span [start, end] to 1/48th-quarter-note units
    by splitting the span across ebeat sub-intervals and summing proportional
    contributions from each sub-interval.
    """
    duration = 0.0
    n_beats = len(beat_times_sec)
    for i in range(n_beats - 1):
        beat_start = beat_times_sec[i]
        beat_end   = beat_times_sec[i + 1]

        if start >= beat_end:
            continue
        if end <= beat_start:
            break

        beat_length  = beat_end - beat_start
        note_start_  = max(start, beat_start)
        note_end_    = min(end,   beat_end)

        # Each sub-beat contributes (4 / time_denominator) quarter notes.
        # Multiply by 48 to get units.
        beat_duration = (note_end_ - note_start_) / beat_length * 4 / time_denominator
        duration += beat_duration

    return duration * 48.0


def _match_rhythm(
    note_ends:    list[float],
    start:        int,
    end:          int,
    offset:       float,
    length:       float,
    beat_duration: int,
) -> None:
    """
    Recursive divide-and-conquer: snap the note_ends in [start, end) to the
    nearest beat-grid position within [offset, offset+length].

    Port of RhythmDetector.MatchRhythm() from the C# source.
    Mutates note_ends in place.
    """
    # Base case: one note or fewer — nothing to snap
    if end - start <= 1:
        return

    # Can't subdivide any further: merge all notes here into the last one
    if length <= 3:
        for i in range(start, end - 1):
            note_ends[i] = offset
        return

    triplet_beat = beat_duration * 2 // 3

    PRECISION = 1.0
    min_match_pos  = start
    min_match_end  = offset
    min_match_diff = length + 1.0

    # Find the note end that best aligns with a beat or triplet-beat boundary
    for i in range(start, end - 1):
        # Regular beat grid
        mult = round(note_ends[i] / beat_duration)
        diff = abs(mult * beat_duration - note_ends[i])
        cand = mult * beat_duration
        if diff < min_match_diff and offset <= cand <= offset + length:
            min_match_pos  = i
            min_match_end  = cand
            min_match_diff = diff

        # Triplet grid
        if triplet_beat > 0:
            mult = round(note_ends[i] / triplet_beat)
            diff = abs(mult * triplet_beat - note_ends[i])
            cand = mult * triplet_beat
            if diff < min_match_diff and offset <= cand <= offset + length:
                min_match_pos  = i
                min_match_end  = cand
                min_match_diff = diff

    if min_match_diff < PRECISION or beat_duration <= 3:
        # Snap the winning note end and recurse on both sides
        corrected_left  = min_match_end - offset
        corrected_right = length - corrected_left

        note_ends[min_match_pos] = min_match_end

        # Recurse left  (notes before the snap point)
        _match_rhythm(note_ends, start, min_match_pos + 1,
                      offset, corrected_left, beat_duration)
        # Recurse right (notes after the snap point)
        _match_rhythm(note_ends, min_match_pos + 1, end,
                      min_match_end, corrected_right, beat_duration)
    else:
        # No good match at this resolution — try half the beat duration
        _match_rhythm(note_ends, start, end, offset, length, beat_duration // 2)


def _split_durations(
    durations:    list[RhythmValue],
    bar_duration: int,
    beat_length:  int,
) -> None:
    """
    Split any RhythmValue whose duration is not in PRINTABLE_DURATIONS into
    two or more printable values.  Mutates the list in place.

    Port of RhythmDetector.SplitDurations() from the C# source.
    """
    cur_pos = 0
    i = 0
    while i < len(durations):
        rv = durations[i]

        if rv.duration_units <= 1:
            i += 1
            continue

        if rv.duration_units in PRINTABLE_DURATIONS:
            cur_pos += rv.duration_units
            i += 1
            continue

        # Try to split this duration into two printable values
        note_end  = cur_pos + rv.duration_units
        done      = False

        cur_beat = beat_length
        n, d = 2, 3   # alternating multipliers for even / triplet sub-beats

        while not done and cur_beat >= 2:
            max_mult = note_end // cur_beat
            for j in range(max_mult, 0, -1):
                remaining = note_end - j * cur_beat
                if remaining < 2 and remaining != 0:
                    break
                dur_a = rv.duration_units - remaining
                if dur_a in PRINTABLE_DURATIONS:
                    rv.duration_units = dur_a
                    if remaining != 0:
                        durations.insert(i + 1, RhythmValue(
                            duration_units=remaining,
                            note_index=rv.note_index,
                        ))
                    done = True
                    break

            # Alternate between even and triplet sub-beat divisions
            cur_beat = cur_beat * n // d
            if n == 2:
                n, d = 3, 4
            else:
                n, d = 2, 3

        if rv.duration_units not in PRINTABLE_DURATIONS:
            # Last resort: split in half and retry on the next iteration
            half = rv.duration_units // 2
            durations.insert(i + 1, RhythmValue(
                duration_units=rv.duration_units - half,
                note_index=rv.note_index,
            ))
            rv.duration_units = half
            i -= 1  # retry this slot

        else:
            cur_pos += rv.duration_units

        i += 1


# ── EBEAT BUILDER (mirrors rs_xml._generate_ebeats) ──────────────────────────

def build_ebeat_times(
    song_length_sec: float,
    bpm:             float,
    beats_per_bar:   int = 4,
) -> list[tuple[float, int]]:
    """
    Generate a list of (time_sec, measure_number) ebeat entries.

    measure_number is the 1-based bar index for downbeats, -1 for sub-beats.
    This matches what Rocksmith expects in the <ebeats> section.

    Returns a flat list you can use to:
      - write <ebeat> elements in rs_xml.py
      - build per-bar beat_times lists for snap_bar_to_grid()
    """
    beat_dur = 60.0 / bpm
    entries: list[tuple[float, int]] = []
    t       = 0.0
    beat    = 0
    measure = 1

    while t <= song_length_sec + beat_dur:
        is_downbeat = (beat % beats_per_bar == 0)
        entries.append((t, measure if is_downbeat else -1))
        if is_downbeat:
            measure += 1
        t    += beat_dur
        beat += 1

    return entries


def group_ebeats_by_bar(
    ebeat_entries: list[tuple[float, int]],
) -> list[list[float]]:
    """
    Group ebeat times into per-bar lists suitable for snap_bar_to_grid().

    Each inner list is [bar_start, sub_beat_1, sub_beat_2, ..., next_bar_start].
    The final sentinel (next_bar_start) makes GetDuration work correctly for
    the last note in a bar.

    Args:
        ebeat_entries: output of build_ebeat_times()

    Returns:
        List of beat-time lists, one per bar.
    """
    # Collect downbeat indices
    downbeat_indices = [
        i for i, (_, m) in enumerate(ebeat_entries) if m != -1
    ]

    bars: list[list[float]] = []
    for k in range(len(downbeat_indices) - 1):
        start_idx = downbeat_indices[k]
        end_idx   = downbeat_indices[k + 1]
        # Include all beats from this bar's downbeat up to (and including)
        # the next bar's downbeat as a sentinel
        bar_times = [ebeat_entries[j][0] for j in range(start_idx, end_idx + 1)]
        bars.append(bar_times)

    return bars


# ── INTEGRATION EXAMPLE ───────────────────────────────────────────────────────
#
# How to plug this into gp_input.py + rs_xml.py:
#
#   from rhythm_detector import (
#       snap_bar_to_grid, units_to_seconds,
#       build_ebeat_times, group_ebeats_by_bar,
#       PRINTABLE_DURATIONS,
#   )
#
#   # 1. Build ebeats (do this once per song)
#   ebeat_entries = build_ebeat_times(song_length_sec, bpm, beats_per_bar=4)
#   bar_beat_times = group_ebeats_by_bar(ebeat_entries)
#   quarter_note_sec = 60.0 / bpm
#
#   # 2. For each bar of GP notes:
#   for bar_idx, bar_notes in enumerate(notes_grouped_by_bar):
#       beat_times = bar_beat_times[bar_idx]  # [bar_start, ..., next_bar_start]
#       bar_start  = beat_times[0]
#       bar_end    = beat_times[-1]
#
#       # Raw durations: note i runs until next note's start (or bar end)
#       note_starts = [n.start_sec for n in bar_notes]
#       note_ends_  = note_starts[1:] + [bar_end]
#       raw_durs    = [e - s for s, e in zip(note_starts, note_ends_)]
#
#       # Snap to musical grid
#       rhythm_vals = snap_bar_to_grid(
#           raw_durs, beat_times,
#           time_nominator=4, time_denominator=4
#       )
#
#       # rhythm_vals may be longer than bar_notes if any note was split.
#       # Use note_index to find the original note.
#       for rv in rhythm_vals:
#           orig_note     = bar_notes[rv.note_index]
#           snapped_dur   = units_to_seconds(
#               rv.duration_units, 4, 4, quarter_note_sec
#           )
#           # emit orig_note at orig_note.start_sec with sustain = snapped_dur - epsilon
#
# ── WHAT CAUSES THE RHYTHM TO BE "OFF" IN YOUR CURRENT CODE ─────────────────
#
# Your gp_input.py reads beats as (start_sec, duration_sec) from GP XML and
# emits them directly to rs_xml.py without any grid-snapping.  The problem:
#
#   1. GP files store rhythm as NoteValue (Quarter, Eighth, etc.) + optional dot.
#      This is already quantised — the GP editor snapped it for you.
#
#   2. You convert those to seconds using seconds_per_beat = 60.0 / bpm.
#      Fine so far.
#
#   3. rs_xml.py emits ebeats using the same BPM.  Also fine.
#
#   4. BUT: the Rocksmith engine uses ebeats, not absolute time, to decide
#      *which beat a note falls on*. If floating-point rounding has moved a
#      note by even 1-2ms relative to where the ebeat grid says it should be,
#      RS will mis-classify it (e.g., a downbeat gets counted as landing on
#      the upbeat just before it).
#
#   5. Accumulated per-bar: if a 4/4 bar has 8 eighth notes and each is off
#      by 1ms, the 8th note lands 8ms late — enough to be perceived as wrong.
#
# The fix: after converting GP beats to seconds, group them into bars, pass
# them through snap_bar_to_grid(), then re-derive the absolute note times
# from the snapped durations.  This keeps every note exactly on a
# 1/48th-quarter-note boundary relative to the ebeat grid.