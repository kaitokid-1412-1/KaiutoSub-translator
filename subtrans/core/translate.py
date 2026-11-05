"""Batch translation orchestrator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import pysubs2

from subtrans.core.config import Config
from subtrans.core.llm import FinishReasonLengthError, LLMClient, LLMClientError, QuotaExhaustedError
from subtrans.core.parse import (
    LineStatus,
    ParsedLine,
    classify_subtitles,
    load_subtitle,
)
from subtrans.core.protect import ProtectedLine, TagProtector
from subtrans.core.store import TranslationStore, compute_text_hash
from subtrans.core.writeout import get_output_path, write_subtitle_file

TONE_PRESETS = {
    "movie_tv": "لحن طبیعی و روان متناسب با فیلم و سریال (محاوره‌ای خوش‌خوان و استاندارد).",
    "anime": "لحن متناسب با انیمه و انیمیشن (بیان احساسی، پویا و صمیمی).",
    "documentary": "لحن رسمی، دقیق و علمی متناسب با مستند و گزارش‌ها.",
    "formal": "کاملاً رسمی، کتابی، فاخر و بدون کلمات شکسته.",
    "colloquial": "بسیار عامیانه، صمیمانه و روزمره با افعال شکسته.",
}


def extract_json_from_text(raw_text: str) -> Dict[str, Any]:
    """Robustly extract and parse JSON object from LLM response text."""
    text = raw_text.strip()

    # 1. Strip markdown fences if present
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(text)
    if match:
        text = match.group(1).strip()

    # 2. Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Find outermost curly braces { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        snippet = text[first_brace : last_brace + 1]
        try:
            data = json.loads(snippet)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"Could not extract valid JSON from response: {raw_text[:200]}")


@dataclass
class BatchItem:
    line_index: int
    payload_id: int
    source_event_text: str
    protected: ProtectedLine
    src_hash: str


@dataclass
class TranslationReport:
    file_id: str
    total_lines: int = 0
    translated_count: int = 0
    skipped_count: int = 0
    degraded_count: int = 0
    failed_count: int = 0
    cached_count: int = 0
    api_calls: int = 0
    total_tokens: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


class BatchTranslator:
    """Orchestrates batching, prompting, and retry logic."""

    def __init__(
        self,
        config: Config,
        llm_client: Optional[LLMClient] = None,
        store: Optional[TranslationStore] = None,
    ):
        self.cfg = config
        self.llm = llm_client or LLMClient(config.provider)
        self.protector = TagProtector()
        self.store = store

    def _build_system_prompt(
        self,
        series_context: str = "",
        glossary: Optional[Dict[str, str]] = None,
    ) -> str:
        tone_desc = TONE_PRESETS.get(self.cfg.translate.tone_preset, TONE_PRESETS["movie_tv"])
        parts = [
            "شما یک مترجم حرفه‌ای زیرنویس به زبان فارسی هستید.",
            f"سبک و لحن ترجمه: {tone_desc}",
        ]
        if series_context:
            parts.append(f"زمینه اثر/خلاصه: {series_context}")
        if glossary:
            glossary_lines = [f"- {k}: {v}" for k, v in glossary.items()]
            parts.append("واژه‌نامه و اسامی خاص (دقیقاً رعایت شود):\n" + "\n".join(glossary_lines))

        parts.extend([
            "قوانین بسیار مهم که نقض آن‌ها کل کار را باطل می‌کند:",
            "1. خروجی باید صرفاً یک آبجکت JSON معتبر به شکل {\"lines\": [{\"id\": ..., \"translated_text\": \"...\"}]} باشد.",
            "2. مقادیر id در خروجی باید دقیقاً با id ورودی مطابقت داشته باشد؛ هیچ خطی را ادغام یا تفکیک نکنید.",
            "3. نشانگرهای استایل مانند [[T1]], [[T2]] را دست‌نخورده در موقعیت منطقی داخل متن فارسی حفظ کنید.",
            "4. شکست خط‌ها (\\n) درون متن را دقیقاً حفظ کنید.",
            "5. از اضافه کردن هرگونه توضیح، سلام یا حاشیه‌نویسی خارج از JSON اکیداً خودداری کنید.",
        ])
        return "\n\n".join(parts)

    def _translate_batch_with_retry(
        self,
        batch: List[BatchItem],
        system_prompt: str,
        context_before: List[Tuple[str, str]],
        context_after: List[str],
    ) -> Dict[int, str]:
        """Translate a batch of items with halving and single-line fallback."""
        if not batch:
            return {}

        payload_lines = [{"id": item.payload_id, "text": item.protected.payload} for item in batch]
        user_message_parts = []

        if context_before:
            ctx_b_text = "\n".join([f"[قبل - فقط جهت زمینه] {src} => {trans}" for src, trans in context_before])
            user_message_parts.append(ctx_b_text)

        user_message_parts.append("خطوط زیر را ترجمه کن:")
        user_message_parts.append(json.dumps({"lines": payload_lines}, ensure_ascii=False))

        if context_after:
            ctx_a_text = "\n".join([f"[بعد - فقط جهت زمینه] {src}" for src in context_after])
            user_message_parts.append(ctx_a_text)

        user_message = "\n\n".join(user_message_parts)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Try translating batch
        try:
            resp = self.llm.chat_completion(
                messages=messages,
                temperature=self.cfg.translate.temperature,
                json_mode=True,
                max_attempts=self.cfg.retry.max_attempts,
                base_delay=float(self.cfg.retry.base_delay_seconds),
            )
            parsed_json = extract_json_from_text(resp.content)
            raw_lines = parsed_json.get("lines", [])

            # Validate returned lines
            returned_map: Dict[int, str] = {}
            for r in raw_lines:
                if isinstance(r, dict) and "id" in r and "translated_text" in r:
                    returned_map[int(r["id"])] = str(r["translated_text"])

            expected_ids = {item.payload_id for item in batch}
            # Check all expected ids present
            if expected_ids.issubset(returned_map.keys()):
                # Validate length ratio & tokens
                valid = True
                for item in batch:
                    trans = returned_map[item.payload_id]
                    src_len = max(len(item.protected.payload), 1)
                    if len(trans) > src_len * 4.5 and len(trans) > 50:
                        valid = False
                        break
                    if not self.protector.validate_tokens(trans, item.protected):
                        valid = False
                        break
                if valid:
                    return returned_map
        except (FinishReasonLengthError, QuotaExhaustedError):
            raise
        except Exception:
            pass

        # If batch > 1 and failed, split in half
        if len(batch) > 1:
            mid = len(batch) // 2
            left_res = self._translate_batch_with_retry(batch[:mid], system_prompt, context_before, [b.protected.payload for b in batch[mid:mid+2]])
            # update context_before for right side
            updated_ctx_b = context_before[-2:] + [(b.protected.payload, left_res.get(b.payload_id, "")) for b in batch[:mid][-2:]]
            right_res = self._translate_batch_with_retry(batch[mid:], system_prompt, updated_ctx_b, context_after)
            combined = {}
            combined.update(left_res)
            combined.update(right_res)
            return combined

        # Single item fallback failure
        item = batch[0]
        # Fallback: return source text as degraded/failed
        return {item.payload_id: item.protected.payload}

    def translate_file(
        self,
        subtitle_path: Path,
        output_path: Optional[Path] = None,
        job_id: str = "default_job",
        series_context: str = "",
        glossary: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Tuple[Path, TranslationReport]:
        """Translate a single subtitle file according to SPEC M1."""
        subs, fmt, encoding = load_subtitle(subtitle_path)
        is_ass = (fmt in ("ass", "ssa"))
        classified = classify_subtitles(
            subs,
            translate_signs_songs=self.cfg.translate.translate_signs_songs,
            translate_sdh_cues=self.cfg.translate.translate_sdh_cues,
        )

        file_id = subtitle_path.name
        report = TranslationReport(file_id=file_id, total_lines=len(classified))

        completed_store = self.store.get_completed_lines(file_id) if self.store else {}
        system_prompt = self._build_system_prompt(series_context, glossary)

        # Prepare translatable batches
        items_to_translate: List[BatchItem] = []
        payload_counter = 1

        # Local in-file deduplication cache
        in_file_cache: Dict[str, str] = {}

        # Track rolling context
        rolling_context_history: List[Tuple[str, str]] = []

        for line in classified:
            if line.status != LineStatus.TRANSLATABLE:
                report.skipped_count += 1
                continue

            src_hash = compute_text_hash(line.source_text)
            # 1. Resume check from store
            if line.line_index in completed_store:
                prev_hash, prev_text = completed_store[line.line_index]
                if prev_hash == src_hash:
                    subs.events[line.line_index].text = prev_text
                    report.cached_count += 1
                    rolling_context_history.append((line.plain_text, prev_text))
                    continue

            # 2. Global cache check
            if self.store:
                cached_trans = self.store.lookup_cache(line.plain_text, target_lang=self.cfg.general.target_lang)
                if cached_trans:
                    protected = self.protector.protect(line.source_text)
                    restored, _ = self.protector.restore(cached_trans, protected, is_ass=is_ass)
                    subs.events[line.line_index].text = restored
                    report.cached_count += 1
                    self.store.save_lines_batch([{
                        "file_id": file_id,
                        "idx": line.line_index,
                        "src_hash": src_hash,
                        "text": restored,
                        "status": "DONE",
                    }])
                    rolling_context_history.append((line.plain_text, restored))
                    continue

            # Protected representation
            protected = self.protector.protect(line.source_text)
            item = BatchItem(
                line_index=line.line_index,
                payload_id=payload_counter,
                source_event_text=line.source_text,
                protected=protected,
                src_hash=src_hash,
            )
            items_to_translate.append(item)
            payload_counter += 1

        # Chunk items into batches
        max_batch_lines = self.cfg.translate.batch_lines
        max_batch_chars = self.cfg.translate.batch_max_chars

        batches: List[List[BatchItem]] = []
        current_batch: List[BatchItem] = []
        current_chars = 0

        for item in items_to_translate:
            item_chars = len(item.protected.payload)
            if len(current_batch) >= max_batch_lines or (current_chars + item_chars > max_batch_chars and current_batch):
                batches.append(current_batch)
                current_batch = [item]
                current_chars = item_chars
            else:
                current_batch.append(item)
                current_chars += item_chars

        if current_batch:
            batches.append(current_batch)

        total_batches = len(batches)
        processed_lines = 0

        # Execute translation batch by batch
        for b_idx, batch in enumerate(batches):
            if progress_callback:
                msg = f"ترجمه دسته {b_idx + 1} از {total_batches}"
                progress_callback(processed_lines, len(items_to_translate), msg)

            # Rolling context
            ctx_before = rolling_context_history[-self.cfg.translate.context_before :]
            next_items = batches[b_idx + 1] if b_idx + 1 < total_batches else []
            ctx_after = [it.protected.payload for it in next_items[: self.cfg.translate.context_after]]

            # Deduplicate items in batch against in_file_cache
            untranslated_in_batch = []
            results_map: Dict[int, str] = {}

            for item in batch:
                if item.protected.payload in in_file_cache:
                    results_map[item.payload_id] = in_file_cache[item.protected.payload]
                    report.cached_count += 1
                else:
                    untranslated_in_batch.append(item)

            if untranslated_in_batch:
                batch_res = self._translate_batch_with_retry(
                    untranslated_in_batch,
                    system_prompt,
                    ctx_before,
                    ctx_after,
                )
                results_map.update(batch_res)

            # Process and restore each item
            lines_to_save = []
            for item in batch:
                trans_payload = results_map.get(item.payload_id, item.protected.payload)
                in_file_cache[item.protected.payload] = trans_payload

                restored_text, is_valid = self.protector.restore(trans_payload, item.protected, is_ass=is_ass)
                if not is_valid:
                    report.degraded_count += 1
                else:
                    report.translated_count += 1

                # Update subtitle event in memory
                subs.events[item.line_index].text = restored_text

                # Update context
                rolling_context_history.append((item.protected.payload, trans_payload))

                # Prepare DB record
                lines_to_save.append({
                    "file_id": file_id,
                    "idx": item.line_index,
                    "src_hash": item.src_hash,
                    "text": restored_text,
                    "status": "DONE",
                })

                # Global cache
                if self.store and is_valid:
                    self.store.save_to_cache(
                        src_text_norm=item.protected.payload,
                        translated_text=trans_payload,
                        target_lang=self.cfg.general.target_lang,
                    )

            # Commit to store after every batch (SPEC section 5)
            if self.store:
                self.store.save_lines_batch(lines_to_save)

            processed_lines += len(batch)

        # Output target path
        if output_path is None:
            output_path = get_output_path(
                source_path=subtitle_path,
                output_pattern=self.cfg.general.output_pattern,
                target_lang=self.cfg.general.target_lang,
            )

        saved_path = write_subtitle_file(
            subs=subs,
            output_path=output_path,
            encoding=self.cfg.general.srt_encoding if not is_ass else "utf-8",
            overwrite=self.cfg.general.overwrite_existing,
            format_=fmt,
        )

        report.api_calls = self.llm.call_count
        report.total_tokens = self.llm.total_tokens

        if progress_callback:
            progress_callback(len(items_to_translate), len(items_to_translate), "ترجمه کامل شد.")

        return saved_path, report

