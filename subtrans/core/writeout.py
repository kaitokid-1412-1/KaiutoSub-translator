"""Subtitle output generation with atomic writes and UTF-8 BOM."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional
import pysubs2


def get_output_path(
    source_path: Path,
    output_pattern: str = "{stem}.{lang}.{ext}",
    target_lang: str = "fa",
    target_ext: Optional[str] = None,
) -> Path:
    """Generate target output path based on configurable pattern."""
    stem = source_path.stem
    # If source already has .eng or other lang tag, strip or keep appropriately
    ext = target_ext if target_ext else source_path.suffix.lstrip(".")
    formatted_name = output_pattern.format(stem=stem, lang=target_lang, ext=ext)
    return source_path.parent / formatted_name


def write_subtitle_file(
    subs: pysubs2.SSAFile,
    output_path: Path,
    encoding: str = "utf-8-sig",
    overwrite: bool = False,
    backup_existing: bool = True,
    format_: Optional[str] = None,
) -> Path:
    """Write translated subtitle file safely using temp file and atomic replace.
    
    Protects original files, writes with UTF-8 BOM (if configured), and handles backups.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Never overwrite original video/subtitle if output_path is same as source
    # If target exists and overwrite is False, raise or return
    if output_path.exists():
        if not overwrite:
            raise FileExistsError(f"فایل مقصد از قبل وجود دارد: {output_path}")
        elif backup_existing:
            bak_path = output_path.with_suffix(output_path.suffix + ".bak")
            shutil.copy2(output_path, bak_path)

    # Determine format
    fmt = format_ or output_path.suffix.lower().lstrip(".")
    if fmt not in ("srt", "ass", "ssa", "vtt"):
        fmt = "srt"

    # Convert to string representation
    content_str = subs.to_string(format_=fmt)

    # Handle encoding
    enc = encoding.lower()
    if enc in ("utf-8-sig", "utf-8_sig", "bom"):
        raw_bytes = b"\xef\xbb\xbf" + content_str.encode("utf-8")
    else:
        raw_bytes = content_str.encode(encoding, errors="replace")

    # Atomic write via temp file in the same directory
    temp_fd, temp_file_path = tempfile.mkstemp(
        prefix=".subtrans_tmp_",
        suffix=output_path.suffix,
        dir=output_path.parent,
    )
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(raw_bytes)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        os.replace(temp_file_path, output_path)
    except Exception:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        raise

    return output_path

