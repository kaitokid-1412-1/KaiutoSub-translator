"""Quality control pass and translation validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pysubs2

from subtrans.core.parse import LATIN_PATTERN, MUSIC_DIGIT_PATTERN, PERSIAN_PATTERN

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
TAG_PATTERN = re.compile(r"\{[^{}]*\}|\[\[T\d+\]\]|\\[a-zA-Z]+|[\r\n]")


def is_line_suspicious_non_persian(
    text: str,
    keep_terms: Optional[Set[str]] = None,
) -> bool:
    """Check if translated line still contains mostly untranslated Latin letters."""
    if not text:
        return False

    cleaned = TAG_PATTERN.sub("", text)
    cleaned = URL_PATTERN.sub("", cleaned)

    if keep_terms:
        for term in keep_terms:
            if term:
                cleaned = cleaned.replace(term, "")

    if MUSIC_DIGIT_PATTERN.match(cleaned):
        return False

    persian_count = len(PERSIAN_PATTERN.findall(cleaned))
    latin_count = len(LATIN_PATTERN.findall(cleaned))

    if latin_count > 0 and latin_count >= persian_count:
        return True
    return False


@dataclass
class FlaggedQCLine:
    line_index: int
    start_time: str
    end_time: str
    source_text: str
    translated_text: str
    reason: str


@dataclass
class QCReport:
    file_id: str
    total_lines: int = 0
    translated_count: int = 0
    skipped_count: int = 0
    degraded_count: int = 0
    failed_count: int = 0
    api_calls: int = 0
    flagged_lines: List[FlaggedQCLine] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    def to_persian_text(self) -> str:
        lines = [
            f"=== گزارش کنترل کیفیت ترجمه (QC Report): {self.file_id} ===",
            f"مجموع خطوط: {self.total_lines}",
            f"خطوط ترجمه شده: {self.translated_count}",
            f"خطوط رد شده (توضیحی/استایل/فارسی): {self.skipped_count}",
            f"خطوط با استایل تقلیل یافته (Degraded): {self.degraded_count}",
            f"خطوط ناموفق: {self.failed_count}",
            f"تعداد فراخوانی‌های API: {self.api_calls}",
            "--------------------------------------------------",
        ]
        if not self.flagged_lines:
            lines.append("وضعیت کنترل کیفیت: کاملاً تایید شده (هیچ خط مشکوکی یافت نشد).")
        else:
            lines.append(f"تعداد خطوط مشکوک یا نیازمند بازبینی: {len(self.flagged_lines)}")
            for item in self.flagged_lines:
                lines.append(
                    f"[خط {item.line_index + 1} | {item.start_time} --> {item.end_time}] علت: {item.reason}\n"
                    f"   متن اصلی: {item.source_text}\n"
                    f"   ترجمه فعلی: {item.translated_text}"
                )
        return "\n".join(lines)

    def save(self, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        # 1. JSON report
        json_path = output_dir / f"{self.file_id}.qc.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        # 2. Text report
        txt_path = output_dir / f"{self.file_id}.qc.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self.to_persian_text())


class QualityChecker:
    """Checks translated lines for non-Persian leftovers or anomalies."""

    def __init__(self, keep_terms: Optional[Set[str]] = None):
        self.keep_terms = keep_terms or set()

    def run_qc(
        self,
        subs: pysubs2.SSAFile,
        file_id: str,
        total_lines: int,
        translated_count: int,
        skipped_count: int,
        degraded_count: int,
        failed_count: int,
        api_calls: int,
        translatable_indices: Optional[Set[int]] = None,
    ) -> Tuple[QCReport, List[int]]:
        """Run QC check on translated subtitle events and return report and list of line indices needing re-translation."""
        flagged: List[FlaggedQCLine] = []
        indices_to_retranslate: List[int] = []

        for idx, event in enumerate(subs.events):
            if getattr(event, "is_comment", False):
                continue
            if translatable_indices is not None and idx not in translatable_indices:
                continue
            text = event.text or ""
            if not text.strip():
                continue

            if is_line_suspicious_non_persian(text, self.keep_terms):
                start_ts = pysubs2.time.ms_to_str(event.start)
                end_ts = pysubs2.time.ms_to_str(event.end)
                flagged.append(FlaggedQCLine(
                    line_index=idx,
                    start_time=start_ts,
                    end_time=end_ts,
                    source_text="",
                    translated_text=text,
                    reason="متن همچنان انگلیسی یا با درصد بالای حروف لاتین است",
                ))
                indices_to_retranslate.append(idx)

        report = QCReport(
            file_id=file_id,
            total_lines=total_lines,
            translated_count=translated_count,
            skipped_count=skipped_count,
            degraded_count=degraded_count,
            failed_count=failed_count,
            api_calls=api_calls,
            flagged_lines=flagged,
        )
        return report, indices_to_retranslate

