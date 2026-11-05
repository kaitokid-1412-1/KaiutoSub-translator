"""Subtitle extraction from video containers using ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from subtrans.core.parse import LATIN_PATTERN, PERSIAN_PATTERN, load_subtitle
from subtrans.core.probe import SubtitleTrack


def extract_subtitle_track(
    video_path: Path,
    track: SubtitleTrack,
    output_path: Optional[Path] = None,
) -> Path:
    """Extract a specific subtitle track from video container using ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise FileNotFoundError("FFmpeg پیدا نشد. لطفاً مطمئن شوید در PATH نصب است.")

    if output_path is None:
        ext = track.extension
        output_path = video_path.parent / f"{video_path.stem}.extracted.{ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Base ffmpeg command
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-map", f"0:{track.index}",
    ]

    # Handle codec conversion: mov_text -> srt; otherwise copy
    if track.codec_name == "mov_text":
        cmd.extend(["-c:s", "srt"])
    else:
        cmd.extend(["-c:s", "copy"])

    cmd.append(str(output_path))

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        raise RuntimeError(f"خطا در استخراج زیرنویس با FFmpeg: {proc.stderr}")

    return output_path


def find_external_subtitle(video_path: Path) -> Optional[Path]:
    """Look for an external subtitle with matching stem in the same folder.
    
    Ignores files ending in .fa.* or existing translations.
    """
    directory = video_path.parent
    stem = video_path.stem

    valid_extensions = {".srt", ".ass", ".ssa", ".vtt"}

    # Exact match: video.srt, video.ass, etc.
    for ext in valid_extensions:
        cand = directory / f"{stem}{ext}"
        if cand.is_file():
            return cand

    # Pattern matches: video.en.srt, video.eng.ass, etc.
    for file in directory.iterdir():
        if not file.is_file() or file.suffix.lower() not in valid_extensions:
            continue
        if file.name.lower().endswith((".fa.srt", ".fa.ass", ".fa.vtt")):
            continue
        if file.stem.startswith(stem):
            return file

    return None


def is_subtitle_already_persian(sub_path: Path) -> bool:
    """Check if subtitle content is already mostly Persian."""
    try:
        subs, _, _ = load_subtitle(sub_path)
    except Exception:
        return False

    all_text = " ".join([ev.plaintext for ev in subs.events if ev.plaintext])
    persian_count = len(PERSIAN_PATTERN.findall(all_text))
    latin_count = len(LATIN_PATTERN.findall(all_text))

    if persian_count > 0 and persian_count >= latin_count:
        return True
    return False

