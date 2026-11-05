"""Unit tests for subtitle parsing, encoding detection, and line classification."""

from pathlib import Path
import pysubs2
from subtrans.core.parse import (
    LineStatus,
    classify_line,
    classify_subtitles,
    detect_and_read_subtitle_content,
    load_subtitle,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_encoding_detection():
    # 1. BOM detection
    content, enc = detect_and_read_subtitle_content(FIXTURES_DIR / "sample_bom.srt")
    assert enc == "utf-8-sig"
    assert "Hello" in content

    # 2. Standard UTF-8
    content, enc = detect_and_read_subtitle_content(FIXTURES_DIR / "sample.srt")
    assert enc == "utf-8"
    assert "Hello" in content

    # 3. CP1256
    content, enc = detect_and_read_subtitle_content(FIXTURES_DIR / "sample_cp1256.srt")
    assert enc.lower() in ("cp1256", "windows-1256")
    assert "مرحبا" in content


def test_classify_lines_srt():
    subs, fmt, enc = load_subtitle(FIXTURES_DIR / "sample.srt")
    classified = classify_subtitles(subs, translate_signs_songs=False, translate_sdh_cues=True)

    # Line 0: "Hello <i>world</i>!\nThis is a second line." -> TRANSLATABLE
    assert classified[0].status == LineStatus.TRANSLATABLE

    # Line 1: "♪ ♫ 12345 ♪" -> SKIP_MUSIC_OR_NUMBERS
    assert classified[1].status == LineStatus.SKIP_MUSIC_OR_NUMBERS

    # Line 2: "[door slams loudly]" -> TRANSLATABLE (translate_sdh_cues=True)
    assert classified[2].status == LineStatus.TRANSLATABLE

    # Line 3: "این خط قبلاً به فارسی ترجمه شده است." -> SKIP_ALREADY_PERSIAN
    assert classified[3].status == LineStatus.SKIP_ALREADY_PERSIAN

    # Line 4: "Thank you very much!" -> TRANSLATABLE
    assert classified[4].status == LineStatus.TRANSLATABLE


def test_classify_lines_sdh_disabled():
    subs, fmt, enc = load_subtitle(FIXTURES_DIR / "sample.srt")
    classified = classify_subtitles(subs, translate_signs_songs=False, translate_sdh_cues=False)
    # Line 2: [door slams loudly] -> SKIP_SDH
    assert classified[2].status == LineStatus.SKIP_SDH


def test_classify_lines_ass():
    subs, fmt, enc = load_subtitle(FIXTURES_DIR / "sample.ass")
    classified = classify_subtitles(subs, translate_signs_songs=False)

    # 0: Dialogue with tags and breaks -> TRANSLATABLE
    assert classified[0].status == LineStatus.TRANSLATABLE

    # 1: Style Sign -> SKIP_STYLE
    assert classified[1].status == LineStatus.SKIP_STYLE

    # 2: Style OP_Song -> SKIP_STYLE
    assert classified[2].status == LineStatus.SKIP_STYLE

    # 3: Karaoke -> SKIP_KARAOKE
    assert classified[3].status == LineStatus.SKIP_KARAOKE

    # 4: Vector drawing \p1 -> SKIP_DRAWING
    assert classified[4].status == LineStatus.SKIP_DRAWING

    # 5: Comment event -> SKIP_COMMENT
    assert classified[5].status == LineStatus.SKIP_COMMENT

    # 6: Dialogue "Good morning, Sensei!" -> TRANSLATABLE
    assert classified[6].status == LineStatus.TRANSLATABLE
