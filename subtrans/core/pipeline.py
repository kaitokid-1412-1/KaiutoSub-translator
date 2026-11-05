"""Overall translation pipeline coordinator."""

from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class Stage(str, Enum):
    DISCOVER = "discover"
    EXTRACT = "extract"
    OCR = "ocr"
    CONTEXT = "context"
    TRANSLATE = "translate"
    QC = "qc"
    WRITE = "write"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


class Pipeline:
    """Coordinates pipeline execution across files."""
    pass
