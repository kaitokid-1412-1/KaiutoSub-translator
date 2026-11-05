"""Overall translation pipeline coordinator."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from subtrans.core.config import Config, get_user_data_dir
from subtrans.core.context import ContextManager, extract_media_info
from subtrans.core.extract import (
    extract_subtitle_track,
    find_external_subtitle,
    is_subtitle_already_persian,
)
from subtrans.core.glossary import GlossaryManager
from subtrans.core.llm import QuotaExhaustedError
from subtrans.core.ocr import OcrTimeoutError, ocr_bitmap_subtitle
from subtrans.core.probe import choose_best_subtitle_track, probe_subtitles
from subtrans.core.store import TranslationStore
from subtrans.core.translate import BatchTranslator
from subtrans.core.writeout import get_output_path

VIDEO_EXTENSIONS = {".mkv", ".mp4"}
SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


class Stage(str, Enum):
    DISCOVER = "discover"
    EXTRACT = "extract"
    OCR = "ocr"
    CONTEXT = "context"
    TRANSLATE = "translate"
    QC = "qc"
    WRITE = "write"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class FileTask:
    path: Path
    is_video: bool
    stages: Dict[str, StageStatus] = field(default_factory=dict)
    messages: Dict[str, str] = field(default_factory=dict)
    output_path: Optional[Path] = None
    extracted_subtitle_path: Optional[Path] = None
    error: Optional[str] = None

    def set_stage(self, stage: Stage, status: StageStatus, message: str = ""):
        self.stages[stage.value] = status
        self.messages[stage.value] = message


def natural_sort_key(path: Path) -> List[Any]:
    """Sort filenames naturally (e.g. 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", path.name)]


def has_existing_translation(file_path: Path, target_lang: str = "fa") -> bool:
    """Check if target translation subtitle already exists next to video/sub."""
    parent = file_path.parent
    stem = file_path.stem
    for ext in ("srt", "ass", "ssa", "vtt"):
        target_name = f"{stem}.{target_lang}.{ext}"
        if (parent / target_name).is_file():
            return True
        plain_name = f"{stem}.{ext}"
        # If the file itself is the source, don't flag plain_name
        if file_path.suffix.lower().lstrip(".") != ext and (parent / plain_name).is_file():
            # Check if plain_name is already Persian
            if is_subtitle_already_persian(parent / plain_name):
                return True
    return False


def discover_inputs(
    path: Path,
    overwrite_existing: bool = False,
    target_lang: str = "fa",
) -> List[FileTask]:
    """Discover videos and subtitles recursively, skipping export dirs and existing translations."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"مسیر پیدا نشد: {path}")

    found_files: List[Path] = []

    if path.is_file():
        found_files = [path]
    else:
        for root, dirs, files in os.walk(path):
            # Ignore folders named Subtitles_Export_* or hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith("Subtitles_Export_") and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in VIDEO_EXTENSIONS or ext in SUBTITLE_EXTENSIONS:
                    found_files.append(Path(root) / f)

    # Sort naturally
    found_files.sort(key=natural_sort_key)

    tasks: List[FileTask] = []
    for fp in found_files:
        ext = fp.suffix.lower()
        # Skip if already a translated file (e.g. .fa.srt)
        if fp.name.lower().endswith(f".{target_lang}.srt") or fp.name.lower().endswith(f".{target_lang}.ass"):
            continue

        is_vid = ext in VIDEO_EXTENSIONS
        task = FileTask(path=fp, is_video=is_vid)

        # Initialize stages
        for st in Stage:
            task.stages[st.value] = StageStatus.PENDING

        task.set_stage(Stage.DISCOVER, StageStatus.SUCCESS, "فایل شناسایی شد")
        tasks.append(task)

    return tasks


class Pipeline:
    """Coordinates pipeline execution across files."""

    def __init__(self, config: Config, store: Optional[TranslationStore] = None):
        self.cfg = config
        self.store = store

    def run(
        self,
        input_path: Path,
        dry_run: bool = False,
        job_id: str = "default_job",
        on_event: Optional[Callable[[FileTask, Stage, StageStatus, str], None]] = None,
    ) -> List[FileTask]:
        """Execute translation pipeline over discovered files."""
        tasks = discover_inputs(
            input_path,
            overwrite_existing=self.cfg.general.overwrite_existing,
            target_lang=self.cfg.general.target_lang,
        )

        job_dir = get_user_data_dir() / "jobs" / job_id
        store = self.store or TranslationStore(job_dir=job_dir)
        translator = BatchTranslator(config=self.cfg, store=store)

        # M5: Series Context & Glossary
        context_mgr = ContextManager(cache_dir=job_dir, llm_client=translator.llm)
        glossary_mgr = GlossaryManager(base_dir=job_dir, llm_client=translator.llm)
        loaded_glossary = glossary_mgr.load_glossary(job_dir)
        prompt_glossary = loaded_glossary.to_prompt_dict() if loaded_glossary else None

        # Resolve series context once per series / job
        first_input_path = tasks[0].path if tasks else input_path
        media_info = extract_media_info(str(first_input_path))
        series_context = context_mgr.resolve_context(job_dir, media_info)
        series_prompt_text = series_context.to_prompt_text() if series_context else ""

        for task in tasks:
            def emit(st: Stage, status: StageStatus, msg: str):
                task.set_stage(st, status, msg)
                if on_event:
                    on_event(task, st, status, msg)

            # Check if output already exists
            if not self.cfg.general.overwrite_existing and has_existing_translation(task.path, self.cfg.general.target_lang):
                emit(Stage.EXTRACT, StageStatus.SKIPPED, "فایل ترجمه از قبل هست")
                emit(Stage.TRANSLATE, StageStatus.SKIPPED, "فایل ترجمه از قبل هست")
                continue

            sub_to_translate: Optional[Path] = None
            temp_extracted = False

            if task.is_video:
                emit(Stage.EXTRACT, StageStatus.RUNNING, "در حال بررسی و استخراج زیرنویس از ویدیو...")
                try:
                    tracks = probe_subtitles(task.path)
                    best_track = choose_best_subtitle_track(tracks, preferred_languages=self.cfg.extraction.source_languages)

                    if best_track:
                        if best_track.is_bitmap:
                            if not self.cfg.ocr.enabled:
                                emit(Stage.OCR, StageStatus.SKIPPED, "OCR غیرفعال است")
                                emit(Stage.EXTRACT, StageStatus.SKIPPED, "ترک تصویری نادیده گرفته شد")
                                continue

                            # Extract bitmap stream first (.sup / .sub)
                            emit(Stage.EXTRACT, StageStatus.RUNNING, f"استخراج ترک تصویری {best_track.index}...")
                            extracted_bitmap = extract_subtitle_track(task.path, best_track)
                            temp_extracted = True
                            emit(Stage.EXTRACT, StageStatus.SUCCESS, f"ترک تصویری استخراج شد: {extracted_bitmap.name}")

                            # Perform OCR
                            emit(Stage.OCR, StageStatus.RUNNING, "تبدیل زیرنویس تصویری به متن با OCR...")
                            try:
                                ocr_result = ocr_bitmap_subtitle(
                                    input_path=extracted_bitmap,
                                    timeout_seconds=self.cfg.ocr.timeout_seconds,
                                    subtitleedit_path=self.cfg.ocr.subtitleedit_path,
                                    ocr_engine=self.cfg.ocr.engine,
                                    use_gpu=self.cfg.ocr.use_gpu,
                                    language=self.cfg.ocr.language,
                                )
                                if ocr_result and ocr_result.exists():
                                    sub_to_translate = ocr_result
                                    emit(Stage.OCR, StageStatus.SUCCESS, "OCR با موفقیت انجام شد")
                                else:
                                    emit(Stage.OCR, StageStatus.FAILED, "OCR خروجی متنی تولید نکرد")
                                    continue
                            except OcrTimeoutError:
                                emit(Stage.OCR, StageStatus.FAILED, "زمان OCR به پایان رسید (Timeout) و رد شد")
                                continue
                            except FileNotFoundError as fnf_err:
                                emit(Stage.OCR, StageStatus.SKIPPED, str(fnf_err))
                                continue
                            except Exception as ocr_err:
                                emit(Stage.OCR, StageStatus.FAILED, f"خطا در OCR: {ocr_err}")
                                continue
                        else:
                            # Text track: extract
                            extracted = extract_subtitle_track(task.path, best_track)
                            task.extracted_subtitle_path = extracted
                            sub_to_translate = extracted
                            temp_extracted = True
                            emit(Stage.EXTRACT, StageStatus.SUCCESS, f"ترک {best_track.index} ({best_track.codec_name}) استخراج شد")
                    else:
                        # Check external subtitle
                        external = find_external_subtitle(task.path)
                        if external:
                            sub_to_translate = external
                            emit(Stage.EXTRACT, StageStatus.SUCCESS, f"زیرنویس خارجی پیدا شد: {external.name}")
                        else:
                            emit(Stage.EXTRACT, StageStatus.FAILED, "زیرنویسی در این ویدیو یا کنار آن پیدا نشد")
                            continue
                except Exception as e:
                    emit(Stage.EXTRACT, StageStatus.FAILED, f"خطا در استخراج: {e}")
                    task.error = str(e)
                    continue
            else:
                sub_to_translate = task.path
                emit(Stage.EXTRACT, StageStatus.SKIPPED, "ورودی خود زیرنویس است")

            # Check if subtitle is already Persian
            if self.cfg.extraction.skip_if_already_persian and is_subtitle_already_persian(sub_to_translate):
                emit(Stage.TRANSLATE, StageStatus.SKIPPED, "متن زیرنویس از قبل فارسی است")
                if temp_extracted and sub_to_translate.exists():
                    try:
                        sub_to_translate.unlink()
                    except Exception:
                        pass
                continue

            # Dry run check
            if dry_run:
                emit(Stage.TRANSLATE, StageStatus.SKIPPED, "محاسبه آزمایشی (Dry Run)")
                if temp_extracted and sub_to_translate.exists():
                    try:
                        sub_to_translate.unlink()
                    except Exception:
                        pass
                continue

            # Stage TRANSLATE
            emit(Stage.TRANSLATE, StageStatus.RUNNING, "در حال ترجمه زیرنویس...")
            try:
                # Target output
                target_ext = sub_to_translate.suffix.lstrip(".") if sub_to_translate else "srt"
                target_out = get_output_path(
                    source_path=task.path,
                    output_pattern=self.cfg.general.output_pattern,
                    target_lang=self.cfg.general.target_lang,
                    target_ext=target_ext,
                )

                def on_sub_progress(done: int, total: int, msg: str):
                    if on_event:
                        on_event(task, Stage.TRANSLATE, StageStatus.RUNNING, f"{msg} ({done}/{total})")

                emit(Stage.CONTEXT, StageStatus.SUCCESS, f"کانتکست: {series_context.title or 'عمومی'}")
                saved_path, rep = translator.translate_file(
                    subtitle_path=sub_to_translate,
                    output_path=target_out,
                    job_id=job_id,
                    series_context=series_prompt_text,
                    glossary=prompt_glossary,
                    progress_callback=on_sub_progress,
                )
                task.output_path = saved_path
                emit(Stage.TRANSLATE, StageStatus.SUCCESS, f"ترجمه موفق ({rep.translated_count} خط)")
                emit(Stage.QC, StageStatus.SUCCESS, f"QC پاس شد ({rep.qc_fixed_count} خط بازنویسی شد)")
                emit(Stage.WRITE, StageStatus.SUCCESS, f"ذخیره شد: {saved_path.name}")
            except QuotaExhaustedError as qe:
                # Quota pause rule (SPEC section 4.8 & 8)
                emit(Stage.TRANSLATE, StageStatus.FAILED, f"سهمیه یا محدودیت سرعت؛ پیشرفت ذخیره شد: {qe}")
                task.error = "PAUSED_QUOTA"
                break
            except Exception as e:
                emit(Stage.TRANSLATE, StageStatus.FAILED, f"خطا در ترجمه: {e}")
                task.error = str(e)
            finally:
                # Clean temp extracted file if created
                if temp_extracted and sub_to_translate and sub_to_translate.exists():
                    try:
                        sub_to_translate.unlink()
                    except Exception:
                        pass

        return tasks

