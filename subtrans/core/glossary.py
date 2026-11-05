"""Glossary management for consistent translation across episodes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from subtrans.core.llm import LLMClient


@dataclass
class GlossaryEntry:
    """A term or name in the glossary."""

    term: str
    translation: str
    action: str = "transliterate"  # 'transliterate', 'keep', 'translate'
    notes: str = ""


@dataclass
class Glossary:
    """Container for glossary terms, keep-names, and free notes."""

    terms: Dict[str, str] = field(default_factory=dict)  # "Walter White": "والتر وایت"
    keep_terms: List[str] = field(default_factory=list)  # ["FBI", "NASA", "iPhone"]
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "terms": self.terms,
            "keep_terms": self.keep_terms,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Glossary:
        return cls(
            terms=data.get("terms", {}),
            keep_terms=data.get("keep_terms", []),
            notes=data.get("notes", ""),
        )

    def to_prompt_dict(self) -> Dict[str, str]:
        """Produce dictionary suitable for translation prompt."""
        res = dict(self.terms)
        for k in self.keep_terms:
            if k not in res:
                res[k] = k  # Kept as original
        return res


class GlossaryManager:
    """Manages project and series-level glossaries."""

    GLOSSARY_FILE_NAME = "glossary.json"

    def __init__(self, base_dir: Optional[Path] = None, llm_client: Optional[LLMClient] = None):
        self.base_dir = base_dir
        self.llm = llm_client

    def _get_glossary_path(self, target_dir: Path) -> Path:
        if self.base_dir:
            return self.base_dir / self.GLOSSARY_FILE_NAME
        return target_dir / self.GLOSSARY_FILE_NAME

    def load_glossary(self, target_dir: Path) -> Glossary:
        """Load glossary from target directory or return empty one."""
        gpath = self._get_glossary_path(target_dir)
        if not gpath.exists():
            return Glossary()

        try:
            with open(gpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Glossary.from_dict(data)
        except Exception:
            return Glossary()

    def save_glossary(self, target_dir: Path, glossary: Glossary) -> Path:
        """Save glossary to JSON."""
        target_dir.mkdir(parents=True, exist_ok=True)
        gpath = self._get_glossary_path(target_dir)
        with open(gpath, "w", encoding="utf-8") as f:
            json.dump(glossary.to_dict(), f, ensure_ascii=False, indent=2)
        return gpath

    def update_terms(self, target_dir: Path, new_terms: Dict[str, str]) -> Glossary:
        """Add or update terms in glossary."""
        glossary = self.load_glossary(target_dir)
        glossary.terms.update(new_terms)
        self.save_glossary(target_dir, glossary)
        return glossary

    def extract_names_from_subtitles(
        self,
        target_dir: Path,
        subtitle_lines: List[str],
        sample_size: int = 100,
    ) -> Dict[str, str]:
        """Optionally analyze lines to extract proper names and suggest Persian spellings."""
        if not self.llm or not subtitle_lines:
            return {}

        sample = subtitle_lines[:sample_size]
        text_block = "\n".join(sample[:50])

        prompt = (
            "متن زیر بخشی از زیرنویس یک فیلم/سریال است. لطفاً اسامی خاص اشخاص، مکان‌ها، یا عناوین پرتکرار "
            "را پیدا کنید و معادل استاندارد یا آوانگاری مناسب آن‌ها به فارسی را بنویسید.\n\n"
            f"{text_block}\n\n"
            "خروجی فقط و فقط یک آبجکت معتبر JSON به صورت زیر باشد بدون هیچ متن یا توضیح اضافی:\n"
            '{"names": {"Walter": "والتر", "Albuquerque": "البوکرکی"}}'
        )

        messages = [
            {
                "role": "system",
                "content": "شما استخراج‌کننده اسامی خاص و واژه‌نامه برای هماهنگی زیرنویس هستید. خروجی فقط JSON باشد.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            resp = self.llm.chat_completion(messages, temperature=0.1)
            content = resp.content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            parsed = json.loads(content)
            extracted = parsed.get("names", {})
            if isinstance(extracted, dict):
                # Update disk glossary
                self.update_terms(target_dir, extracted)
                return extracted
        except Exception:
            pass

        return {}

