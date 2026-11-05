"""Unit tests for SQLite state store and global cache."""

from pathlib import Path
from subtrans.core.store import TranslationStore, compute_text_hash


def test_translation_store_batch_and_resume(tmp_path: Path):
    job_dir = tmp_path / "job_test"
    store = TranslationStore(job_dir=job_dir, global_cache_dir=tmp_path)

    file_id = "episode1.srt"
    batch_lines = [
        {"file_id": file_id, "idx": 0, "src_hash": compute_text_hash("Hello"), "text": "سلام", "status": "DONE"},
        {"file_id": file_id, "idx": 1, "src_hash": compute_text_hash("World"), "text": "دنیا", "status": "DONE"},
    ]
    store.save_lines_batch(batch_lines)

    completed = store.get_completed_lines(file_id)
    assert len(completed) == 2
    assert completed[0][1] == "سلام"
    assert completed[1][1] == "دنیا"


def test_global_cache(tmp_path: Path):
    store = TranslationStore(job_dir=tmp_path / "job", global_cache_dir=tmp_path)

    # Cache miss
    assert store.lookup_cache("Good morning") is None

    # Cache save and hit
    store.save_to_cache("Good morning", "صبح بخیر")
    hit = store.lookup_cache("Good morning")
    assert hit == "صبح بخیر"
