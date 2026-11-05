"""Series context extraction, metadata resolution, and caching."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from guessit import guessit

from subtrans.core.llm import LLMClient


@dataclass
class MediaInfo:
    """Parsed media metadata from filename or explicit user input."""

    raw_title: str = ""
    title: str = ""
    season: Optional[int] = None
    episode: Optional[int] = None
    year: Optional[int] = None
    release_group: Optional[str] = None
    media_type: str = "unknown"  # 'episode', 'movie', etc.
    custom_synopsis: Optional[str] = None


@dataclass
class SeriesContext:
    """Cached narrative context for a series or movie to guide translation."""

    title: str = ""
    summary: str = ""
    tone: str = "movie_tv"
    characters: List[Dict[str, str]] = field(default_factory=list)
    notes: str = ""

    def to_prompt_text(self) -> str:
        """Render context as concise instructions for LLM system prompt."""
        parts = []
        if self.title:
            parts.append(f"نام اثر: {self.title}")
        if self.summary:
            parts.append(f"خلاصه داستان و تم اصلی: {self.summary}")
        if self.characters:
            char_lines = []
            for c in self.characters:
                name = c.get("name", "")
                gender = c.get("gender", "")
                role = c.get("role", "")
                desc = f"- {name}"
                if gender or role:
                    info = ", ".join(filter(None, [gender, role]))
                    desc += f" ({info})"
                char_lines.append(desc)
            if char_lines:
                parts.append("شخصیت‌های کلیدی (توجه به جنسیت در افعال و ضمایر فارسی):\n" + "\n".join(char_lines))
        if self.notes:
            parts.append(f"نکات ویژه: {self.notes}")
        return "\n".join(parts)


def extract_media_info(filename_or_path: str, custom_title: Optional[str] = None) -> MediaInfo:
    """Extract series title, season, and episode from filename using guessit."""
    path_obj = Path(filename_or_path)
    clean_name = path_obj.name

    try:
        parsed = guessit(clean_name)
    except Exception:
        parsed = {}

    title = custom_title or parsed.get("title") or path_obj.stem
    season = parsed.get("season")
    if isinstance(season, list):
        season = season[0] if season else None

    episode = parsed.get("episode")
    if isinstance(episode, list):
        episode = episode[0] if episode else None

    year = parsed.get("year")
    group = parsed.get("release_group")
    mtype = parsed.get("type", "unknown")

    return MediaInfo(
        raw_title=clean_name,
        title=str(title).strip(),
        season=season,
        episode=episode,
        year=year,
        release_group=group,
        media_type=str(mtype),
    )


class ContextManager:
    """Manages generation and caching of series_context.json in job/series directories."""

    CONTEXT_FILE_NAME = "series_context.json"

    def __init__(self, cache_dir: Optional[Path] = None, llm_client: Optional[LLMClient] = None):
        self.cache_dir = cache_dir
        self.llm = llm_client

    def _get_context_path(self, target_dir: Path) -> Path:
        if self.cache_dir:
            return self.cache_dir / self.CONTEXT_FILE_NAME
        return target_dir / self.CONTEXT_FILE_NAME

    def load_context(self, target_dir: Path) -> Optional[SeriesContext]:
        """Load cached series context from json if it exists."""
        ctx_file = self._get_context_path(target_dir)
        if not ctx_file.exists():
            return None

        try:
            with open(ctx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SeriesContext(
                title=data.get("title", ""),
                summary=data.get("summary", ""),
                tone=data.get("tone", "movie_tv"),
                characters=data.get("characters", []),
                notes=data.get("notes", ""),
            )
        except Exception:
            return None

    def save_context(self, target_dir: Path, context: SeriesContext) -> Path:
        """Save series context to disk."""
        target_dir.mkdir(parents=True, exist_ok=True)
        ctx_file = self._get_context_path(target_dir)
        data = asdict(context)
        with open(ctx_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return ctx_file

    def resolve_context(
        self,
        target_dir: Path,
        media_info: MediaInfo,
        force_refresh: bool = False,
    ) -> SeriesContext:
        """Get or generate series context for a project/folder."""
        if not force_refresh:
            cached = self.load_context(target_dir)
            if cached:
                return cached

        # If LLM client is available and title exists, generate context
        if self.llm and media_info.title:
            try:
                generated = self.generate_context_from_llm(media_info)
                self.save_context(target_dir, generated)
                return generated
            except Exception:
                pass

        # Fallback basic context without LLM call
        fallback = SeriesContext(
            title=media_info.title,
            summary=media_info.custom_synopsis or "",
            tone="movie_tv",
            characters=[],
            notes=f"نوع رسانه: {media_info.media_type}",
        )
        self.save_context(target_dir, fallback)
        return fallback

    def generate_context_from_llm(self, media_info: MediaInfo) -> SeriesContext:
        """Call LLM once per series to produce narrative context."""
        if not self.llm:
            raise ValueError("LLMClient is required to generate context")

        prompt = (
            f"عنوان اثر: {media_info.title}\n"
            f"نوع رسانه: {media_info.media_type}\n"
        )
        if media_info.year:
            prompt += f"سال ساخت: {media_info.year}\n"
        if media_info.custom_synopsis:
            prompt += f"توضیحات تکمیلی کاربر: {media_info.custom_synopsis}\n"

        prompt += (
            "\nلطفاً اطلاعات زیر را در قالب JSON برای راهنمایی مترجم استخراج کنید:\n"
            "1. خلاصه داستان بسیار کوتاه و تم اصلی (summary) به زبان فارسی (حداکثر ۲ یا ۳ جمله).\n"
            "2. لحن عمومی داستان (tone).\n"
            "3. لیست شخصیت‌های اصلی داستان (characters) شامل نام (name)، جنسیت (gender: مرد/زن/نامشخص) "
            "و نقش یا ویژگی کوتاه (role) برای انتخاب درست افعال و ضمایر در زبان فارسی.\n"
            "اگر این اثر را نمی‌شناسید یا اطلاعات موثقی ندارید، اصلاً حدس نزنید و فیلدها را خالی بگذارید.\n"
            "خروجی فقط و فقط یک آبجکت معتبر JSON با این کلیدها باشد:\n"
            '{"title": "...", "summary": "...", "tone": "...", "characters": [{"name": "...", "gender": "...", "role": "..."}], "notes": "..."}'
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "شما یک دستیار متخصص تولید کانتکست و متادیتای فیلم و سریال برای ترجمه دقیق زیرنویس هستید. "
                    "فقط پاسخ JSON معتبر بدون هیچ مارک‌داون یا متن اضافی تولید کنید."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        resp = self.llm.chat_completion(messages, temperature=0.2)
        content = resp.content.strip()

        # Parse JSON
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        try:
            data = json.loads(content)
        except Exception:
            data = {}

        return SeriesContext(
            title=data.get("title") or media_info.title,
            summary=data.get("summary", ""),
            tone=data.get("tone", "movie_tv"),
            characters=data.get("characters", []),
            notes=data.get("notes", ""),
        )

