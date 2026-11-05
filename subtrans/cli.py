"""Command-line interface for SubTrans Auto."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from subtrans.core.config import Config, get_user_data_dir, load_config
from subtrans.core.doctor import format_diagnostics_persian, run_diagnostics
from subtrans.core.extract import extract_subtitle_track
from subtrans.core.pipeline import FileTask, Pipeline, Stage, StageStatus, natural_sort_key
from subtrans.core.probe import choose_best_subtitle_track, probe_subtitles
from subtrans.core.store import TranslationStore
from subtrans.core.translate import BatchTranslator
from subtrans.web.server import run_server


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
    translate_parser.add_argument("--output", "-o", type=str, default=None, help="مسیر ذخیره فایل خروجی")
    translate_parser.add_argument("--tone", type=str, default=None, help="لحن ترجمه (movie_tv, anime, documentary, formal, colloquial)")
    translate_parser.add_argument("--job-id", type=str, default="cli_job", help="شناسه عملیات برای ذخیره سابقه")

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


def handle_translate(args: argparse.Namespace) -> int:
    sub_path = Path(args.subtitle)
    if not sub_path.is_file():
        print(f"[خطا] فایل زیرنویس پیدا نشد: {sub_path}")
        return 1

    cfg = load_config()
    if args.tone:
        cfg.translate.tone_preset = args.tone

    job_dir = get_user_data_dir() / "jobs" / args.job_id
    store = TranslationStore(job_dir=job_dir)
    translator = BatchTranslator(config=cfg, store=store)

    output_path = Path(args.output) if args.output else None

    def on_progress(done: int, total: int, msg: str):
        print(f"[{done}/{total}] {msg}")

    print(f"شروع ترجمه فایل: {sub_path.name}")
    try:
        out_file, rep = translator.translate_file(
            subtitle_path=sub_path,
            output_path=output_path,
            job_id=args.job_id,
            progress_callback=on_progress,
        )
        print("-----------------------------------")
        print(f"✔ فایل ترجمه‌شده با موفقیت ذخیره شد: {out_file}")
        print(f"تعداد کل خطوط: {rep.total_lines}")
        print(f"خطوط ترجمه شده: {rep.translated_count}")
        print(f"خطوط رد شده (استایل/توضیحات/فارسی): {rep.skipped_count}")
        print(f"خطوط از حافظه/کش: {rep.cached_count}")
        print(f"خطوط با استایل تقلیل‌یافته (Degraded): {rep.degraded_count}")
        print(f"تعداد درخواست‌های API: {rep.api_calls}")
        print(f"مجموع توکن‌ها: {rep.total_tokens}")
        return 0
    except Exception as e:
        print(f"[خطا در ترجمه] {e}")
        return 1


def handle_run(args: argparse.Namespace) -> int:
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"[خطا] مسیر مورد نظر پیدا نشد: {target_path}")
        return 1

    cfg = load_config()
    if args.overwrite:
        cfg.general.overwrite_existing = True

    job_id = args.resume or f"run_{target_path.stem}"
    pipeline = Pipeline(config=cfg)

    print(f"=== اجرای پایپ‌لاین روی: {target_path} ===")
    if args.dry_run:
        print("[حالت محاسبه آزمایشی - بدون کسر سهمیه]")

    def on_event(task: FileTask, stage: Stage, status: StageStatus, msg: str):
        icon = "✔" if status == StageStatus.SUCCESS else ("✘" if status == StageStatus.FAILED else ("⟳" if status == StageStatus.RUNNING else "⏭"))
        print(f"[{icon}] {task.path.name} | مرحله {stage.value}: {msg}")

    tasks = pipeline.run(
        input_path=target_path,
        dry_run=args.dry_run,
        job_id=job_id,
        on_event=on_event,
    )

    print("--------------------------------------------------")
    print(f"پردازش تمام شد. مجموع فایل‌های بررسی شده: {len(tasks)}")
    success_count = sum(1 for t in tasks if t.stages.get(Stage.WRITE.value) == StageStatus.SUCCESS or t.stages.get(Stage.TRANSLATE.value) == StageStatus.SUCCESS)
    skipped_count = sum(1 for t in tasks if any(st == StageStatus.SKIPPED for st in t.stages.values()) and not t.output_path)
    failed_count = sum(1 for t in tasks if any(st == StageStatus.FAILED for st in t.stages.values()))

    print(f"موفق: {success_count} | رد شده: {skipped_count} | خطا: {failed_count}")
    return 0 if failed_count == 0 else 1


def handle_extract(args: argparse.Namespace) -> int:
    target_path = Path(args.path)
    if not target_path.exists():
        print(f"[خطا] مسیر پیدا نشد: {target_path}")
        return 1

    files_to_probe: List[Path] = []
    if target_path.is_file():
        files_to_probe = [target_path]
    else:
        for f in target_path.iterdir():
            if f.is_file() and f.suffix.lower() in (".mkv", ".mp4"):
                files_to_probe.append(f)
        files_to_probe.sort(key=natural_sort_key)

    cfg = load_config()
    extracted_any = False

    for vid in files_to_probe:
        print(f"بررسی ویدیو: {vid.name}")
        tracks = probe_subtitles(vid)
        if not tracks:
            print(f"  [✘] هیچ ترک زیرنویسی در {vid.name} پیدا نشد.")
            continue

        best = choose_best_subtitle_track(tracks, preferred_languages=cfg.extraction.source_languages)
        if not best:
            print("  [✘] هیچ ترک مناسبی انتخاب نشد.")
            continue

        print(f"  [✔] انتخاب ترک {best.index} (زبان: {best.language}, کدک: {best.codec_name}, عنوان: {best.title or 'ندارد'})")
        try:
            out_path = extract_subtitle_track(vid, best)
            print(f"  -> استخراج شد در: {out_path.name}")
            extracted_any = True
        except Exception as e:
            print(f"  [خطا در استخراج] {e}")

    return 0 if extracted_any else 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "doctor":
        return handle_doctor(args)
    elif args.command == "run":
        return handle_run(args)
    elif args.command == "extract":
        return handle_extract(args)
    elif args.command == "translate":
        return handle_translate(args)
    elif args.command == "web":
        run_server(host=args.host, port=args.port, open_browser=True)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
