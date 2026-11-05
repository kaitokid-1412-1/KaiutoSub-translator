"""Tests for bitmap subtitle OCR and watchdog timeout handling."""

import sys
from pathlib import Path
import pytest

from subtrans.core.ocr import OcrTimeoutError, find_subtitleedit, ocr_bitmap_subtitle


def test_find_subtitleedit_custom_path(tmp_path: Path):
    fake_exe = tmp_path / "custom_se.exe"
    fake_exe.write_text("dummy", encoding="utf-8")
    found = find_subtitleedit(str(fake_exe))
    assert found == fake_exe


def test_ocr_missing_binary_raises_filenotfound(tmp_path: Path):
    fake_input = tmp_path / "test.sup"
    fake_input.write_bytes(b"dummy sup")
    with pytest.raises(FileNotFoundError) as exc_info:
        ocr_bitmap_subtitle(
            input_path=fake_input,
            subtitleedit_path=str(tmp_path / "non_existent_binary.exe"),
        )
    assert "SubtitleEdit" in str(exc_info.value)
    assert "winget" in str(exc_info.value)


def test_ocr_watchdog_kills_hung_process(tmp_path: Path):
    """SPEC 10 & Definition of Done: OCR watchdog ends a hung process within timeout + 5s."""
    # Create a fake slow python script that sleeps for 15 seconds
    script_file = tmp_path / "hung_ocr.py"
    script_file.write_text(
        "import time, sys\ntime.sleep(15)\nsys.exit(0)\n",
        encoding="utf-8",
    )

    fake_sup = tmp_path / "sample.sup"
    fake_sup.write_bytes(b"dummy")

    # Run with 1 second timeout using python script as the binary
    with pytest.raises(OcrTimeoutError) as exc_info:
        ocr_bitmap_subtitle(
            input_path=fake_sup,
            timeout_seconds=1,
            subtitleedit_path=str(script_file),
        )

    assert "Timeout" in str(exc_info.value)
    assert "sample.sup" in str(exc_info.value)


def test_ocr_successful_simulated_run(tmp_path: Path):
    """Test successful run with a mock CLI that creates the output srt file."""
    # Write a script that writes the target .srt file
    script_file = tmp_path / "mock_se.py"
    # When called with /outputfilename:path or arguments, it creates an srt file
    script_content = (
        "import sys\n"
        "from pathlib import Path\n"
        "for arg in sys.argv:\n"
        "    if arg.startswith('/outputfilename:'):\n"
        "        out = Path(arg.split(':', 1)[1])\n"
        "        out.write_text('1\\n00:00:01,000 --> 00:00:04,000\\nHello world\\n', encoding='utf-8')\n"
        "sys.exit(0)\n"
    )
    script_file.write_text(script_content, encoding="utf-8")

    fake_sup = tmp_path / "sample.sup"
    fake_sup.write_bytes(b"dummy sup")
    target_srt = tmp_path / "sample.ocr.srt"

    res = ocr_bitmap_subtitle(
        input_path=fake_sup,
        output_path=target_srt,
        timeout_seconds=10,
        subtitleedit_path=str(script_file),
    )

    assert res is not None
    assert res.exists()
    assert "Hello world" in res.read_text(encoding="utf-8")
