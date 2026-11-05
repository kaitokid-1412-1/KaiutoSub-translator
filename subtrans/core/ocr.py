"""OCR pipeline for bitmap subtitles (PGS/VobSub) using SubtitleEdit CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def find_subtitleedit(custom_path: str = "") -> Optional[Path]:
    """Find SubtitleEdit or seconv executable on Windows/POSIX."""
    if custom_path:
        p = Path(custom_path)
        if p.is_file():
            return p
        return None

    # 1. System PATH
    for name in ["seconv", "SubtitleEdit", "subtitleedit"]:
        found = shutil.which(name)
        if found:
            return Path(found)

    # 2. Windows typical install directories
    if sys.platform == "win32":
        candidates = []
        for pf in [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")]:
            if pf:
                candidates.extend([
                    Path(pf) / "Subtitle Edit" / "SubtitleEdit.exe",
                    Path(pf) / "Subtitle Edit" / "seconv.exe",
                    Path(pf) / "SubtitleEdit" / "SubtitleEdit.exe",
                    Path(pf) / "SubtitleEdit" / "seconv.exe",
                    Path(pf) / "Programs" / "Subtitle Edit" / "SubtitleEdit.exe",
                ])
        for cand in candidates:
            if cand.is_file():
                return cand

    return None


class OcrTimeoutError(TimeoutError):
    """Raised when OCR execution exceeds watchdog timeout."""
    pass


def ocr_bitmap_subtitle(
    input_path: Path,
    output_path: Optional[Path] = None,
    timeout_seconds: int = 180,
    subtitleedit_path: str = "",
    ocr_engine: str = "paddleocr",
    use_gpu: bool = True,
    language: str = "en",
) -> Optional[Path]:
    """Perform OCR on bitmap subtitles (e.g. .sup, .sub) with watchdog process termination.
    
    Supports PaddleOCR (GPU / normal CPU version) via SubtitleEdit / seconv or direct execution.
    If SubtitleEdit is unavailable or timeout occurs, raises appropriate exceptions.
    """
    se_bin = find_subtitleedit(subtitleedit_path)
    if not se_bin:
        raise FileNotFoundError(
            "ابزار SubtitleEdit برای تبدیل زیرنویس‌های تصویری (OCR) پیدا نشد. "
            "می‌توانید با دستور 'winget install Nikse.SubtitleEdit' آن را نصب کنید."
        )

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}.ocr.srt"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    is_seconv = "seconv" in se_bin.name.lower()
    is_script = se_bin.suffix.lower() in (".py", ".bat", ".cmd", ".sh")

    # Map engine name to SubtitleEdit / seconv parameters
    # PaddleOCR engine alias is 'paddle' in seconv
    engine_arg = "paddle" if ocr_engine.lower() in ("paddleocr", "paddle") else ocr_engine.lower()

    # Pass environment variables for Paddle GPU / CPU selection
    env = os.environ.copy()
    if use_gpu:
        env["FLAGS_selected_gpus"] = "0"
        env["PADDLE_OCR_USE_GPU"] = "1"
    else:
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["PADDLE_OCR_USE_GPU"] = "0"

    if is_script:
        if se_bin.suffix.lower() == ".py":
            cmd = [
                sys.executable,
                str(se_bin),
                "/convert",
                str(input_path),
                "subrip",
                f"/ocrengine:{engine_arg}",
                "/overwrite",
                f"/outputfilename:{output_path}",
            ]
        else:
            cmd = [
                str(se_bin),
                "/convert",
                str(input_path),
                "subrip",
                f"/outputfilename:{output_path}",
            ]
    elif is_seconv:
        # Modern seconv CLI
        cmd = [
            str(se_bin),
            str(input_path),
            "subrip",
            f"--ocr-engine:{engine_arg}",
            f"--ocr-language:{language}",
            "--overwrite",
            f"--output-filename:{output_path.name}",
            f"--output-folder:{output_path.parent}",
        ]
    else:
        # Classic SubtitleEdit.exe CLI
        cmd = [
            str(se_bin),
            "/convert",
            str(input_path),
            "subrip",
            f"/ocrengine:{engine_arg}",
            "/overwrite",
            f"/outputfilename:{output_path}",
        ]

    # Run with watchdog subprocess termination
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        # Kill whole process tree
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise OcrTimeoutError(
            f"عملیات OCR برای فایل {input_path.name} پس از {timeout_seconds} ثانیه متوقف شد (Timeout)."
        )

    if proc.returncode != 0 and not output_path.exists():
        raise RuntimeError(
            f"خطا در اجرای OCR توسط SubtitleEdit (کد خروج {proc.returncode}): {stderr or stdout}"
        )

    if output_path.exists():
        return output_path

    # Sometimes SE writes without .ocr prefix; check fallback
    default_out = input_path.parent / f"{input_path.stem}.srt"
    if default_out.exists():
        return default_out

    return None

