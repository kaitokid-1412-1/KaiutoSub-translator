"""Unit tests for Quality Control (QC) and report generation."""

from pathlib import Path
import pysubs2
from subtrans.core.qc import QualityChecker, is_line_suspicious_non_persian


def test_is_line_suspicious_non_persian():
    # Pure Persian: OK
    assert not is_line_suspicious_non_persian("سلام حال شما چطور است؟")

    # Mixed with more Persian: OK
    assert not is_line_suspicious_non_persian("این یک تست برای iPhone جدید است.")

    # Mostly English leftover: Suspicious
    assert is_line_suspicious_non_persian("This line was not translated at all.")
    assert is_line_suspicious_non_persian("Hello world!")

    # Excluded keep terms (e.g. character name "Spider-Man")
    assert not is_line_suspicious_non_persian("Spider-Man", keep_terms={"Spider-Man"})


def test_qc_pass_and_report_saving(tmp_path: Path):
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=1000, end=2000, text="سلام دنیا"))
    subs.append(pysubs2.SSAEvent(start=3000, end=4000, text="Wait a minute!"))

    qc = QualityChecker()
    report, flagged_indices = qc.run_qc(
        subs=subs,
        file_id="test_ep01.srt",
        total_lines=2,
        translated_count=2,
        skipped_count=0,
        degraded_count=0,
        failed_count=0,
        api_calls=1,
    )

    assert len(flagged_indices) == 1
    assert flagged_indices[0] == 1
    assert len(report.flagged_lines) == 1
    assert "Wait a minute!" in report.flagged_lines[0].translated_text

    # Save reports
    report.save(tmp_path)
    json_path = tmp_path / "test_ep01.srt.qc.json"
    txt_path = tmp_path / "test_ep01.srt.qc.txt"

    assert json_path.is_file()
    assert txt_path.is_file()

    txt_content = txt_path.read_text(encoding="utf-8")
    assert "گزارش کنترل کیفیت ترجمه" in txt_content
    assert "Wait a minute!" in txt_content
