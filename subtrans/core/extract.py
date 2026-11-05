"""Subtitle extraction from video containers using ffmpeg."""

from __future__ import annotations
from pathlib import Path
from typing import Optional


def extract_subtitle_track(
    video_path: Path,
    track_index: int,
    output_path: Path,
    is_bitmap: bool = False,
) -> Path:
    """Extract a specific subtitle track from video container."""
    raise NotImplementedError("Will be implemented in M3")
