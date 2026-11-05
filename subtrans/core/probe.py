"""Media probing utilities using ffprobe."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional


def probe_subtitles(video_path: Path) -> List[Dict[str, Any]]:
    """Probe subtitle streams inside a video container using ffprobe."""
    raise NotImplementedError("Will be implemented in M3")
