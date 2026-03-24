# validate.py
# Compares your generated MIDI against a reference MIDI (e.g. from Songsterr)
# and reports precision, recall, and F1 score.
#
# Run after any pipeline change to see if accuracy improved or degraded:
#   python -m tests.validate
#
# Metrics:
#   Precision = of all notes you generated, what % are correct
#   Recall    = of all real notes, what % did you find
#   F1        = combined score (harmonic mean of precision and recall)

from collections import Counter
import mido

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Your generated MIDI (output of the pipeline)
GENERATED_MIDI = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_output\bass.mid"

# Reference MIDI (from Songsterr, Guitar Pro, or a DAW)
REFERENCE_MIDI = r"C:\Users\Celina Alzenor\Desktop\Projects\bass_autocharter\test_input\Ariana_Grande-_don_t_wanna_break_up_again___A_MAJOR_-05-16-2025.mid"

# Which track in the reference MIDI is the bass? (None = auto-detect)
REFERENCE_TRACK = 2

# How many milliseconds of timing error is acceptable for a match
TIMING_TOLERANCE_MS = 150

# ── END CONFIG ────────────────────────────────────────────────────────────────


_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
def _note_name(pitch: int) -> str:
    return f"{_NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _build_tempo_map(track) -> list:
    tempo_map    = []
    current_tick = 0
    for msg in track:
        current_tick += msg.time
        if msg.type == 'set_tempo':
            tempo_map.append((current_tick, msg.tempo))
    if not tempo_map:
        tempo_map = [(0, 500000)]
    return tempo_map


def _ticks_to_seconds(ticks, ticks_per_beat, tempo_map) -> float:
    seconds    = 0.0
    prev_tick  = 0
    prev_tempo = 500000
    for change_tick, tempo in tempo_map:
        if ticks <= change_tick:
            break
        seconds   += (change_tick - prev_tick) / ticks_per_beat * prev_tempo / 1_000_000
        prev_tick  = change_tick
        prev_tempo = tempo
    seconds += (ticks - prev_tick) / ticks_per_beat * prev_tempo / 1_000_000
    return seconds


def _extract_notes(mid, track_index) -> list:
    tempo_map    = _build_tempo_map(mid.tracks[0])
    notes        = []
    current_tick = 0
    active       = {}
    for msg in mid.tracks[track_index]:
        current_tick += msg.time
        if msg.type == 'note_on' and msg.velocity > 0:
            active[msg.note] = current_tick
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in active:
                s = _ticks_to_seconds(active.pop(msg.note), mid.ticks_per_beat, tempo_map)
                e = _ticks_to_seconds(current_tick, mid.ticks_per_beat, tempo_map)
                notes.append((s, e, msg.note))
    return sorted(notes)


def _auto_detect_bass_track(mid) -> int:
    best_track       = 1
    lowest_avg_pitch = float('inf')
    for i in range(1, len(mid.tracks)):
        notes = _extract_notes(mid, i)
        if len(notes) < 10:
            continue
        avg = sum(p for s, e, p in notes) / len(notes)
        if avg < lowest_avg_pitch:
            lowest_avg_pitch = avg
            best_track       = i
    return best_track


def compare(generated, reference, tolerance) -> dict:
    """
    Compare generated notes against reference notes.
    A match requires exact pitch and onset within `tolerance` seconds.
    """
    matched_gen = set()
    matched_ref = set()

    for gi, (gs, ge, gp) in enumerate(generated):
        for ri, (rs, re, rp) in enumerate(reference):
            if ri in matched_ref:
                continue
            if gp == rp and abs(gs - rs) <= tolerance:
                matched_gen.add(gi)
                matched_ref.add(ri)
                break

    tp = len(matched_gen)
    fp = len(generated) - tp
    fn = len(reference)  - len(matched_ref)

    precision = tp / len(generated) if generated else 0.0
    recall    = tp / len(reference)  if reference  else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "true_positives":  tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision":       precision,
        "recall":          recall,
        "f1":              f1,
        "missed":   [(s,e,p) for i,(s,e,p) in enumerate(reference)  if i not in matched_ref],
        "invented": [(s,e,p) for i,(s,e,p) in enumerate(generated) if i not in matched_gen],
    }


if __name__ == "__main__":
    tolerance_sec = TIMING_TOLERANCE_MS / 1000

    # Load reference
    ref_mid   = mido.MidiFile(REFERENCE_MIDI)
    ref_track = REFERENCE_TRACK if REFERENCE_TRACK is not None else _auto_detect_bass_track(ref_mid)
    ref_notes = _extract_notes(ref_mid, ref_track)

    # Load generated
    gen_mid   = mido.MidiFile(GENERATED_MIDI)
    gen_notes = _extract_notes(gen_mid, 0)

    print(f"Reference:  {len(ref_notes)} notes  "
          f"({ref_notes[0][0]:.1f}s — {ref_notes[-1][1]:.1f}s)  [track {ref_track}]")
    print(f"Generated:  {len(gen_notes)} notes  "
          f"({gen_notes[0][0]:.1f}s — {gen_notes[-1][1]:.1f}s)")
    print()

    # Accuracy at multiple tolerances
    print("Accuracy at different timing tolerances:")
    print(f"  {'Tolerance':>10}  {'TP':>5}  {'FP':>5}  {'FN':>5}  "
          f"{'Precision':>10}  {'Recall':>8}  {'F1':>8}")
    print(f"  {'-'*68}")
    for tol_ms in [50, 100, 150, 200, 300, 500]:
        r      = compare(gen_notes, ref_notes, tol_ms / 1000)
        marker = " ◄" if tol_ms == TIMING_TOLERANCE_MS else ""
        print(f"  {tol_ms:>8}ms  {r['true_positives']:>5}  "
              f"{r['false_positives']:>5}  {r['false_negatives']:>5}  "
              f"{r['precision']:>10.1%}  {r['recall']:>8.1%}  "
              f"{r['f1']:>8.1%}{marker}")

    # Detailed at chosen tolerance
    print()
    result = compare(gen_notes, ref_notes, tolerance_sec)
    print(f"Detailed breakdown at {TIMING_TOLERANCE_MS}ms:")
    print(f"  Precision:  {result['precision']:.1%}  "
          f"({result['true_positives']} of your {len(gen_notes)} notes are correct)")
    print(f"  Recall:     {result['recall']:.1%}  "
          f"({result['true_positives']} of {len(ref_notes)} real notes found)")
    print(f"  F1 Score:   {result['f1']:.1%}")

    print()
    print("Notes you missed (false negatives):")
    for pitch, count in sorted(Counter(p for s,e,p in result['missed']).items()):
        print(f"  {pitch:3} ({_note_name(pitch):4}): {count}x")

    print()
    print("Notes you invented (false positives):")
    for pitch, count in sorted(Counter(p for s,e,p in result['invented']).items()):
        print(f"  {pitch:3} ({_note_name(pitch):4}): {count}x")

    # Bar-by-bar breakdown
    print()
    print("Bar-by-bar accuracy (97 BPM):")
    BAR_DUR = 60 / 97 * 4
    print(f"  {'Bar':>4}  {'Time':>7}  {'Ref':>4}  {'Gen':>4}  {'TP':>4}  Status")
    print(f"  {'-'*48}")
    for bar in range(70):
        bar_start = bar * BAR_DUR
        bar_end   = bar_start + BAR_DUR
        bar_ref   = [(s,e,p) for s,e,p in ref_notes if bar_start <= s < bar_end]
        bar_gen   = [(s,e,p) for s,e,p in gen_notes if bar_start <= s < bar_end]
        if not bar_ref and not bar_gen:
            continue
        r  = compare(bar_gen, bar_ref, tolerance_sec)
        tp = r['true_positives']
        if not bar_ref:
            status = "── no bass"
        elif tp == len(bar_ref):
            status = "✓ perfect"
        elif tp >= len(bar_ref) * 0.75:
            status = "~ mostly correct"
        elif tp >= len(bar_ref) * 0.5:
            status = "△ partial"
        else:
            status = "✗ poor"
        print(f"  {bar+1:>4}  {bar_start:>5.1f}s  "
              f"{len(bar_ref):>4}  {len(bar_gen):>4}  {tp:>4}  {status}")