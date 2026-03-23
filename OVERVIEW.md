# Bass Auto-Charter — Project Overview

A CLI tool that takes a song (YouTube URL or local file) and automatically
generates a playable Rocksmith 2014 bass arrangement (.psarc).

---

## How the pipeline works

```
YouTube URL or local file
        ↓
   src/download.py        — downloads audio from YouTube as MP3
        ↓
   src/separate.py        — isolates the bass track from the full mix
        ↓
   src/transcribe.py      — converts the bass audio to MIDI notes
        ↓
   src/postprocess.py     — cleans up transcription errors
        ↓
   src/fretting.py        — maps MIDI pitches to string/fret positions
        ↓
   src/techniques.py      — detects hammer-ons, pull-offs, slides, bends, vibrato
        ↓
   src/rs_xml.py          — generates Rocksmith 2014 arrangement XML
        ↓
   src/package.py         — packages everything into a .psarc file
        ↓
   song.psarc  →  drop into Rocksmith 2014 /dlc/ folder and play
```

---

## File by file

### main.py
The entry point. Parses CLI arguments and runs each pipeline stage in order.
This is the only file you need to run directly.

```bash
python main.py "https://youtube.com/watch?v=..." --artist "Queen" --toolkit "path/to/toolkit"
```

---

### src/download.py
Downloads audio from a URL (YouTube, SoundCloud, etc.) using yt-dlp and
converts it to a 320kbps MP3 using FFmpeg.

If the input is a local file path rather than a URL, this stage is skipped.

Key function: `download_audio(url, output_dir) -> (mp3_path, song_title)`

---

### src/separate.py
Takes the full song MP3 and isolates just the bass track using Demucs —
a source separation model from Meta Research.

Demucs splits the audio into stems (bass, drums, vocals, other). We only
keep the bass stem and discard the rest.

Also validates that the bass stem is not silent (which would mean the song
has no detectable bass track).

Key function: `separate_bass(input_path, output_dir) -> bass_wav_path`

---

### src/transcribe.py
Takes the isolated bass WAV and converts it to a MIDI file using
basic-pitch — Spotify's open-source pitch detection model.

basic-pitch analyzes the audio frame by frame and outputs:
  - note onset times (when each note starts)
  - MIDI pitches (what note is being played)
  - note durations (how long each note lasts)

Key function: `transcribe_bass(bass_wav, output_midi) -> pretty_midi.PrettyMIDI`

---

### src/postprocess.py
Cleans up common errors in the basic-pitch transcription before fretting.

Problems it fixes:
  - Octave errors: notes detected an octave too high/low get shifted back
  - Noise hits: very short notes (< 50ms) that are likely artifacts get removed
  - Duplicate notes: consecutive same-pitch notes with tiny gaps get merged
  - Note density: enforces a minimum 80ms gap between notes so the game
    doesn't lag from too many notes per second
  - Slides: detects rapid semitone runs and collapses them into a single
    note with a slideTo destination (used later in techniques.py)

Key function: `postprocess_midi(midi) -> pretty_midi.PrettyMIDI`

---

### src/fretting.py
**The most algorithmically interesting file.**

Takes a list of MIDI pitches and figures out the best (string, fret)
position for each note on a physical bass guitar.

The challenge: any given pitch can be played in multiple places on the neck.
The goal is to find the sequence of positions that minimizes total hand
movement across the whole song.

How it works:
  1. `get_fret_positions(pitch)` — returns every valid (string, fret) pair
     for a given MIDI pitch on the given tuning
  2. `hand_movement_cost(pos_a, pos_b)` — estimates how hard it is to move
     between two positions (fret distance + string change penalty)
  3. `_find_lowest_cost_path(pitches)` — Viterbi dynamic programming
     algorithm that finds the minimum-cost path through all note positions
  4. `find_optimal_fretting(pitches)` — public function that filters out
     unplayable notes and calls the path finder

Supports multiple tunings: standard, drop D, Eb, D standard.

Key function: `find_optimal_fretting(midi_pitches, tuning) -> list[(string, fret)]`

---

### src/techniques.py
Detects playing techniques from the note timing and pitch data and annotates
each note with the appropriate RS2014 technique flags.

Techniques detected:
  - **Hammer-ons**: two notes on the same string, close together, ascending pitch
  - **Pull-offs**: two notes on the same string, close together, descending pitch
  - **Slides**: rapid semitone run between two positions → slideTo attribute
  - **Vibrato**: sustained note followed by rapid pitch wobble cluster
  - **Bends**: pitch rise within a single note's duration → bendValues XML elements

Techniques NOT detected (require timbre analysis, out of scope):
  - Palm mutes
  - Slap / pop

Key functions:
  - `detect_hopo(rs_notes) -> rs_notes`
  - `detect_slides(midi_notes, fretting) -> (midi_notes, fretting)`
  - `detect_vibrato(rs_notes, raw_midi_notes) -> rs_notes`
  - `detect_bends(rs_notes, note_events) -> rs_notes`

---

### src/rs_xml.py
Converts the fretting solution and technique annotations into a valid
Rocksmith 2014 arrangement XML file.

RS2014 arrangement XML contains:
  - Song metadata (title, artist, tuning)
  - Ebeats: the tempo map — one entry per beat, used to sync notes to audio
  - Notes: each note with time, string, fret, sustain, and technique attributes
  - Bend values: child elements on bend notes with timestamped pitch steps

The XML format was reverse-engineered by the Rocksmith modding community
and is documented in the rocksmith-custom-song-toolkit source.

Key function: `generate_arrangement_xml(rs_notes, midi, song_name, artist, output_path)`

---

### src/package.py
Calls the Rocksmith Custom Song Toolkit CLI to package the arrangement XML
and audio file into a .psarc file that Rocksmith 2014 can load.

The toolkit handles:
  - Converting WAV audio to the .wem format Rocksmith uses (requires Wwise)
  - Compiling the arrangement XML into a binary .sng file
  - Generating manifest and metadata files
  - Encrypting and packaging everything into the final .psarc archive

Key function: `package_psarc(arrangement_xml, audio_wav, song_name, artist, output_dir, toolkit_path) -> psarc_path`

---

## Data flow summary

| Stage | Input | Output | Format |
|---|---|---|---|
| download | YouTube URL | audio file | .mp3 |
| separate | full mix | bass only | .wav |
| transcribe | bass audio | note events | .mid |
| postprocess | raw MIDI | cleaned MIDI | pretty_midi object |
| fretting | MIDI pitches | fret positions | list of (string, fret) |
| techniques | RS notes | annotated notes | list of RSNote |
| rs_xml | RS notes + MIDI | arrangement | .xml |
| package | XML + audio | playable file | .psarc |

---

## Key dependencies

| Library | What it does | Stage |
|---|---|---|
| yt-dlp | Downloads audio from YouTube | download |
| demucs | ML model: separates bass from mix | separate |
| basic-pitch | ML model: audio → MIDI notes | transcribe |
| pretty_midi | Read/write MIDI files | transcribe, postprocess |
| librosa | Audio analysis (RMS check) | separate |
| soundfile | Read/write WAV files | transcribe |
| mido | Low-level MIDI parsing | rs_xml |
| RS Toolkit CLI | Packages .psarc (external binary) | package |

---

## Tests

```
tests/
  test_fretting.py     — unit tests for the Viterbi fretting algorithm
  test_transcribe.py   — synthetic sine wave test for basic-pitch
  test_rs_xml.py       — XML structure validation
  test_techniques.py   — unit tests for HO/PO and slide detection
  test_download.py     — smoke test for yt-dlp (marked integration, skipped in CI)
  benchmark.py         — regression benchmark against known-good CustomsForge charts
```

Run all unit tests:
```bash
pytest tests/ -v -m "not integration"
```

Run everything including download test:
```bash
pytest tests/ -v
```
