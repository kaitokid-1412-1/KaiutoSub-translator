"""Unit tests for M5: guessit metadata, series context caching, and glossary."""

import json
from pathlib import Path
import pytest

from subtrans.core.config import Config
from subtrans.core.context import (
    ContextManager,
    MediaInfo,
    SeriesContext,
    extract_media_info,
)
from subtrans.core.glossary import Glossary, GlossaryManager
from subtrans.core.translate import DEFAULT_TONE_PRESETS, load_tone_presets


def test_extract_media_info_fansub_anime():
    filename = "[SubsPlease] Sousou no Frieren - 05 (1080p) [ABCD1234].mkv"
    info = extract_media_info(filename)
    assert info.title == "Sousou no Frieren"
    assert info.episode == 5
    assert info.release_group == "SubsPlease"


def test_extract_media_info_tv_series():
    filename = "Breaking.Bad.S01E03.1080p.BluRay.x264.mkv"
    info = extract_media_info(filename)
    assert info.title == "Breaking Bad"
    assert info.season == 1
    assert info.episode == 3


def test_series_context_prompt_formatting():
    ctx = SeriesContext(
        title="Frieren",
        summary="داستان یک الف جادوگر پس از شکست پادشاه شیاطین.",
        tone="anime",
        characters=[
            {"name": "Frieren", "gender": "زن", "role": "جادوگر الف"},
            {"name": "Himmel", "gender": "مرد", "role": "قهرمان شجاع"},
        ],
        notes="لحن احساسی و صمیمی",
    )
    prompt_text = ctx.to_prompt_text()
    assert "Frieren" in prompt_text
    assert "زن" in prompt_text
    assert "Himmel" in prompt_text
    assert "مرد" in prompt_text


def test_context_manager_save_and_load(tmp_path: Path):
    mgr = ContextManager(cache_dir=tmp_path)
    ctx = SeriesContext(
        title="Test Movie",
        summary="A movie summary",
        tone="formal",
        characters=[{"name": "Alice", "gender": "زن"}],
    )
    saved_file = mgr.save_context(tmp_path, ctx)
    assert saved_file.exists()

    loaded = mgr.load_context(tmp_path)
    assert loaded is not None
    assert loaded.title == "Test Movie"
    assert loaded.tone == "formal"
    assert len(loaded.characters) == 1
    assert loaded.characters[0]["name"] == "Alice"


def test_glossary_save_load_and_prompt_dict(tmp_path: Path):
    mgr = GlossaryManager(base_dir=tmp_path)
    glossary = Glossary(
        terms={"Walter": "والتر", "Jesse": "جسی"},
        keep_terms=["DEA", "FBI"],
        notes="برکینگ بد",
    )
    mgr.save_glossary(tmp_path, glossary)

    loaded = mgr.load_glossary(tmp_path)
    assert loaded.terms["Walter"] == "والتر"
    assert "DEA" in loaded.keep_terms

    prompt_dict = loaded.to_prompt_dict()
    assert prompt_dict["Walter"] == "والتر"
    assert prompt_dict["DEA"] == "DEA"


def test_glossary_update_terms(tmp_path: Path):
    mgr = GlossaryManager(base_dir=tmp_path)
    mgr.update_terms(tmp_path, {"Hank": "هنک"})
    loaded = mgr.load_glossary(tmp_path)
    assert loaded.terms.get("Hank") == "هنک"

    mgr.update_terms(tmp_path, {"Skyler": "اسکایلر"})
    loaded2 = mgr.load_glossary(tmp_path)
    assert loaded2.terms.get("Hank") == "هنک"
    assert loaded2.terms.get("Skyler") == "اسکایلر"


def test_load_tone_presets(tmp_path: Path):
    presets = load_tone_presets(tmp_path)
    assert "movie_tv" in presets
    assert "anime" in presets
    assert "documentary" in presets

    # Check that text files were created on disk
    anime_file = tmp_path / "anime.txt"
    assert anime_file.exists()
    assert len(anime_file.read_text(encoding="utf-8")) > 0

    # Test editing an existing preset text file
    anime_file.write_text("لحن انیمه‌ای ویرایش شده و خاص", encoding="utf-8")
    reloaded = load_tone_presets(tmp_path)
    assert reloaded["anime"] == "لحن انیمه‌ای ویرایش شده و خاص"
