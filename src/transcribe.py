# transcribe.py
# Converts an isolated bass WAV file into a list of (start_sec, end_sec, midi_pitch) tuples.
#
# ── APPROACH ──────────────────────────────────────────────────────────────────
#
# Previous approach (onset detection) — why it failed:
#   aubio's onset detector works by looking for sudden changes in the audio spectrum.
#   Repeated notes at the same pitch (e.g. 0 0 0 0 0 on the E string) produce
#   almost no spectral change between them, so the detector misses most of them.
#   This is a fundamental limitation, not a tuning problem.
#
# New approach (beat grid sampling) — why it works:
#   Instead of looking for spectral changes, we:
#     1. Detect the song's BPM using librosa
#     2. Generate a grid of expected note positions (every 16th note)
#     3. At each grid position, check if the bass is actually playing (RMS energy)
#     4. If it is, detect the pitch using aubio's YIN algorithm
#
#   This mirrors what a human transcriber does — they know the tempo and check
#   each beat subdivision rather than hunting for spectral changes.
#   Repeated notes are no longer a problem because we're sampling at regular
#   intervals regardless of whether the spectrum changes.
#
# ── OUTPUT FORMAT ─────────────────────────────────────────────────────────────
#   list of (start_sec, end_sec, midi_pitch) tuples
#   This is the same format used by postprocess.py and rs_xml.py — no changes
#   needed downstream.

import numpy as np
import librosa
import aubio
import soundfile as sf
import mido
from mido import MidiFile, MidiTrack, Message, MetaMessage


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

# Bass range: E1 (open low string) to Bb2 (reasonable upper limit for most songs)
# Keeping this conservative avoids octave errors from harmonics
BASS_MIDI_MIN = 28   # E1  — open low E string
BASS_MIDI_MAX = 46   # Bb2 — conservative upper limit

# Energy threshold: how loud a grid slot needs to be to count as a note
# Too high = missed notes in quiet passages
# Too low  = phantom notes during rests
# 0.01 is a good starting point for Demucs-separated bass stems
ENERGY_THRESHOLD = 0.01

# YIN pitch detection settings
YIN_CONFIDENCE_THRESHOLD = 0.75  # minimum confidence to accept a pitch reading
YIN_SILENCE_DB           = -60   # frames quieter than this are ignored
YIN_TOLERANCE            = 0.8   # how strict YIN is about pitch stability

# Analysis window: how many audio samples to analyze around each grid position
# 2048 samples at 44100 Hz = ~46ms window — enough to get a stable pitch reading
ANALYSIS_WINDOW_SAMPLES = 2048
HOP_SIZE_SAMPLES        = 512    # step size between YIN analysis frames


# ── MAIN FUNCTION ─────────────────────────────────────────────────────────────

def transcribe_bass(bass_wav_path: str, output_midi_path: str,
                    full_mix_path: str = None) -> list[tuple]:
    """
    full_mix_path: if provided, use the full mix for beat detection
                   (more accurate than detecting beats from bass stem alone)
    """
    print("    Loading audio...")
    bass_samples, sample_rate = _load_mono_audio(bass_wav_path)

    # Use full mix for beat detection if available — much more accurate
    beat_source = full_mix_path if full_mix_path else bass_wav_path
    print("    Detecting BPM and beat grid...")
    beat_audio, beat_sr = _load_mono_audio(beat_source)
    bpm, grid_times = _build_note_grid(beat_audio, beat_sr)
    print(f"    Detected BPM: {bpm:.1f} — {len(grid_times)} grid slots")

    print("    Sampling pitch at each grid position...")
    notes = _sample_pitches_on_grid(bass_samples, sample_rate, grid_times)
    print(f"    Detected {len(notes)} notes")

    _write_midi(notes, output_midi_path, bpm)
    return notes


# ── STEP 1: LOAD AUDIO ────────────────────────────────────────────────────────

def _load_mono_audio(wav_path: str) -> tuple[np.ndarray, int]:
    """
    Load a WAV file as a mono float32 numpy array.

    If the file is stereo, average the two channels into one.
    aubio and librosa both require mono float32 input.
    """
    audio_samples, sample_rate = sf.read(wav_path, always_2d=False)

    if audio_samples.ndim > 1:
        # Stereo → average left and right channels to get mono
        audio_samples = audio_samples.mean(axis=1)

    return audio_samples.astype(np.float32), sample_rate


# ── STEP 2: BUILD NOTE GRID ───────────────────────────────────────────────────

def _build_note_grid(audio_samples: np.ndarray, sample_rate: int) -> tuple[float, list[float]]:
    """
    Detect the song's BPM and generate a grid of 16th-note positions.

    librosa's beat_track() returns:
      - bpm: the estimated tempo in beats per minute
      - beat_frames: frame indices of each detected beat (quarter notes)

    We then subdivide each beat into 4 equal parts to get 16th note positions.
    This gives us the grid we'll sample pitches on.

    Returns (bpm, list_of_grid_times_in_seconds).
    """
    # librosa works with float32 audio normalized to [-1, 1]
    bpm, beat_frames = librosa.beat.beat_track(
        y=audio_samples,
        sr=sample_rate,
        units="frames",
        hop_length=HOP_SIZE_SAMPLES,
        tightness=100,   # higher = beats more evenly spaced (good for electronic music)
    )

    # Convert beat frame indices to time in seconds
    beat_times = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=HOP_SIZE_SAMPLES,
    )

    # Subdivide each beat (quarter note) into 4 equal parts (16th notes)
    # For each pair of adjacent beats, insert 3 evenly spaced points between them
    grid_times = []
    for i in range(len(beat_times) - 1):
        beat_start    = beat_times[i]
        beat_end      = beat_times[i + 1]
        sixteenth_dur = (beat_end - beat_start) / 4

        for subdivision in range(4):
            grid_time = beat_start + subdivision * sixteenth_dur
            grid_times.append(grid_time)

    # Add the last beat position itself
    if len(beat_times) > 0:
        grid_times.append(beat_times[-1])

    return float(bpm), sorted(grid_times)


# ── STEP 3: SAMPLE PITCHES ON GRID ───────────────────────────────────────────

def _sample_pitches_on_grid(
    audio_samples: np.ndarray,
    sample_rate:   int,
    grid_times:    list[float],
) -> list[tuple]:
    """
    At each grid position, check if the bass is playing and detect the pitch.

    For each grid slot:
      1. Extract a short window of audio centered on that time
      2. Check the RMS energy — if too quiet, skip (no note playing)
      3. Run YIN pitch detection on the window
      4. If confidence is high enough and pitch is in bass range, record the note

    Note duration is set as the distance to the next grid slot, capped at 2 seconds.

    Returns list of (start_sec, end_sec, midi_pitch).
    """
    # Set up aubio YIN pitch detector
    pitch_detector = aubio.pitch("yin", ANALYSIS_WINDOW_SAMPLES, HOP_SIZE_SAMPLES, sample_rate)
    pitch_detector.set_unit("midi")
    pitch_detector.set_silence(YIN_SILENCE_DB)
    pitch_detector.set_tolerance(YIN_TOLERANCE)

    notes = []

    for slot_index, grid_time in enumerate(grid_times):

        # ── 1. Extract audio window around this grid position ─────────────────
        center_sample = int(grid_time * sample_rate)
        window_start  = max(0, center_sample)
        window_end    = min(len(audio_samples), window_start + ANALYSIS_WINDOW_SAMPLES)
        audio_window  = audio_samples[window_start:window_end]

        # Pad with zeros if we're near the end of the file
        if len(audio_window) < ANALYSIS_WINDOW_SAMPLES:
            audio_window = np.pad(audio_window, (0, ANALYSIS_WINDOW_SAMPLES - len(audio_window)))

        # ── 2. Check energy — skip silent slots ───────────────────────────────
        rms_energy = float(np.sqrt(np.mean(audio_window ** 2)))
        if rms_energy < ENERGY_THRESHOLD:
            continue

        # ── 3. Detect pitch using YIN ─────────────────────────────────────────
        # aubio expects exactly HOP_SIZE_SAMPLES per call.
        # Run it over multiple chunks of the window and take the median pitch
        # for robustness against noisy individual frames.
        pitch_readings = []
        for chunk_start in range(0, ANALYSIS_WINDOW_SAMPLES - HOP_SIZE_SAMPLES, HOP_SIZE_SAMPLES):
            chunk      = audio_window[chunk_start:chunk_start + HOP_SIZE_SAMPLES].astype(np.float32)
            chunk_pitch      = pitch_detector(chunk)[0]
            chunk_confidence = pitch_detector.get_confidence()
            if chunk_confidence >= YIN_CONFIDENCE_THRESHOLD and chunk_pitch > 0:
                pitch_readings.append(chunk_pitch)

        if not pitch_readings:
            continue  # no confident pitch readings in this window

        detected_pitch_midi = float(np.median(pitch_readings))

        midi_pitch = round(float(detected_pitch_midi))

        if not (BASS_MIDI_MIN <= midi_pitch <= BASS_MIDI_MAX):
            continue  # Outside bass range — almost certainly a harmonic or noise

        # ── 5. Set note duration ──────────────────────────────────────────────
        # Note ends at the next grid slot, capped at 2 seconds
        if slot_index + 1 < len(grid_times):
            note_end = grid_times[slot_index + 1]
        else:
            note_end = grid_time + 0.5

        note_end = min(note_end, grid_time + 2.0)  # cap at 2 seconds

        notes.append((grid_time, note_end, midi_pitch))

    return notes


# ── STEP 4: WRITE MIDI ────────────────────────────────────────────────────────

def _write_midi(notes: list[tuple], output_path: str, bpm: float):
    """
    Write the detected notes to a standard MIDI file.

    Uses the detected BPM for the tempo so the MIDI grid matches the song tempo.
    This makes the MIDI easier to inspect in a DAW and improves RS2014 sync.
    """
    ticks_per_beat = 480
    tempo_microseconds = int(60_000_000 / bpm)  # microseconds per beat

    # How long one tick is in seconds
    seconds_per_tick = tempo_microseconds / ticks_per_beat / 1_000_000

    def seconds_to_ticks(time_seconds: float) -> int:
        return int(round(time_seconds / seconds_per_tick))

    midi_file  = MidiFile(ticks_per_beat=ticks_per_beat)
    midi_track = MidiTrack()
    midi_file.tracks.append(midi_track)

    # Write tempo and track name metadata
    midi_track.append(MetaMessage("set_tempo", tempo=tempo_microseconds, time=0))
    midi_track.append(MetaMessage("track_name", name="Bass", time=0))

    # Build a flat list of (tick, event_type, pitch, velocity) and sort by tick
    # note_off events sort before note_on at the same tick to prevent stuck notes
    all_events = []
    for start_sec, end_sec, midi_pitch in notes:
        all_events.append((seconds_to_ticks(start_sec), "note_on",  midi_pitch, 100))
        all_events.append((seconds_to_ticks(end_sec),   "note_off", midi_pitch, 0))

    all_events.sort(key=lambda event: (event[0], 0 if event[1] == "note_off" else 1))

    # Write delta-time MIDI messages
    last_tick = 0
    for tick, event_type, pitch, velocity in all_events:
        delta_ticks = max(0, tick - last_tick)
        if event_type == "note_on":
            midi_track.append(Message("note_on",  note=pitch, velocity=velocity, time=delta_ticks))
        else:
            midi_track.append(Message("note_off", note=pitch, velocity=0,        time=delta_ticks))
        last_tick = tick

    midi_track.append(MetaMessage("end_of_track", time=0))
    midi_file.save(output_path)