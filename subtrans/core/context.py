"""Series context extraction and metadata caching."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional


def extract_media_info(filename: str) -> Dict[str, Any]:
    """Extract series title, season, and episode from filename using guessit."""
    raise NotImplementedError("Will be implemented in M5")
