# fretting.py
# Maps MIDI pitches → (string, fret) using an improved Viterbi algorithm

# ── TUNINGS ─────────────────────────────────────────────────────────────

TUNINGS = {
    "standard":   [28, 33, 38, 43],
    "drop_d":     [26, 33, 38, 43],
    "eb":         [27, 32, 37, 42],
    "d_standard": [26, 31, 36, 41],
}

MAX_FRET = 24


# ── POSITION LOOKUP ─────────────────────────────────────────────────────

def get_fret_positions(midi_pitch: int, tuning: str = "standard") -> list[tuple[int, int]]:
    open_strings = TUNINGS[tuning]
    positions = []

    for string_idx, open_pitch in enumerate(open_strings):
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRET:
            positions.append((string_idx, fret))

    return positions


# ── IMPROVED COST FUNCTION ──────────────────────────────────────────────

def hand_movement_cost(prev: tuple, curr: tuple) -> float:
    """
    Improved cost model:
    - penalizes large fret jumps
    - penalizes string changes (but not too harshly)
    - penalizes unreachable hand spans
    - slightly prefers open strings
    """

    if prev is None:
        return 0.0

    s1, f1 = prev
    s2, f2 = curr

    # ── 1. fret movement ────────────────────────────────────────────────
    fret_dist = abs(f2 - f1)

    # ── 2. string change ────────────────────────────────────────────────
    string_penalty = abs(s2 - s1) * 0.8

    # ── 3. reach penalty (hand span ~4 frets) ───────────────────────────
    reach_penalty = 0.0
    if f2 > f1 + 4 or f2 < f1 - 1:
        reach_penalty = 3.0 + abs(f2 - f1)

    # ── 4. high fret penalty (less common for bass lines) ───────────────
    high_fret_penalty = max(0, f2 - 12) * 0.2

    # ── 5. open string bonus ────────────────────────────────────────────
    open_bonus = -0.7 if f2 == 0 else 0.0

    return (
        fret_dist
        + string_penalty
        + reach_penalty
        + high_fret_penalty
        + open_bonus
    )


# ── VITERBI ALGORITHM ───────────────────────────────────────────────────

def _find_lowest_cost_path(midi_pitches: list[int], tuning: str) -> list[tuple[int, int]]:
    if not midi_pitches:
        return []

    num_notes = len(midi_pitches)
    cost_table = [{} for _ in range(num_notes)]

    # ── init ────────────────────────────────────────────────────────────
    for pos in get_fret_positions(midi_pitches[0], tuning):
        cost_table[0][pos] = (0.0, None)

    # ── forward pass ────────────────────────────────────────────────────
    for i in range(1, num_notes):
        positions = get_fret_positions(midi_pitches[i], tuning)

        for curr in positions:
            best_cost = float("inf")
            best_prev = None

            for prev, (prev_cost, _) in cost_table[i - 1].items():
                c = prev_cost + hand_movement_cost(prev, curr)

                if c < best_cost:
                    best_cost = c
                    best_prev = prev

            cost_table[i][curr] = (best_cost, best_prev)

    # ── backtrack ───────────────────────────────────────────────────────
    last = min(cost_table[-1], key=lambda p: cost_table[-1][p][0])
    path = [last]

    for i in range(num_notes - 1, 0, -1):
        last = cost_table[i][last][1]
        path.insert(0, last)

    return path


# ── PUBLIC API ──────────────────────────────────────────────────────────

def find_optimal_fretting(midi_pitches: list[int], tuning: str = "standard") -> list[tuple[int, int]]:
    playable = []

    for pitch in midi_pitches:
        positions = get_fret_positions(pitch, tuning)
        if not positions:
            print(f"Warning: MIDI pitch {pitch} not playable in {tuning}")
            continue
        playable.append(pitch)

    return _find_lowest_cost_path(playable, tuning)