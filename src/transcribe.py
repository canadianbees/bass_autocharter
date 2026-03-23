# transcribe.py
# Converts the isolated bass WAV into a MIDI file using aubio.
#
# Why aubio instead of basic-pitch:
#   basic-pitch is a general-purpose ML transcription model — it struggles with
#   bass guitar specifically because:
#     - repeated open strings produce nearly identical audio frames, confusing onset detection
#     - it hallucinates octave-3 notes from harmonics
#     - it generates 3-4x too many notes on sparse bass lines
#
#   aubio uses the YIN algorithm — a classical pitch detection method explicitly
#   designed for monophonic instruments. It handles low frequencies and repeated
#   notes much better than ML-based approaches for this use case.
#
# Pipeline:
#   1. Onset detection  — finds when each note starts (aubio onset detector)
#   2. Pitch detection  — finds what note is playing at each onset (aubio YIN)
#   3. Duration         — note ends at the next onset (or a cap of 4s)
#   4. MIDI output      — writes a standard .mid file via mido

import aubio
import numpy as np
import soundfile as sf
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

BASS_MIDI_MIN = 28    # E1  — lowest note on standard 4-string bass
BASS_MIDI_MAX = 55    # G3  — anything above is almost certainly an octave error
SILENCE_DB    = -40   # dB threshold below which a frame is considered silent
MIN_CONFIDENCE = 0.85 # YIN confidence required to accept a pitch reading
MIN_NOTE_SEC  = 0.08  # minimum note duration — filters ghost notes
HOP_SIZE      = 512   # audio frames per analysis window (~11ms at 44.1kHz)
WIN_SIZE      = 2048  # FFT window size


# ── MAIN ──────────────────────────────────────────────────────────────────────

def transcribe_bass(bass_wav_path: str, output_midi_path: str) -> list[tuple]:
    """
    Detects notes in the isolated bass WAV using aubio and writes a MIDI file.

    Returns a list of (start_sec, end_sec, midi_pitch) tuples.
    This is the format used throughout the rest of the pipeline.
    """
    print("    Running aubio pitch detection...")

    samples, sr = _load_mono(bass_wav_path)
    onsets      = _detect_onsets(samples, sr)
    notes       = _detect_pitches(samples, sr, onsets)
    notes       = _filter_notes(notes)

    print(f"    Detected {len(notes)} notes")

    _write_midi(notes, output_midi_path)
    print(f"    MIDI written to {output_midi_path}")

    return notes


# ── STEP 1: LOAD AUDIO ────────────────────────────────────────────────────────

def _load_mono(wav_path: str) -> tuple[np.ndarray, int]:
    """Load WAV as mono float32."""
    samples, sr = sf.read(wav_path, always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples.astype(np.float32), sr


# ── STEP 2: ONSET DETECTION ───────────────────────────────────────────────────

def _detect_onsets(samples: np.ndarray, sr: int) -> list[float]:
    """
    Find note onset times in seconds using aubio's onset detector.

    Uses the 'default' method (spectral flux + phase deviation) which works
    well for plucked string instruments. Returns a sorted list of onset times.
    """
    detector = aubio.onset("default", WIN_SIZE, HOP_SIZE, sr)
    detector.set_threshold(0.3)     # lower = more sensitive to quiet notes
    detector.set_silence(SILENCE_DB)
    detector.set_minioi_ms(60)      # minimum 60ms between onsets — prevents doubles

    onsets = []
    for i in range(0, len(samples) - HOP_SIZE, HOP_SIZE):
        frame = samples[i:i + HOP_SIZE]
        if detector(frame):
            t = detector.get_last_s()
            onsets.append(float(t))

    return sorted(set(onsets))


# ── STEP 3: PITCH DETECTION ───────────────────────────────────────────────────

def _detect_pitches(samples: np.ndarray, sr: int, onsets: list[float]) -> list[tuple]:
    """
    For each onset, measure the pitch of the audio in a window after that onset.

    Uses the YIN algorithm — specifically designed for monophonic pitched
    instruments. Samples pitch in the first 80ms after each onset (the attack
    has the clearest pitch) and takes the median for robustness.

    Returns list of (start_sec, end_sec, midi_pitch).
    """
    pitch_detector = aubio.pitch("yin", WIN_SIZE, HOP_SIZE, sr)
    pitch_detector.set_unit("midi")
    pitch_detector.set_silence(SILENCE_DB)
    pitch_detector.set_tolerance(0.8)  # higher = stricter pitch acceptance

    # Pre-compute pitch + confidence for every frame
    frame_pitches = []
    for i in range(0, len(samples) - HOP_SIZE, HOP_SIZE):
        frame      = samples[i:i + HOP_SIZE]
        pitch      = pitch_detector(frame)[0]
        confidence = pitch_detector.get_confidence()
        t          = i / sr
        frame_pitches.append((t, float(pitch), float(confidence)))

    notes = []
    for idx, onset_t in enumerate(onsets):
        # Duration: from this onset to the next onset
        end_t = onsets[idx + 1] if idx + 1 < len(onsets) else onset_t + 2.0

        # Sample pitch readings in the first 80ms after onset
        window_end    = onset_t + 0.08
        window_frames = [
            (p, c) for (t, p, c) in frame_pitches
            if onset_t <= t <= window_end and c >= MIN_CONFIDENCE
        ]

        if not window_frames:
            continue

        # Median pitch is more robust than mean against outlier frames
        pitches    = [p for p, c in window_frames]
        midi_pitch = round(float(np.median(pitches)))

        # Skip if outside bass range — postprocess will catch edge cases
        if not (BASS_MIDI_MIN <= midi_pitch <= BASS_MIDI_MAX):
            continue

        notes.append((onset_t, end_t, midi_pitch))

    return notes


# ── STEP 4: FILTER NOTES ──────────────────────────────────────────────────────

def _filter_notes(notes: list[tuple]) -> list[tuple]:
    """
    Remove notes too short to be intentional.
    Cap sustain at 4 seconds — prevents excessively long held notes
    from overlapping with the next note.
    """
    filtered = []
    for start, end, pitch in notes:
        if (end - start) < MIN_NOTE_SEC:
            continue
        end = min(end, start + 4.0)
        filtered.append((start, end, pitch))
    return filtered


# ── STEP 5: WRITE MIDI ────────────────────────────────────────────────────────

def _write_midi(notes: list[tuple], output_path: str):
    """
    Write notes to a standard MIDI file at 120 BPM.
    """
    TICKS_PER_BEAT = 480
    TEMPO          = 500000   # microseconds per beat = 120 BPM
    SEC_PER_TICK   = TEMPO / TICKS_PER_BEAT / 1e6

    def sec_to_tick(t: float) -> int:
        return int(round(t / SEC_PER_TICK))

    mid   = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    track = MidiTrack()
    mid.tracks.append(track)

    track.append(MetaMessage("set_tempo", tempo=TEMPO, time=0))
    track.append(MetaMessage("track_name", name="Bass", time=0))

    # Build flat event list then sort by tick
    events = []
    for start, end, pitch in notes:
        events.append((sec_to_tick(start), "note_on",  pitch, 100))
        events.append((sec_to_tick(end),   "note_off", pitch, 0))

    # note_off before note_on at same tick (prevents stuck notes)
    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

    last_tick = 0
    for tick, etype, pitch, velocity in events:
        delta = max(0, tick - last_tick)
        if etype == "note_on":
            track.append(Message("note_on",  note=pitch, velocity=velocity, time=delta))
        else:
            track.append(Message("note_off", note=pitch, velocity=0,        time=delta))
        last_tick = tick

    track.append(MetaMessage("end_of_track", time=0))
    mid.save(output_path)