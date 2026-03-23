# transcribe.py
# Converts the isolated bass WAV into a MIDI file using basic-pitch.
# basic-pitch is Spotify's open-source pitch detection model — it analyzes
# the audio frame by frame and outputs note onset times, pitches, and durations.

from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
import pretty_midi


def transcribe_bass(bass_wav_path: str, output_midi_path: str) -> pretty_midi.PrettyMIDI:
    """
    Runs basic-pitch on the isolated bass WAV and writes a MIDI file.

    The thresholds are tuned for bass guitar:
      - onset_threshold:      how confident basic-pitch must be that a note started
      - frame_threshold:      how confident it must be that a note is still playing
      - minimum_note_length:  filters out very short notes (likely noise)
      - minimum_frequency:    bass E string is ~41Hz, so we ignore anything below 30Hz
      - maximum_frequency:    highest practical bass note is well below 300Hz

    Returns a pretty_midi.PrettyMIDI object containing the detected notes.
    """
    print("    Running basic-pitch — this takes about 30-60 seconds...")

    model_output, midi_data, note_events = predict(
        bass_wav_path,
        ICASSP_2022_MODEL_PATH,
        onset_threshold=0.5,     # higher = fewer false positives
        frame_threshold=0.3,     # lower = catches more sustained notes
        minimum_note_length=58,  # milliseconds — filters out noise hits
        minimum_frequency=30,    # Hz — below open E string, ignore it
        maximum_frequency=300,   # Hz — well above highest bass note
    )

    midi_data.write(output_midi_path)
    print(f"    MIDI written to {output_midi_path}")

    num_notes = len(midi_data.instruments[0].notes) if midi_data.instruments else 0
    print(f"    Detected {num_notes} notes")

    return midi_data