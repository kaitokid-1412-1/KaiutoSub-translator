"""Command-line interface for SubTrans Auto."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from subtrans.core.config import Config, load_config
from subtrans.core.doctor import format_diagnostics_persian, run_diagnostics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m subtrans",
        description="SubTrans Auto - مترجم خودکار زیرنویس با هوش مصنوعی",
    )
    subparsers = parser.add_subparsers(dest="command", help="دستورات برنامه")

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="بررسی پیش‌نیازها و سلامت سیستم")

    # run
    run_parser = subparsers.add_parser("run", help="پردازش کامل ویدیوها یا پوشه زیرنویس")
    run_parser.add_argument("path", type=str, help="مسیر فایل ویدیو یا پوشه فصل")
    run_parser.add_argument("--dry-run", action="store_true", help="محاسبه تخمینی بدون فراخوانی واقعی API")
    run_parser.add_argument("--resume", type=str, default=None, help="شناسه عملیات (Job ID) برای ادامه کار")
    run_parser.add_argument("--overwrite", action="store_true", help="بازنویسی فایل‌های ترجمه موجود")

    # extract
    extract_parser = subparsers.add_parser("extract", help="استخراج زیرنویس از ویدیو")
    extract_parser.add_argument("path", type=str, help="مسیر فایل ویدیو یا پوشه")

    # translate
    translate_parser = subparsers.add_parser("translate", help="ترجمه مستقیم یک فایل زیرنویس")
    translate_parser.add_argument("subtitle", type=str, help="مسیر فایل زیرنویس (SRT/ASS/VTT)")

    # web
    web_parser = subparsers.add_parser("web", help="اجرای وب‌سرور محلی و رابط کاربری فارسی")
    web_parser.add_argument("--host", type=str, default="127.0.0.1", help="آدرس هاست محلی")
    web_parser.add_argument("--port", type=int, default=8765, help="پورت وب‌سرور")

    return parser


def handle_doctor(args: argparse.Namespace) -> int:
    cfg = load_config()
    items = run_diagnostics(cfg)
    report = format_diagnostics_persian(items)
    print(report)
    all_essential_ok = all(item.ok for item in items if item.name in ("ffmpeg", "ffprobe", "write_permission"))
    return 0 if all_essential_ok else 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "doctor":
        return handle_doctor(args)
    elif args.command == "run":
        print(f"اجرای پایپ‌لاین روی مسیر: {args.path} (در مایل‌استون‌های بعدی تکمیل می‌شود)")
        return 0
    elif args.command == "extract":
        print(f"استخراج زیرنویس از مسیر: {args.path} (در M3 پیاده‌سازی می‌شود)")
        return 0
    elif args.command == "translate":
        print(f"ترجمه فایل زیرنویس: {args.subtitle} (در M1 پیاده‌سازی می‌شود)")
        return 0
    elif args.command == "web":
        print(f"اجرای وب‌سرور روی http://{args.host}:{args.port} (در M4 پیاده‌سازی می‌شود)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
