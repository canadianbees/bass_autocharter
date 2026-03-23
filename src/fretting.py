# fretting.py
# Maps MIDI pitches → (string, fret) using a Viterbi dynamic programming algorithm.

TUNINGS = {
    "standard":   [28, 33, 38, 43],   # E1 A1 D2 G2
    "drop_d":     [26, 33, 38, 43],   # D1 A1 D2 G2
    "eb":         [27, 32, 37, 42],   # Eb1 Ab1 Db2 Gb2
    "d_standard": [26, 31, 36, 41],   # D1 G1 C2 F2
}

MAX_FRET = 24


def get_fret_positions(midi_pitch: int, tuning: str = "standard") -> list[tuple[int, int]]:
    """Return all valid (string_idx, fret) pairs. string_idx: 0=E, 1=A, 2=D, 3=G."""
    positions = []
    for string_idx, open_pitch in enumerate(TUNINGS[tuning]):
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRET:
            positions.append((string_idx, fret))
    return positions


def hand_movement_cost(prev: tuple, curr: tuple) -> float:
    """Cost of moving from prev (string, fret) to curr. Lower = more natural."""
    if prev is None:
        return 0.0
    s1, f1 = prev
    s2, f2 = curr
    fret_dist         = abs(f2 - f1)
    string_penalty    = abs(s2 - s1) * 0.8
    reach_penalty     = (3.0 + abs(f2 - f1)) if (f2 > f1 + 4 or f2 < f1 - 1) else 0.0
    high_fret_penalty = max(0, f2 - 12) * 0.2
    open_bonus        = -0.7 if f2 == 0 else 0.0
    return fret_dist + string_penalty + reach_penalty + high_fret_penalty + open_bonus


def _find_lowest_cost_path(midi_pitches: list[int], tuning: str) -> list[tuple[int, int]]:
    """Viterbi DP: find minimum hand-movement path through all note positions."""
    if not midi_pitches:
        return []

    n          = len(midi_pitches)
    cost_table = [{} for _ in range(n)]

    for pos in get_fret_positions(midi_pitches[0], tuning):
        cost_table[0][pos] = (0.0, None)

    for i in range(1, n):
        for curr in get_fret_positions(midi_pitches[i], tuning):
            best_cost, best_prev = float("inf"), None
            for prev, (prev_cost, _) in cost_table[i - 1].items():
                cost = prev_cost + hand_movement_cost(prev, curr)
                if cost < best_cost:
                    best_cost, best_prev = cost, prev
            cost_table[i][curr] = (best_cost, best_prev)

    last = min(cost_table[-1], key=lambda p: cost_table[-1][p][0])
    path = [last]
    for i in range(n - 1, 0, -1):
        last = cost_table[i][last][1]
        path.insert(0, last)
    return path


def find_optimal_fretting(
    midi_pitches: list[int],
    tuning: str = "standard"
) -> tuple[list[tuple[int, int]], list[int]]:
    """
    Returns (fretting, playable_pitches) — both same length, unplayable notes dropped.
    Use filter_notes_to_fretting() to keep your notes list in sync automatically.
    """
    playable, skipped = [], 0
    for pitch in midi_pitches:
        if get_fret_positions(pitch, tuning):
            playable.append(pitch)
        else:
            print(f"    Warning: MIDI pitch {pitch} not playable in {tuning} — skipped")
            skipped += 1
    if skipped:
        print(f"    Skipped {skipped} unplayable pitches")
    return _find_lowest_cost_path(playable, tuning), playable


def filter_notes_to_fretting(
    notes:        list[tuple],
    midi_pitches: list[int],
    tuning:       str = "standard"
) -> tuple[list[tuple], list[tuple[int, int]]]:
    """
    Filters notes AND computes fretting in one call.
    Guarantees returned lists are the same length and safe to zip.

    Returns (playable_notes, fretting).
    """
    fretting, _ = find_optimal_fretting(midi_pitches, tuning)

    # Walk in parallel to handle duplicate pitches correctly
    playable_notes = []
    pitch_iter     = iter(midi_pitches)
    for note in notes:
        p = next(pitch_iter)
        if get_fret_positions(p, tuning):
            playable_notes.append(note)

    if len(playable_notes) != len(fretting):
        raise RuntimeError(
            f"filter_notes_to_fretting: length mismatch "
            f"({len(playable_notes)} notes vs {len(fretting)} fretting). "
            "This is a bug — please report it."
        )

    return playable_notes, fretting