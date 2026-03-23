# rs_xml.py

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import pretty_midi

from src.phrases import segment_phrases
from src.anchors import smooth_anchors
from src.difficulty import generate_levels


@dataclass
class RSNote:
    time: float
    string: int
    fret: int
    sustain: float
    hammer_on: bool = False
    pull_off: bool = False
    slide_to: int = -1
    vibrato: bool = False
    bend: float = 0.0
    bend_values: list[dict[str, Any]] = field(default_factory=list)


# ── MIDI → RS ──────────────────────────────────────────────────────────

def midi_to_rs_notes(midi, fretting):
    notes = midi.instruments[0].notes
    rs_notes = []

    for midi_note, (string_idx, fret) in zip(notes, fretting):
        rs_string = 3 - string_idx
        duration = midi_note.end - midi_note.start
        sustain = duration if duration > 0.1 else 0.0

        rs_notes.append(RSNote(
            time=midi_note.start,
            string=rs_string,
            fret=fret,
            sustain=sustain
        ))

    return sorted(rs_notes, key=lambda n: n.time)


# ── MAIN ───────────────────────────────────────────────────────────────

def generate_arrangement_xml(
    rs_notes,
    midi,
    song_name,
    artist,
    output_path,
    album_name="",
    album_year=0,
    arrangement="Bass"
):
    root = ET.Element("song")
    root.set("version", "8")

    song_length = max(midi.get_end_time(), max((n.time + n.sustain for n in rs_notes), default=0.0))
    timestamp = datetime.utcnow().strftime("%m-%d-%Y %H:%M")

    avg_tempo = _get_average_tempo(midi)
    internal_name = _make_internal_name(song_name, arrangement)

    # ── FULL METADATA (REQUIRED) ────────────────────────────────────────
    ET.SubElement(root, "title").text = song_name
    ET.SubElement(root, "arrangement").text = arrangement
    ET.SubElement(root, "part").text = "1"
    ET.SubElement(root, "offset").text = "0"
    ET.SubElement(root, "centOffset").text = "0"
    ET.SubElement(root, "songLength").text = f"{song_length:.3f}"
    ET.SubElement(root, "internalName").text = internal_name
    ET.SubElement(root, "songNameSort").text = song_name
    ET.SubElement(root, "startBeat").text = "0"
    ET.SubElement(root, "averageTempo").text = f"{avg_tempo:.3f}"
    ET.SubElement(root, "capo").text = "0"
    ET.SubElement(root, "artistName").text = artist
    ET.SubElement(root, "artistNameSort").text = artist
    ET.SubElement(root, "albumName").text = album_name
    ET.SubElement(root, "albumNameSort").text = album_name
    ET.SubElement(root, "albumYear").text = str(album_year if album_year else 0)
    ET.SubElement(root, "crowdSpeed").text = "1"
    ET.SubElement(root, "lastConversionDateTime").text = timestamp

    # ── REQUIRED CORE BLOCKS ───────────────────────────────────────────
    tuning = ET.SubElement(root, "tuning")
    for i in range(4):
        tuning.set(f"string{i}", "0")

    arr_props = ET.SubElement(root, "arrangementProperties")
    arr_props.set("pathBass", "1")
    arr_props.set("standardTuning", "1")
    arr_props.set("represent", "0")
    arr_props.set("sustain", "1")

    ET.SubElement(root, "tonebase").text = ""
    ET.SubElement(root, "tonea").text = ""
    ET.SubElement(root, "toneb").text = ""
    ET.SubElement(root, "tonec").text = ""
    ET.SubElement(root, "toned").text = ""
    ET.SubElement(root, "tone_multiplayer").text = ""
    ET.SubElement(root, "tones", count="0")

    ET.SubElement(root, "volume").text = "0.0"
    ET.SubElement(root, "previewVolume").text = "0.0"

    ET.SubElement(root, "chordTemplates", count="0")
    ET.SubElement(root, "fretHandMutes", count="0")

    # ── EBEATS ─────────────────────────────────────────────────────────
    ebeats = ET.SubElement(root, "ebeats")
    _generate_ebeats(ebeats, midi)
    bar_starts = [float(e.get("time")) for e in ebeats if e.get("measure") != "-1"]

    # ── PHRASES ───────────────────────────────────────────────────────
    phrase_times = segment_phrases(rs_notes, bar_starts)

    phrases = ET.SubElement(root, "phrases", count="1")
    ET.SubElement(phrases, "phrase", name="main", maxDifficulty="2")

    phrase_iters = ET.SubElement(root, "phraseIterations", count=str(len(phrase_times)))
    for t in phrase_times:
        ET.SubElement(phrase_iters, "phraseIteration", time=f"{t:.3f}", phraseId="0")

    props = ET.SubElement(root, "phraseProperties", count="1")
    ET.SubElement(props, "phraseProperty",
                  phraseId="0",
                  redundant="0",
                  levelJump="0",
                  empty="0")

    ET.SubElement(root, "newLinkedDiffs", count="0")
    ET.SubElement(root, "linkedDiffs", count="0")

    # ── SECTIONS ──────────────────────────────────────────────────────
    sections = ET.SubElement(root, "sections", count="2")
    ET.SubElement(sections, "section", name="intro", number="1", startTime="0.0")
    ET.SubElement(sections, "section", name="verse", number="1",
                  startTime=f"{phrase_times[1] if len(phrase_times)>1 else 5.0:.3f}")

    ET.SubElement(root, "events", count="0")
    ET.SubElement(root, "toneChanges", count="0")
    ET.SubElement(root, "controls", count="0")

    # ── LEVELS ────────────────────────────────────────────────────────
    levels_notes = generate_levels(rs_notes)
    levels = ET.SubElement(root, "levels", count=str(len(levels_notes)))

    for diff, notes in enumerate(levels_notes):
        level = ET.SubElement(levels, "level", difficulty=str(diff))

        notes_el = ET.SubElement(level, "notes", count=str(len(notes)))

        for n in notes:
            note = ET.SubElement(notes_el, "note")
            note.set("time", f"{n.time:.3f}")
            note.set("string", str(n.string))
            note.set("fret", str(n.fret))
            note.set("sustain", f"{n.sustain:.3f}")

        ET.SubElement(level, "chords", count="0")

        anchors_data = smooth_anchors(notes)
        anchors = ET.SubElement(level, "anchors", count=str(len(anchors_data)))

        for t, f in anchors_data:
            ET.SubElement(anchors, "anchor", time=f"{t:.3f}", fret=str(f), width="4")

        ET.SubElement(level, "anchorExtensions", count="0")
        ET.SubElement(level, "handShapes", count="0")
        ET.SubElement(level, "fingerprints", count="0")

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


# ── HELPERS ────────────────────────────────────────────────────────────

def _generate_ebeats(ebeats_element, midi):
    tempo_times, tempos = midi.get_tempo_changes()

    if not tempos:
        tempos = [120]
        tempo_times = [0]

    beat = 0
    measure = 1

    for i, tempo in enumerate(tempos):
        start = tempo_times[i]
        end = tempo_times[i+1] if i+1 < len(tempos) else midi.get_end_time()
        dur = 60 / tempo

        t = start
        while t < end:
            down = (beat % 4 == 0)
            ET.SubElement(
                ebeats_element,
                "ebeat",
                time=f"{t:.3f}",
                measure=str(measure) if down else "-1"
            )
            if down:
                measure += 1
            t += dur
            beat += 1


def _get_average_tempo(midi):
    _, tempos = midi.get_tempo_changes()
    return float(sum(tempos) / len(tempos)) if tempos.size else 120.0


def _make_internal_name(song_name, arrangement):
    safe = "".join(c for c in song_name if c.isalnum())
    return f"{safe}_{arrangement.lower()}"