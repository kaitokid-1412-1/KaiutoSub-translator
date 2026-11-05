"""OCR pipeline for bitmap subtitles (PGS/VobSub) using SubtitleEdit CLI."""

from __future__ import annotations
from pathlib import Path
from typing import Optional


def ocr_bitmap_subtitle(
    input_path: Path,
    output_path: Path,
    timeout_seconds: int = 180,
    subtitleedit_path: str = "",
) -> Optional[Path]:
    """Perform OCR on bitmap subtitles with watchdog timer."""
    raise NotImplementedError("Will be implemented in M6")
