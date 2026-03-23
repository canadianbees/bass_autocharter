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
    """
    Convert (start, end, pitch) tuples + fretting into RSNote objects.

    note_tuples and fretting must be the same length — use
    filter_notes_to_fretting() from fretting.py to guarantee this.

    RS2014 string numbering is reversed from the fretting algorithm:
      fretting:  0=E (lowest string) ... 3=G (highest)
      RS2014:    0=G (highest)       ... 3=E (lowest)
    """
    if len(note_tuples) != len(fretting):
        raise ValueError(
            f"notes_to_rs: length mismatch — "
            f"{len(note_tuples)} notes vs {len(fretting)} fretting entries. "
            "Use filter_notes_to_fretting() to keep them in sync."
        )

    rs_notes = []
    for (start, end, pitch), (string_idx, fret) in zip(note_tuples, fretting):
        rs_string = 3 - string_idx          # flip string order for RS2014
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
    """
    Generate a Rocksmith 2014 arrangement XML file.

    song_length: total song duration in seconds
    avg_tempo:   BPM — used for ebeat generation (set to actual song tempo)
    """
    root      = ET.Element("song")
    root.set("version", "8")
    timestamp = datetime.utcnow().strftime("%m-%d-%Y %H:%M")
    internal  = _make_internal_name(song_name, arrangement)

    # ── METADATA ──────────────────────────────────────────────────────────
    ET.SubElement(root, "title").text          = song_name
    ET.SubElement(root, "arrangement").text    = arrangement
    ET.SubElement(root, "part").text           = "1"
    ET.SubElement(root, "offset").text         = "0"
    ET.SubElement(root, "centOffset").text     = "0"
    ET.SubElement(root, "songLength").text     = f"{song_length:.3f}"
    ET.SubElement(root, "internalName").text   = internal
    ET.SubElement(root, "songNameSort").text   = song_name
    ET.SubElement(root, "startBeat").text      = "0"
    ET.SubElement(root, "averageTempo").text   = f"{avg_tempo:.3f}"
    ET.SubElement(root, "capo").text           = "0"
    ET.SubElement(root, "artistName").text     = artist
    ET.SubElement(root, "artistNameSort").text = artist
    ET.SubElement(root, "albumName").text      = album_name
    ET.SubElement(root, "albumNameSort").text  = album_name
    ET.SubElement(root, "albumYear").text      = str(album_year)
    ET.SubElement(root, "crowdSpeed").text     = "1"
    ET.SubElement(root, "lastConversionDateTime").text = timestamp

    # ── TUNING ────────────────────────────────────────────────────────────
    tuning = ET.SubElement(root, "tuning")
    for i in range(4):
        tuning.set(f"string{i}", "0")

    # ── ARRANGEMENT PROPERTIES ────────────────────────────────────────────
    arr_props = ET.SubElement(root, "arrangementProperties")
    arr_props.set("pathBass",       "1")
    arr_props.set("standardTuning", "1")
    arr_props.set("represent",      "0")
    arr_props.set("sustain",        "1")

    # ── TONES ─────────────────────────────────────────────────────────────
    for t in ("tonebase", "tonea", "toneb", "tonec", "toned", "tone_multiplayer"):
        ET.SubElement(root, t).text = ""
    ET.SubElement(root, "tones", count="0")

    ET.SubElement(root, "volume").text        = "0.0"
    ET.SubElement(root, "previewVolume").text = "0.0"

    ET.SubElement(root, "chordTemplates", count="0")
    ET.SubElement(root, "fretHandMutes",  count="0")

    # ── EBEATS ────────────────────────────────────────────────────────────
    ebeats_el  = ET.SubElement(root, "ebeats")
    bar_starts = _generate_ebeats(ebeats_el, song_length, avg_tempo)

    # ── PHRASES ───────────────────────────────────────────────────────────
    phrase_times = segment_phrases(rs_notes, bar_starts)

    phrases_el = ET.SubElement(root, "phrases", count="1")
    ET.SubElement(phrases_el, "phrase", name="main", maxDifficulty="2")

    iters_el = ET.SubElement(root, "phraseIterations", count=str(len(phrase_times)))
    for t in phrase_times:
        ET.SubElement(iters_el, "phraseIteration",
                      time=f"{t:.3f}", phraseId="0")

    props_el = ET.SubElement(root, "phraseProperties", count="1")
    ET.SubElement(props_el, "phraseProperty",
                  phraseId="0", redundant="0", levelJump="0", empty="0")

    ET.SubElement(root, "newLinkedDiffs", count="0")
    ET.SubElement(root, "linkedDiffs",    count="0")

    # ── SECTIONS ──────────────────────────────────────────────────────────
    sections_el = ET.SubElement(root, "sections", count="2")
    ET.SubElement(sections_el, "section",
                  name="intro", number="1", startTime="0.0")
    ET.SubElement(sections_el, "section",
                  name="verse", number="1",
                  startTime=f"{phrase_times[1] if len(phrase_times) > 1 else 5.0:.3f}")

    ET.SubElement(root, "events",      count="0")
    ET.SubElement(root, "toneChanges", count="0")
    ET.SubElement(root, "controls",    count="0")

    # ── LEVELS ────────────────────────────────────────────────────────────
    levels_notes = generate_levels(rs_notes)
    levels_el    = ET.SubElement(root, "levels", count=str(len(levels_notes)))

    for diff, notes in enumerate(levels_notes):
        level_el = ET.SubElement(levels_el, "level", difficulty=str(diff))
        notes_el = ET.SubElement(level_el,  "notes", count=str(len(notes)))

        for n in notes:
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

            if n.bend_values:
                bvs_el = ET.SubElement(note_el, "bendValues")
                for bv in n.bend_values:
                    bv_el = ET.SubElement(bvs_el, "bendValue")
                    bv_el.set("time", f"{bv['time']:.3f}")
                    bv_el.set("step", f"{bv['step']:.1f}")

        ET.SubElement(level_el, "chords",           count="0")

        anchors_data = smooth_anchors(notes)
        anchors_el   = ET.SubElement(level_el, "anchors", count=str(len(anchors_data)))
        for t, f in anchors_data:
            ET.SubElement(anchors_el, "anchor",
                          time=f"{t:.3f}", fret=str(f), width="4")

        ET.SubElement(level_el, "anchorExtensions", count="0")
        ET.SubElement(level_el, "handShapes",       count="0")
        ET.SubElement(level_el, "fingerprints",     count="0")

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _generate_ebeats(ebeats_el, song_length: float, avg_tempo: float) -> list[float]:
    """
    Generate ebeats at a constant tempo.
    Returns list of bar start times (downbeats) for phrase segmentation.
    """
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

    return bar_starts


def _make_internal_name(song_name: str, arrangement: str) -> str:
    safe = "".join(c for c in song_name if c.isalnum())
    return f"{safe}_{arrangement.lower()}"