"""Persian text normalizer, punctuation fixer, ZWNJ and BiDi handler."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
import pysubs2

from subtrans.core.config import PersianConfig

# Unicode markers
ZWNJ = "\u200c"      # Zero-Width Non-Joiner (Half space)
RLM = "\u200f"       # Right-to-Left Mark
RLE = "\u202b"       # Right-to-Left Embedding
PDF = "\u202c"       # Pop Directional Formatting

# Digit mappings
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "0123456789"
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

ARABIC_INDIC_TRANS = str.maketrans(ARABIC_INDIC_DIGITS, PERSIAN_DIGITS)
ASCII_TO_PERSIAN_DIGITS_TRANS = str.maketrans(ASCII_DIGITS, PERSIAN_DIGITS)

# Persian letters
PERSIAN_LETTERS_PATTERN = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")


class PersianNormalizer:
    """Post-processing pipeline for Persian subtitle text."""

    def __init__(self, config: Optional[PersianConfig] = None):
        self.cfg = config or PersianConfig()

    def normalize_letters(self, text: str) -> str:
        """Standardize Arabic Kaf, Yeh and other letter variants to Persian."""
        if not text:
            return ""
        # Arabic kaf to Persian kaf
        text = text.replace("\u0643", "\u06a9")
        # Arabic yeh and alef maksura to Persian yeh
        text = text.replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
        # Arabic heh with yeh above to heh + ZWNJ + yeh
        text = text.replace("\u06c0", "هٔ").replace("ۀ", "هٔ")
        return text

    def convert_digits(self, text: str, include_ascii: bool = True) -> str:
        """Convert Arabic-Indic (and optionally ASCII) digits to Persian digits."""
        if not text:
            return ""
        # Always convert Arabic-Indic digits
        text = text.translate(ARABIC_INDIC_TRANS)
        if include_ascii:
            # Only convert ASCII digits that are part of Persian text or standalone numbers
            # Do not convert digits inside tokens like [[T1]] or ASS tags {\pos(100,200)}
            def replace_digits(match: re.Match) -> str:
                s = match.group(0)
                # Keep tag/token brackets untouched
                if s.startswith("[[") or s.startswith("{"):
                    return s
                return s.translate(ASCII_TO_PERSIAN_DIGITS_TRANS)

            # Match tokens / override tags OR digit sequences
            text = re.sub(r"\[\[T\d+\]\]|\{[^{}]*\}|\d+", replace_digits, text)
        return text

    def fix_punctuation(self, text: str) -> str:
        """Standardize Persian punctuation and spacing."""
        if not text:
            return ""

        # Replace ... with ellipsis character
        text = re.sub(r"\.{3,}", "…", text)

        # Replace English comma, question mark, semicolon inside Persian text
        # Only replace comma if not directly surrounded by digits (e.g. 1,000)
        text = re.sub(r"(?<=[آ-ی\s]),(?=[آ-ی\s]|$)", "،", text)
        text = text.replace("?", "؟").replace(";", "؛")

        # Fix spacing around punctuation: no space before, one space after if followed by word
        # Punctuation set: . ، ! ؟ ؛ : …
        text = re.sub(r"\s+([.،!؟؛:…])", r"\1", text)
        text = re.sub(r"([.،!؟؛:…])(?=[آ-یA-Za-z0-9])", r"\1 ", text)

        return text

    def fix_zwnj(self, text: str) -> str:
        """Apply conservative ZWNJ rules for Persian verbs, plurals, and compounds."""
        if not text:
            return ""

        # 1. Prefix می and نمی followed by verb: e.g. "می رود" -> "می‌رود"
        text = re.sub(r"\b(ن?می)\s+([آ-ی])", rf"\1{ZWNJ}\2", text)

        # 2. Plural suffix ها: e.g. "کتاب ها" -> "کتاب‌ها", "خانه هایمان" -> "خانه‌هایمان"
        text = re.sub(r"\b([آ-ی]{2,})\s+(ها(?:ی|یی|م|ت|ش|مان|تان|شان|یم|یت|یش|یمان|یتان|یشان)?)\b", rf"\1{ZWNJ}\2", text)

        # 3. Comparative suffixes تر / ترین: e.g. "بزرگ تر" -> "بزرگ‌تر"
        text = re.sub(r"\b([آ-ی]{2,})\s+(تر(?:ین|ی)?)\b", rf"\1{ZWNJ}\2", text)

        # 4. Common compounds: "بی شک", "این گونه", "آن جا"
        text = re.sub(r"\b(بی)\s+([آ-ی]{2,})\b", rf"\1{ZWNJ}\2", text)
        text = re.sub(r"\b(این|آن)\s+(گونه|طور|جا)\b", rf"\1{ZWNJ}\2", text)

        # 5. Clean up duplicate ZWNJ
        text = re.sub(rf"{ZWNJ}+", ZWNJ, text)
        return text

    def rewrap_lines(self, text: str, max_chars: int = 42) -> str:
        """Wrap line into at most two balanced lines if exceeding max_chars."""
        if not text:
            return ""

        # Do not wrap if line already contains breaks (\n or \N) or ASS positioning \pos
        if "\n" in text or r"\N" in text or r"\pos" in text:
            return text

        if len(text) <= max_chars:
            return text

        words = text.split()
        if len(words) <= 1:
            return text

        mid_point = len(text) // 2
        best_split_idx = -1
        min_distance = len(text)
        current_len = 0

        for i, word in enumerate(words[:-1]):
            current_len += len(word)
            dist = abs(current_len - mid_point)
            if dist < min_distance:
                min_distance = dist
                best_split_idx = i
            current_len += 1  # for space

        if best_split_idx != -1:
            line1 = " ".join(words[: best_split_idx + 1])
            line2 = " ".join(words[best_split_idx + 1 :])
            return f"{line1}\n{line2}"

        return text

    def apply_bidi(self, text: str, mode: str = "rle") -> str:
        """Apply BiDi directional embedding or marks to prevent punctuation reversal."""
        if not text or mode == "none":
            return text

        # Split lines by either real newline or ASS \N
        is_ass_break = r"\N" in text and "\n" not in text
        split_token = r"\N" if is_ass_break else "\n"
        lines = text.split(split_token)

        bidi_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                bidi_lines.append(line)
                continue

            if mode == "rlm":
                # Add RLM at beginning if not present
                if not line_str.startswith(RLM):
                    line_str = RLM + line_str
            elif mode == "rle":
                # Wrap line in RLE ... PDF if not already wrapped
                if not (line_str.startswith(RLE) and line_str.endswith(PDF)):
                    line_str = f"{RLE}{line_str}{PDF}"

            bidi_lines.append(line_str)

        return split_token.join(bidi_lines)

    def process(self, text: str, is_ass: bool = False) -> str:
        """Execute full post-processing pipeline based on configuration."""
        if not text:
            return ""

        # Preserve override tags and tokens during post-processing
        # 1. Normalize letters
        if self.cfg.normalize_letters:
            text = self.normalize_letters(text)

        # 2. Punctuation
        if self.cfg.fix_punctuation:
            text = self.fix_punctuation(text)

        # 3. ZWNJ
        if self.cfg.fix_zwnj:
            text = self.fix_zwnj(text)

        # 4. Convert digits
        if self.cfg.persian_digits:
            text = self.convert_digits(text, include_ascii=True)

        # 5. Re-wrap lines if exceeding max chars
        if self.cfg.rewrap:
            text = self.rewrap_lines(text, max_chars=self.cfg.max_chars_per_line)

        # 6. BiDi direction formatting
        if self.cfg.bidi_mode and self.cfg.bidi_mode != "none":
            text = self.apply_bidi(text, mode=self.cfg.bidi_mode)

        # Ensure line break representation
        if is_ass:
            text = text.replace("\r\n", "\n").replace("\n", r"\N")

        return text


def update_ass_styles_for_persian(
    subs: pysubs2.SSAFile,
    font_name: str = "Tahoma",
    encoding: int = 178,
):
    """Set font to Persian font (default Tahoma) and Encoding=178 (Arabic) for ASS styles."""
    for style_name, style in subs.styles.items():
        style.fontname = font_name
        # Encoding 178 = Arabic script in SSA/ASS specification
        style.encoding = encoding


def generate_bidi_test_srt(output_path: Optional[Path] = None) -> Path:
    """Generate bidi_test.srt showcasing none, rlm, and rle modes for player/TV testing."""
    target = output_path or Path("bidi_test.srt")
    cues = [
        "1\n00:00:01,000 --> 00:00:06,000\nحالت ۱ (None - بدون نشانگر):\nسلام! تست شماره 123 بدون نشانگر است. آیا علامت تعجب و نقطه درست هستند؟",
        f"2\n00:00:07,000 --> 00:00:12,000\n{RLM}حالت ۲ (RLM - نشانگر جهت راست به چپ):\n{RLM}سلام! تست شماره 123 با RLM است. آیا علامت تعجب و نقطه درست هستند؟",
        f"3\n00:00:13,000 --> 00:00:18,000\n{RLE}حالت ۳ (RLE - احاطه کامل دوطرفه):\nسلام! تست شماره 123 با RLE است. آیا علامت تعجب و نقطه درست هستند؟{PDF}",
        f"4\n00:00:19,000 --> 00:00:25,000\n{RLE}جان گفت: \"کد 456 را در ساعت 12:30 بررسی کن!\" (کلمات انگلیسی و اعداد){PDF}",
        f"5\n00:00:26,000 --> 00:00:32,000\n{RLE}هر حالتی که در پلیر یا تلویزیون شما علائم را در انتهای جمله بدون جابه‌جایی نشان داد، در تنظیمات انتخاب کنید.{PDF}",
    ]
    srt_text = "\n\n".join(cues) + "\n"
    # Write with UTF-8 BOM
    target.write_bytes(b"\xef\xbb\xbf" + srt_text.encode("utf-8"))
    return target

