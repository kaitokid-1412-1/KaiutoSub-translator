"""System diagnostics and health checks for SubTrans Auto."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from subtrans.core.config import Config, load_config, get_user_data_dir


@dataclass
class DiagnosticItem:
    name: str
    ok: bool
    persian_title: str
    message: str
    fix_suggestion: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


def check_ffmpeg() -> DiagnosticItem:
    """Check if ffmpeg is available in PATH."""
    path = shutil.which("ffmpeg")
    if path:
        return DiagnosticItem(
            name="ffmpeg",
            ok=True,
            persian_title="ابزار FFmpeg",
            message=f"نصب است ({path})",
        )
    return DiagnosticItem(
        name="ffmpeg",
        ok=False,
        persian_title="ابزار FFmpeg",
        message="FFmpeg پیدا نشد. برای استخراج زیرنویس از ویدیوها ضروری است.",
        fix_suggestion="در ترمینال یا پاورشل اجرا کن: winget install Gyan.FFmpeg سپس سیستم را ری‌استارت یا پنجره ترمینال را دوباره باز کن.",
    )


def check_ffprobe() -> DiagnosticItem:
    """Check if ffprobe is available in PATH."""
    path = shutil.which("ffprobe")
    if path:
        return DiagnosticItem(
            name="ffprobe",
            ok=True,
            persian_title="ابزار FFprobe",
            message=f"نصب است ({path})",
        )
    return DiagnosticItem(
        name="ffprobe",
        ok=False,
        persian_title="ابزار FFprobe",
        message="FFprobe پیدا نشد. برای شناسایی ترک‌های ویدیویی لازم است.",
        fix_suggestion="همراه با FFmpeg نصب می‌شود: winget install Gyan.FFmpeg",
    )


def check_subtitle_edit(custom_path: str = "") -> DiagnosticItem:
    """Check if SubtitleEdit CLI is available (optional, for OCR)."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    which_path = shutil.which("SubtitleEdit") or shutil.which("subtitleedit")
    if which_path:
        candidates.append(Path(which_path))

    # Common Windows install locations
    program_files = [os.environ.get("ProgramFiles", "C:\\Program Files"),
                     os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")]
    for pf in program_files:
        if pf:
            candidates.append(Path(pf) / "Subtitle Edit" / "SubtitleEdit.exe")
            candidates.append(Path(pf) / "SubtitleEdit" / "SubtitleEdit.exe")

    found_path = None
    for cand in candidates:
        if cand and cand.is_file():
            found_path = cand
            break

    if found_path:
        return DiagnosticItem(
            name="subtitle_edit",
            ok=True,
            persian_title="ابزار SubtitleEdit (OCR)",
            message=f"نصب است ({found_path})",
        )
    return DiagnosticItem(
        name="subtitle_edit",
        ok=True,  # Optional, so we treat it as non-blocking but informative
        persian_title="ابزار SubtitleEdit (OCR)",
        message="پیدا نشد (اختیاری: فقط برای تبدیل زیرنویس‌های تصویری/PGS نیاز است).",
        fix_suggestion="اگر می‌خواهی زیرنویس‌های تصویری را OCR کنی، می‌توانی با دستور winget install Nikse.SubtitleEdit آن را نصب کنی.",
    )


def check_write_permission() -> DiagnosticItem:
    """Check write access in user data directory and current working directory."""
    data_dir = get_user_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".write_test.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return DiagnosticItem(
            name="write_permission",
            ok=True,
            persian_title="دسترسی نوشتن فایل",
            message=f"دسترسی در پوشه ذخیره‌سازی داده برقرار است ({data_dir}).",
        )
    except Exception as e:
        return DiagnosticItem(
            name="write_permission",
            ok=False,
            persian_title="دسترسی نوشتن فایل",
            message=f"خطا در ایجاد فایل در {data_dir}: {e}",
            fix_suggestion="بررسی کن که دسترسی نوشتن برای پوشه کاربر فعال باشد.",
        )


def check_gateway(cfg: Optional[Config] = None) -> DiagnosticItem:
    """Check connectivity to LLM provider gateway and model listing."""
    if cfg is None:
        cfg = load_config()

    base_url = cfg.provider.base_url.rstrip("/")
    if not base_url:
        return DiagnosticItem(
            name="gateway",
            ok=False,
            persian_title="اتصال به گیت‌وی هوش مصنوعی",
            message="آدرس سرور مشخص نشده است.",
            fix_suggestion="در تنظیمات، آدرس provider.base_url را تنظیم کن.",
        )

    # Note: local URLs must not be routed through system proxy (Section 2)
    is_local = "127.0.0.1" in base_url or "localhost" in base_url
    headers = {}
    if cfg.provider.api_key:
        headers["Authorization"] = f"Bearer {cfg.provider.api_key}"

    # Try /models or /v1/models
    models_url = f"{base_url}/models"
    try:
        with httpx.Client(timeout=5.0, trust_env=not is_local) as client:
            resp = client.get(models_url, headers=headers)
            if resp.status_code == 200:
                models_data = resp.json()
                models_list = []
                if isinstance(models_data, dict) and "data" in models_data:
                    models_list = [m.get("id") for m in models_data.get("data", []) if isinstance(m, dict)]
                return DiagnosticItem(
                    name="gateway",
                    ok=True,
                    persian_title="اتصال به گیت‌وی هوش مصنوعی",
                    message=f"اتصال با موفقیت برقرار شد ({len(models_list)} مدل یافت شد).",
                    details={"models": models_list},
                )
            elif resp.status_code in (401, 403):
                return DiagnosticItem(
                    name="gateway",
                    ok=False,
                    persian_title="اتصال به گیت‌وی هوش مصنوعی",
                    message=f"کلید API نامعتبر است یا دسترسی مجاز نیست (کد {resp.status_code}).",
                    fix_suggestion="کلید API را در تنظیمات بررسی و تصحیح کن.",
                )
            else:
                return DiagnosticItem(
                    name="gateway",
                    ok=False,
                    persian_title="اتصال به گیت‌وی هوش مصنوعی",
                    message=f"پاسخ سرور ناموفق بود (کد وضعیت: {resp.status_code}).",
                    fix_suggestion=f"آدرس {base_url} را بررسی کن و مطمئن شو سرور مدل روشن است.",
                )
    except Exception as e:
        return DiagnosticItem(
            name="gateway",
            ok=False,
            persian_title="اتصال به گیت‌وی هوش مصنوعی",
            message=f"امکان اتصال به {base_url} وجود ندارد ({type(e).__name__}).",
            fix_suggestion="مطمئن شو 9Router یا سرور مدل روشن است و آدرس سرور در تنظیمات درست وارد شده است.",
        )


def run_diagnostics(cfg: Optional[Config] = None) -> List[DiagnosticItem]:
    """Run all diagnostics and return findings."""
    if cfg is None:
        cfg = load_config()

    items = [
        check_ffmpeg(),
        check_ffprobe(),
        check_subtitle_edit(cfg.ocr.subtitleedit_path),
        check_write_permission(),
        check_gateway(cfg),
    ]
    return items


def format_diagnostics_persian(items: List[DiagnosticItem]) -> str:
    """Format diagnostic results in Persian for CLI display."""
    lines = ["=== گزارش سلامت سیستم (Doctor) ==="]
    all_ok = True
    for item in items:
        status_icon = "✔" if item.ok else "✘"
        status_label = "تایید" if item.ok else "خطا"
        lines.append(f"[{status_icon}] {item.persian_title}: {item.message}")
        if not item.ok:
            all_ok = False
            if item.fix_suggestion:
                lines.append(f"    راه حل پیشنهادی: {item.fix_suggestion}")
        elif item.fix_suggestion:
            lines.append(f"    نکته: {item.fix_suggestion}")

    lines.append("-----------------------------------")
    if all_ok:
        lines.append("همه نیازمندی‌های اصلی فراهم است. سیستم آماده به کار است.")
    else:
        lines.append("برخی نیازمندی‌ها ناقص است. لطفاً موارد خطادار را بررسی کن.")
    return "\n".join(lines)
