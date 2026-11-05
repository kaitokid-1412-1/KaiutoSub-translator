"""SQLite storage for job progress, resumable state, and global cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from subtrans.core.config import get_user_data_dir


def compute_text_hash(text: str) -> str:
    """Compute MD5 or SHA256 hex digest for text."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


class TranslationStore:
    """Manages translations.sqlite and global cache.sqlite."""

    def __init__(self, job_dir: Path, global_cache_dir: Optional[Path] = None):
        self.job_dir = Path(job_dir)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.job_dir / "translations.sqlite"
        self.job_json_path = self.job_dir / "job.json"

        cache_base = global_cache_dir if global_cache_dir else get_user_data_dir()
        cache_base.mkdir(parents=True, exist_ok=True)
        self.cache_db_path = cache_base / "cache.sqlite"

        self._init_db()
        self._init_cache_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lines (
                    file_id TEXT,
                    idx INTEGER,
                    src_hash TEXT,
                    text TEXT,
                    status TEXT,
                    attempts INTEGER,
                    updated_at REAL,
                    PRIMARY KEY (file_id, idx)
                );
            """)
            conn.commit()

    def _init_cache_db(self):
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_cache (
                    src_text_norm TEXT,
                    glossary_hash TEXT,
                    target_lang TEXT,
                    prompt_version TEXT,
                    translated_text TEXT,
                    created_at REAL,
                    PRIMARY KEY (src_text_norm, glossary_hash, target_lang, prompt_version)
                );
            """)
            conn.commit()

    def save_lines_batch(self, lines: List[Dict[str, Any]]):
        """Save a batch of translated lines and commit atomically."""
        if not lines:
            return
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for item in lines:
                cursor.execute("""
                    INSERT INTO lines (file_id, idx, src_hash, text, status, attempts, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(file_id, idx) DO UPDATE SET
                        src_hash=excluded.src_hash,
                        text=excluded.text,
                        status=excluded.status,
                        attempts=excluded.attempts,
                        updated_at=excluded.updated_at;
                """, (
                    item["file_id"],
                    item["idx"],
                    item["src_hash"],
                    item["text"],
                    item["status"],
                    item.get("attempts", 1),
                    now,
                ))
            conn.commit()

    def get_completed_lines(self, file_id: str) -> Dict[int, Tuple[str, str]]:
        """Get all lines with status DONE for resume checks.
        
        Returns dict: idx -> (src_hash, text).
        """
        result = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT idx, src_hash, text FROM lines
                WHERE file_id = ? AND status = 'DONE';
            """, (file_id,))
            for idx, s_hash, text in cursor.fetchall():
                result[idx] = (s_hash, text)
        return result

    def lookup_cache(
        self,
        src_text_norm: str,
        glossary_hash: str = "",
        target_lang: str = "fa",
        prompt_version: str = "1",
    ) -> Optional[str]:
        """Look up translation from global cache."""
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT translated_text FROM global_cache
                WHERE src_text_norm = ? AND glossary_hash = ? AND target_lang = ? AND prompt_version = ?;
            """, (src_text_norm.strip(), glossary_hash, target_lang, prompt_version))
            row = cursor.fetchone()
            return row[0] if row else None

    def save_to_cache(
        self,
        src_text_norm: str,
        translated_text: str,
        glossary_hash: str = "",
        target_lang: str = "fa",
        prompt_version: str = "1",
    ):
        """Save translation to global cache."""
        now = time.time()
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO global_cache
                (src_text_norm, glossary_hash, target_lang, prompt_version, translated_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (src_text_norm.strip(), glossary_hash, target_lang, prompt_version, translated_text, now))
            conn.commit()

    def save_job_state(self, job_data: Dict[str, Any]):
        """Save job.json snapshot."""
        with open(self.job_json_path, "w", encoding="utf-8") as f:
            json.dump(job_data, f, indent=2, ensure_ascii=False)

    def load_job_state(self) -> Optional[Dict[str, Any]]:
        """Load job.json if exists."""
        if self.job_json_path.is_file():
            try:
                with open(self.job_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

