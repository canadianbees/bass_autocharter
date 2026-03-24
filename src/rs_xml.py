# rs_xml.py

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.phrases import segment_phrases
from src.anchors import smooth_anchors
from src.difficulty import generate_levels


# ── NOTE DATACLASS ────────────────────────────────────────────────────────────

@dataclass
class RSNote:
    time:        float
    string:      int
    fret:        int
    sustain:     float
    hammer_on:   bool  = False
    pull_off:    bool  = False
    slide_to:    int   = -1
    vibrato:     bool  = False
    bend:        float = 0.0
    bend_values: list[dict[str, Any]] = field(default_factory=list)


# ── CONVERSION ────────────────────────────────────────────────────────────────

def notes_to_rs(
    note_tuples: list[tuple],
    fretting:    list[tuple],
) -> list[RSNote]:
    if len(note_tuples) != len(fretting):
        raise ValueError(
            f"notes_to_rs: length mismatch — "
            f"{len(note_tuples)} notes vs {len(fretting)} fretting entries. "
            "Use filter_notes_to_fretting() to keep them in sync."
        )

    rs_notes = []
    for (start, end, pitch), (string_idx, fret) in zip(note_tuples, fretting):
        rs_string = string_idx  # RS bass: 0=E(low), 1=A, 2=D, 3=G — same as GP
        duration  = end - start
        sustain   = duration if duration > 0.1 else 0.0

        rs_notes.append(RSNote(
            time    = start,
            string  = rs_string,
            fret    = fret,
            sustain = sustain,
        ))

    return sorted(rs_notes, key=lambda n: n.time)


# ── MAIN XML GENERATOR ────────────────────────────────────────────────────────

def generate_arrangement_xml(
    rs_notes:    list[RSNote],
    song_length: float,
    avg_tempo:   float,
    song_name:   str,
    artist:      str,
    output_path: str,
    album_name:  str = "",
    album_year:  int = 0,
    arrangement: str = "Bass",
):
    root      = ET.Element("song")
    root.set("version", "8")
    timestamp = datetime.utcnow().strftime("%m-%d-%Y %H:%M")
    internal  = _make_internal_name(song_name, arrangement)

    ET.SubElement(root, "title").text          = song_name
    ET.SubElement(root, "arrangement").text    = arrangement
    ET.SubElement(root, "part").text           = "1"
    ET.SubElement(root, "offset").text         = "0.000"
    ET.SubElement(root, "centOffset").text     = "0"
    ET.SubElement(root, "songLength").text     = f"{song_length:.3f}"
    ET.SubElement(root, "internalName").text   = internal
    ET.SubElement(root, "songNameSort").text   = song_name
    ET.SubElement(root, "startBeat").text      = "0.000"
    ET.SubElement(root, "averageTempo").text   = f"{avg_tempo:.3f}"
    ET.SubElement(root, "capo").text           = "0"
    ET.SubElement(root, "artistName").text     = artist
    ET.SubElement(root, "artistNameSort").text = artist
    ET.SubElement(root, "albumName").text      = album_name
    ET.SubElement(root, "albumNameSort").text  = album_name
    ET.SubElement(root, "albumYear").text      = str(album_year)
    ET.SubElement(root, "crowdSpeed").text     = "1"
    ET.SubElement(root, "lastConversionDateTime").text = timestamp

    tuning = ET.SubElement(root, "tuning")
    for i in range(4):
        tuning.set(f"string{i}", "0")

    arr_props = ET.SubElement(root, "arrangementProperties")
    arr_props.set("pathBass",       "1")
    arr_props.set("standardTuning", "1")
    arr_props.set("represent",      "0")
    arr_props.set("sustain",        "1")

    for t in ("tonebase", "tonea", "toneb", "tonec", "toned", "tone_multiplayer"):
        ET.SubElement(root, t).text = ""
    ET.SubElement(root, "tones", count="0")

    ET.SubElement(root, "volume").text        = "0.0"
    ET.SubElement(root, "previewVolume").text = "0.0"

    ET.SubElement(root, "chordTemplates", count="0")
    ET.SubElement(root, "fretHandMutes",  count="0")

    # Ebeats
    ebeats_el  = ET.SubElement(root, "ebeats")
    bar_starts = _generate_ebeats(ebeats_el, song_length, avg_tempo)

    # Phrases — COUNT, one per segment, END
    phrase_times = segment_phrases(rs_notes, bar_starts)
    first_note   = rs_notes[0].time if rs_notes else 0.0

    # Ensure no phrase starts at 0 (that's COUNT's slot) — shift to first note
    phrase_times = [t if t > 0 else first_note for t in phrase_times]
    phrase_times = sorted(set(phrase_times))

    # phrase 0 = COUNT, 1..N = main segments, last = END
    n_main = len(phrase_times)
    phrases_el = ET.SubElement(root, "phrases", count=str(n_main + 2))
    ET.SubElement(phrases_el, "phrase", name="COUNT", maxDifficulty="0", disparity="0", ignore="0")
    for _ in phrase_times:
        ET.SubElement(phrases_el, "phrase", name="main", maxDifficulty="0", disparity="0", ignore="0")
    ET.SubElement(phrases_el, "phrase", name="END", maxDifficulty="0", disparity="0", ignore="0")

    end_phrase_id = str(n_main + 1)
    iters_el = ET.SubElement(root, "phraseIterations", count=str(n_main + 2))
    ET.SubElement(iters_el, "phraseIteration", time="0.000", phraseId="0", variation="")
    for i, t in enumerate(phrase_times):
        ET.SubElement(iters_el, "phraseIteration",
                      time=f"{t:.3f}", phraseId=str(i + 1), variation="")
    ET.SubElement(iters_el, "phraseIteration",
                  time=f"{song_length - 0.5:.3f}", phraseId=end_phrase_id, variation="")

    ET.SubElement(root, "phraseProperties", count="0")
    ET.SubElement(root, "newLinkedDiffs",   count="0")
    ET.SubElement(root, "linkedDiffs",      count="0")
    ET.SubElement(root, "sections",         count="0")
    ET.SubElement(root, "events",           count="0")
    ET.SubElement(root, "toneChanges",      count="0")
    ET.SubElement(root, "controls",         count="0")

    # Single level — all notes
    levels_el = ET.SubElement(root, "levels", count="1")
    level_el  = ET.SubElement(levels_el, "level", difficulty="0")
    notes_el  = ET.SubElement(level_el,  "notes", count=str(len(rs_notes)))

    for n in rs_notes:
        note_el = ET.SubElement(notes_el, "note")
        note_el.set("time",           f"{n.time:.3f}")
        note_el.set("string",         str(n.string))
        note_el.set("fret",           str(n.fret))
        note_el.set("sustain",        f"{n.sustain:.3f}")
        note_el.set("hammerOn",       "1" if n.hammer_on else "0")
        note_el.set("pullOff",        "1" if n.pull_off  else "0")
        note_el.set("vibrato",        "1" if n.vibrato   else "0")
        note_el.set("slideTo",        str(n.slide_to))
        note_el.set("bend",           f"{n.bend:.1f}")
        note_el.set("linkNext",       "0")
        note_el.set("accent",         "0")
        note_el.set("harmonic",       "0")
        note_el.set("ignore",         "0")
        note_el.set("mute",           "0")
        note_el.set("palmMute",       "0")
        note_el.set("pluck",          "-1")
        note_el.set("slap",           "-1")
        note_el.set("slideUnpitchTo", "-1")
        note_el.set("hopo",           "0")
        note_el.set("harmonicPinch",  "0")
        note_el.set("rightHand",      "-1")
        note_el.set("tapStyle",       "0")
        note_el.set("pickDirection",  "0")

    ET.SubElement(level_el, "chords", count="0")

    anchors_data = smooth_anchors(rs_notes)
    anchors_el   = ET.SubElement(level_el, "anchors", count=str(len(anchors_data)))
    for t, f in anchors_data:
        ET.SubElement(anchors_el, "anchor", time=f"{t:.3f}", fret=str(f), width="4")

    ET.SubElement(level_el, "anchorExtensions", count="0")
    ET.SubElement(level_el, "handShapes",       count="0")
    ET.SubElement(level_el, "fingerprints",     count="0")

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _generate_ebeats(ebeats_el, song_length: float, avg_tempo: float) -> list[float]:
    beat_dur   = 60.0 / avg_tempo
    t          = 0.0
    beat       = 0
    measure    = 1
    bar_starts = []

    while t <= song_length + beat_dur:
        downbeat = (beat % 4 == 0)
        ET.SubElement(
            ebeats_el, "ebeat",
            time    = f"{t:.3f}",
            measure = str(measure) if downbeat else "-1"
        )
        if downbeat:
            bar_starts.append(t)
            measure += 1
        t    += beat_dur
        beat += 1

    ebeats_el.set("count", str(beat))
    return bar_starts


def _make_internal_name(song_name: str, arrangement: str) -> str:
    safe = "".join(c for c in song_name if c.isalnum())
    return f"{safe}_{arrangement.lower()}"