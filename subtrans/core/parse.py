"""Subtitle file parsing, encoding detection, and line classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import charset_normalizer
import pysubs2

# Persian/Arabic Unicode range
PERSIAN_PATTERN = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_PATTERN = re.compile(r"[a-zA-Z]")

# Drawing commands: \p1 to \p9
DRAWING_PATTERN = re.compile(r"\\p[1-9]")

# Karaoke commands: \k, \kf, \ko, \K
KARAOKE_PATTERN = re.compile(r"\\[kK][fFoO]?\d+")

# Music notes, digits, punctuation only
MUSIC_DIGIT_PATTERN = re.compile(r"^[\s0-9♪♫🎵🎶#\.\,\:\;\-\_\!\?\(\)\[\]\{\}\<\>\"\'\*\+\=\/\\\|\~\`\^\@\&\%\$]+$")

# SDH cue pattern (e.g. [door slams] or (coughing))
SDH_PATTERN = re.compile(r"^\s*(\[[^\]]+\]|\([^\)]+\))\s*$")

# Style names to skip for signs / songs
DEFAULT_SKIP_STYLES = {
    "sign", "signs", "song", "songs", "op", "ed", "opening", "ending",
    "karaoke", "credits", "credit", "title", "insert",
}


class LineStatus(str, Enum):
    TRANSLATABLE = "translatable"
    SKIP_COMMENT = "skip_comment"
    SKIP_DRAWING = "skip_drawing"
    SKIP_KARAOKE = "skip_karaoke"
    SKIP_STYLE = "skip_style"
    SKIP_EMPTY = "skip_empty"
    SKIP_MUSIC_OR_NUMBERS = "skip_music_or_numbers"
    SKIP_ALREADY_PERSIAN = "skip_already_persian"
    SKIP_SDH = "skip_sdh"


@dataclass
class ParsedLine:
    line_index: int
    event: pysubs2.SSAEvent
    status: LineStatus
    source_text: str
    plain_text: str
    skip_reason: Optional[str] = None


def detect_and_read_subtitle_content(file_path: Path) -> Tuple[str, str]:
    """Read subtitle file, detecting BOM, UTF-8, charset-normalizer, cp1256, cp1252.
    
    Returns (content_str, detected_encoding).
    """
    raw_bytes = file_path.read_bytes()
    if not raw_bytes:
        return "", "utf-8"

    # Check BOM
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe"):
        return raw_bytes[2:].decode("utf-16-le", errors="replace"), "utf-16-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes[2:].decode("utf-16-be", errors="replace"), "utf-16-be"

    # Try plain UTF-8
    try:
        return raw_bytes.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    # Try charset-normalizer
    try:
        best_match = charset_normalizer.from_bytes(raw_bytes).best()
        if best_match and best_match.encoding:
            # If charset_normalizer detected high-confidence encoding
            if best_match.coherence > 0.0 or not best_match.encoding.startswith(("cp9", "euc", "shift_jis")):
                return str(best_match), best_match.encoding
    except Exception:
        pass

    # Try cp1256 (Persian/Arabic Windows)
    try:
        decoded_1256 = raw_bytes.decode("cp1256")
        if PERSIAN_PATTERN.search(decoded_1256):
            return decoded_1256, "cp1256"
    except UnicodeDecodeError:
        pass

    # Fallback to cp1252 or utf-8 with replace
    try:
        return raw_bytes.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw_bytes.decode("utf-8", errors="replace"), "utf-8"


def load_subtitle(file_path: Path) -> Tuple[pysubs2.SSAFile, str, str]:
    """Load subtitle file into pysubs2 SSAFile.
    
    Returns (ssa_file, detected_format, detected_encoding).
    """
    content, encoding = detect_and_read_subtitle_content(file_path)
    ext = file_path.suffix.lower().lstrip(".")
    fmt = ext if ext in ("srt", "ass", "ssa", "vtt") else None

    # Try loading from string with format hint or auto-detection
    try:
        if fmt:
            subs = pysubs2.SSAFile.from_string(content, format_=fmt)
        else:
            subs = pysubs2.SSAFile.from_string(content)
            fmt = subs.format or "srt"
    except Exception:
        # Fallback to direct load or empty
        subs = pysubs2.SSAFile()
        fmt = fmt or "srt"

    return subs, fmt, encoding


def classify_line(
    event: pysubs2.SSAEvent,
    index: int,
    translate_signs_songs: bool = False,
    translate_sdh_cues: bool = True,
    custom_skip_styles: Optional[set] = None,
) -> ParsedLine:
    """Classify a subtitle event according to SPEC section 4.5."""
    source_text = event.text or ""
    plain = event.plaintext.strip() if event.plaintext else ""

    # 1. Comment events
    if getattr(event, "is_comment", False):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_COMMENT,
            source_text=source_text,
            plain_text=plain,
            skip_reason="رویداد توضیحی (Comment)",
        )

    # 2. Vector drawings (\p1 to \p9)
    if DRAWING_PATTERN.search(source_text):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_DRAWING,
            source_text=source_text,
            plain_text=plain,
            skip_reason="طرح برداری (Vector Drawing)",
        )

    # 3. Karaoke tags (\k, \kf, \ko)
    if KARAOKE_PATTERN.search(source_text):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_KARAOKE,
            source_text=source_text,
            plain_text=plain,
            skip_reason="تگ کارائوکه",
        )

    # 4. Empty text
    if not plain:
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_EMPTY,
            source_text=source_text,
            plain_text=plain,
            skip_reason="متن خالی",
        )

    # 5. Styles matching sign/song/op/ed/credits/title
    skip_styles = custom_skip_styles if custom_skip_styles is not None else DEFAULT_SKIP_STYLES
    style_lower = (event.style or "").strip().lower()
    if not translate_signs_songs and any(s in style_lower for s in skip_styles):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_STYLE,
            source_text=source_text,
            plain_text=plain,
            skip_reason=f"استایل غیراصلی ({event.style})",
        )

    # 6. Only music symbols or digits/punctuation
    if MUSIC_DIGIT_PATTERN.match(plain):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_MUSIC_OR_NUMBERS,
            source_text=source_text,
            plain_text=plain,
            skip_reason="صرفاً نت موسیقی یا اعداد",
        )

    # 7. Check if already mostly Persian
    persian_chars = len(PERSIAN_PATTERN.findall(plain))
    latin_chars = len(LATIN_PATTERN.findall(plain))
    if persian_chars > 0 and persian_chars >= latin_chars:
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_ALREADY_PERSIAN,
            source_text=source_text,
            plain_text=plain,
            skip_reason="متن از قبل فارسی است",
        )

    # 8. SDH cues if disabled
    if not translate_sdh_cues and SDH_PATTERN.match(plain):
        return ParsedLine(
            line_index=index,
            event=event,
            status=LineStatus.SKIP_SDH,
            source_text=source_text,
            plain_text=plain,
            skip_reason="توضیح ناشنوایان (SDH)",
        )

    # Default: Translatable
    return ParsedLine(
        line_index=index,
        event=event,
        status=LineStatus.TRANSLATABLE,
        source_text=source_text,
        plain_text=plain,
    )


def classify_subtitles(
    subs: pysubs2.SSAFile,
    translate_signs_songs: bool = False,
    translate_sdh_cues: bool = True,
    custom_skip_styles: Optional[set] = None,
) -> List[ParsedLine]:
    """Classify all lines in a subtitle file."""
    classified = []
    for idx, event in enumerate(subs.events):
        line = classify_line(
            event=event,
            index=idx,
            translate_signs_songs=translate_signs_songs,
            translate_sdh_cues=translate_sdh_cues,
            custom_skip_styles=custom_skip_styles,
        )
        classified.append(line)
    return classified

