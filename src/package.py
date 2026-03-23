# package.py

import subprocess
import os
from pathlib import Path


# ── PREVIEW GENERATION ────────────────────────────────────────────────

def _make_preview(audio_path: str, output_dir: str) -> str:
    """
    Generates a 30-second preview clip using ffmpeg.
    """
    preview_path = Path(output_dir) / "preview.wav"

    subprocess.run([
        "ffmpeg",
        "-y",
        "-i", audio_path,
        "-ss", "30",     # start at 30s (simple heuristic)
        "-t", "30",      # 30 second clip
        str(preview_path)
    ], check=True)

    return str(preview_path)


# ── MAIN PACKAGING FUNCTION ───────────────────────────────────────────

def package_psarc(
    arrangement_xml_path: str,
    audio_wav_path: str,
    song_name: str,
    artist: str,
    output_dir: str,
    toolkit_path: str,
) -> str:
    """
    Packages arrangement + audio into a .psarc using RS Toolkit CLI.
    """

    # ── Validate inputs ───────────────────────────────────────────────
    if not Path(arrangement_xml_path).exists():
        raise FileNotFoundError(f"Missing XML: {arrangement_xml_path}")

    if not Path(audio_wav_path).exists():
        raise FileNotFoundError(f"Missing audio: {audio_wav_path}")

    os.makedirs(output_dir, exist_ok=True)

    # ── Generate preview audio ────────────────────────────────────────
    print("    Generating preview audio...")
    preview_path = _make_preview(audio_wav_path, output_dir)

    # ── Build toolkit config ──────────────────────────────────────────
    config_path = Path(output_dir) / "toolkit_config.xml"
    config_xml = _build_toolkit_config(
        arrangement_xml_path,
        audio_wav_path,
        preview_path,
        song_name,
        artist,
    )

    config_path.write_text(config_xml, encoding="utf-8")
    print(f"    Toolkit config written to {config_path}")

    # ── Resolve toolkit executable ────────────────────────────────────
    toolkit_exe = Path(toolkit_path)

    if toolkit_exe.is_dir():
        # Windows default
        exe = toolkit_exe / "RocksmithToolkitCLI.exe"
        if exe.exists():
            toolkit_exe = exe

    if not toolkit_exe.exists():
        raise FileNotFoundError(f"Toolkit not found: {toolkit_exe}")

    # ── Run toolkit ───────────────────────────────────────────────────
    print("    Running RS Toolkit — packaging .psarc...")

    subprocess.run([
        str(toolkit_exe),
        "-c", str(config_path),
        "-o", output_dir,
        "-p", "RS2014",
        "-t", "PC",
    ], check=True)

    # ── Find output ───────────────────────────────────────────────────
    psarc_files = list(Path(output_dir).glob("*.psarc"))

    if not psarc_files:
        raise FileNotFoundError(
            f"No .psarc generated in {output_dir}. Check toolkit logs."
        )

    psarc_path = str(psarc_files[0])
    print(f"    Done: {psarc_path}")
    return psarc_path


# ── CONFIG BUILDER ────────────────────────────────────────────────────

def _build_toolkit_config(
    arrangement_xml_path: str,
    audio_wav_path: str,
    preview_wav_path: str,
    song_name: str,
    artist: str,
) -> str:
    """
    Builds toolkit XML config.
    """

    slug = "".join(c for c in song_name.lower() if c.isalnum() or c == "_")
    slug = slug.replace(" ", "_")

    return f"""<?xml version="1.0"?>
<DLCPackageData>
  <GameVersion>RS2014</GameVersion>
  <Name>{slug}</Name>

  <SongInfo>
    <SongDisplayName>{song_name}</SongDisplayName>
    <Artist>{artist}</Artist>
    <SongYear>2024</SongYear>
    <AverageTempo>120</AverageTempo>
  </SongInfo>

  <Arrangements>
    <Arrangement>
      <ArrangementType>Bass</ArrangementType>

      <SongXml>
        <File>{arrangement_xml_path}</File>
      </SongXml>

      <SongAudio>
        <File>{audio_wav_path}</File>
      </SongAudio>

      <PreviewAudio>
        <File>{preview_wav_path}</File>
      </PreviewAudio>

    </Arrangement>
  </Arrangements>
</DLCPackageData>
"""