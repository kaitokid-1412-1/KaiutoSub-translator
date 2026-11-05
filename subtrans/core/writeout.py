"""Subtitle output generation with atomic writes and UTF-8 BOM."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Optional


def write_subtitle_file(
    content: Any,
    output_path: Path,
    encoding: str = "utf-8-sig",
    overwrite: bool = False,
) -> Path:
    """Write translated subtitle file safely using temp file and atomic replace."""
    raise NotImplementedError("Will be implemented in M1")
