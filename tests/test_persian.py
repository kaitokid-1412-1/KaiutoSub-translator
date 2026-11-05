"""Unit tests for Persian normalizer, punctuation, ZWNJ, and BiDi formatting."""

from pathlib import Path
import pysubs2
from subtrans.core.config import PersianConfig
from subtrans.core.persian import (
    PDF,
    RLE,
    RLM,
    ZWNJ,
    PersianNormalizer,
    generate_bidi_test_srt,
    update_ass_styles_for_persian,
)


def test_persian_normalize_letters():
    norm = PersianNormalizer()
    # Arabic kaf and yeh
    raw = "كتاب يار من است و پنجرهٔ خانه"
    result = norm.normalize_letters(raw)
    assert "ک" in result and "ك" not in result
    assert "ی" in result and "ي" not in result


def test_persian_digits_conversion():
    norm = PersianNormalizer()
    raw = "کد 123 و شماره ٤٥٦ در تگ [[T1]] و {\\pos(100,200)}"
    result = norm.convert_digits(raw, include_ascii=True)
    # Digits in text converted to Persian digits ۱۲۳ and ۴۵۶
    assert "۱۲۳" in result
    assert "۴۵۶" in result
    # Tokens and tags preserved
    assert "[[T1]]" in result
    assert "{\\pos(100,200)}" in result


def test_persian_punctuation_and_spacing():
    norm = PersianNormalizer()
    raw = "سلام ,چطوری ?خوبی... من خوبم ;شما چطور ?"
    result = norm.fix_punctuation(raw)
    assert "،" in result and "," not in result
    assert "؟" in result and "?" not in result
    assert "؛" in result and ";" not in result
    assert "…" in result and "..." not in result
    # Space after punctuation, no space before
    assert "سلام، چطوری؟" in result


def test_persian_zwnj():
    norm = PersianNormalizer()
    # Verbs
    assert norm.fix_zwnj("می روم") == f"می{ZWNJ}روم"
    assert norm.fix_zwnj("نمی دانم") == f"نمی{ZWNJ}دانم"

    # Plural suffix
    assert norm.fix_zwnj("کتاب ها") == f"کتاب{ZWNJ}ها"
    assert norm.fix_zwnj("خانه هایمان") == f"خانه{ZWNJ}هایمان"

    # Comparative suffix
    assert norm.fix_zwnj("بزرگ تر") == f"بزرگ{ZWNJ}تر"
    assert norm.fix_zwnj("زیباترین") == "زیباترین"  # already joined
    assert norm.fix_zwnj("کوچک ترین") == f"کوچک{ZWNJ}ترین"

    # Compounds
    assert norm.fix_zwnj("بی شک") == f"بی{ZWNJ}شک"
    assert norm.fix_zwnj("این گونه") == f"این{ZWNJ}گونه"


def test_persian_rewrap_lines():
    norm = PersianNormalizer()
    # Short line: unchanged
    short_line = "یک خط کوتاه."
    assert norm.rewrap_lines(short_line, max_chars=42) == short_line

    # Long line: wrapped into 2 balanced lines
    long_line = "این یک خط بسیار طولانی برای تست عملکرد شکستن خودکار خطوط زیرنویس است."
    wrapped = norm.rewrap_lines(long_line, max_chars=42)
    assert "\n" in wrapped
    lines = wrapped.split("\n")
    assert len(lines) == 2
    assert all(len(l) < len(long_line) for l in lines)

    # Line with existing breaks: never touched
    multi_line = "خط اول\nخط دوم طولانی که از قبل دارای اینتر و شکستگی است."
    assert norm.rewrap_lines(multi_line, max_chars=42) == multi_line


def test_bidi_modes():
    norm = PersianNormalizer()
    text = "سلام دنیا!"

    # none
    assert norm.apply_bidi(text, mode="none") == text

    # rlm
    rlm_text = norm.apply_bidi(text, mode="rlm")
    assert rlm_text.startswith(RLM)

    # rle
    rle_text = norm.apply_bidi(text, mode="rle")
    assert rle_text.startswith(RLE)
    assert rle_text.endswith(PDF)


def test_update_ass_styles():
    subs = pysubs2.SSAFile()
    style = pysubs2.SSAStyle()
    style.fontname = "Arial"
    style.encoding = 0
    subs.styles["Default"] = style

    update_ass_styles_for_persian(subs, font_name="Tahoma", encoding=178)
    assert subs.styles["Default"].fontname == "Tahoma"
    assert subs.styles["Default"].encoding == 178


def test_generate_bidi_test_srt(tmp_path: Path):
    target = tmp_path / "bidi_test.srt"
    res = generate_bidi_test_srt(target)
    assert res.is_file()
    bytes_data = res.read_bytes()
    assert bytes_data.startswith(b"\xef\xbb\xbf")
    text_data = bytes_data.decode("utf-8")
    assert RLE in text_data
    assert RLM in text_data
    assert "حالت ۱" in text_data
