"""Unit and integration tests for media probing, subtitle extraction, and full video pipeline."""

import shutil
from pathlib import Path
import pytest

from subtrans.core.config import Config
from subtrans.core.extract import extract_subtitle_track, find_external_subtitle
from subtrans.core.pipeline import (
    Pipeline,
    Stage,
    StageStatus,
    discover_inputs,
    has_existing_translation,
    natural_sort_key,
)
from subtrans.core.probe import SubtitleTrack, choose_best_subtitle_track, probe_subtitles
from subtrans.core.store import TranslationStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_natural_sort():
    raw_names = [
        Path("Episode 10.mkv"),
        Path("Episode 2.mkv"),
        Path("Episode 1.mkv"),
        Path("Episode 20.mkv"),
    ]
    sorted_names = sorted(raw_names, key=natural_sort_key)
    expected = [
        Path("Episode 1.mkv"),
        Path("Episode 2.mkv"),
        Path("Episode 10.mkv"),
        Path("Episode 20.mkv"),
    ]
    assert sorted_names == expected


def test_choose_best_subtitle_track_priorities():
    tracks = [
        # Track 0: Sign/Song in English
        SubtitleTrack(index=0, codec_name="ass", language="eng", title="Signs & Songs", is_text=True),
        # Track 1: English dialogue (Text)
        SubtitleTrack(index=1, codec_name="ass", language="eng", title="English Dialogue", is_text=True),
        # Track 2: Japanese dialogue (Text)
        SubtitleTrack(index=2, codec_name="ass", language="jpn", title="Japanese", is_text=True),
        # Track 3: English PGS (Bitmap)
        SubtitleTrack(index=3, codec_name="hdmv_pgs_subtitle", language="eng", title="English PGS", is_text=False, is_bitmap=True),
    ]

    best = choose_best_subtitle_track(tracks, preferred_languages="eng,en,und")
    assert best is not None
    # Track 1 should be selected (English dialog text over sign/song and bitmap)
    assert best.index == 1
    assert best.title == "English Dialogue"


def test_probe_and_extract_subtitles():
    mkv_path = FIXTURES_DIR / "sample_test.mkv"
    assert mkv_path.is_file()

    tracks = probe_subtitles(mkv_path)
    assert len(tracks) >= 1
    track = tracks[0]
    assert track.codec_name == "ass"
    assert track.language == "eng"

    # Test extraction
    out_extracted = FIXTURES_DIR / "test_extracted.ass"
    try:
        res = extract_subtitle_track(mkv_path, track, output_path=out_extracted)
        assert res.is_file()
        content = res.read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "Dialogue:" in content
    finally:
        if out_extracted.exists():
            out_extracted.unlink()


def test_find_external_subtitle(tmp_path: Path):
    vid = tmp_path / "Movie.2024.1080p.mkv"
    vid.write_bytes(b"fake video")

    # No sub yet
    assert find_external_subtitle(vid) is None

    # External sub with language code
    ext_sub = tmp_path / "Movie.2024.1080p.eng.srt"
    ext_sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello", encoding="utf-8")

    found = find_external_subtitle(vid)
    assert found is not None
    assert found.name == "Movie.2024.1080p.eng.srt"


def test_discover_inputs_and_skip_export_dir(tmp_path: Path):
    # Setup directory structure
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    (season_dir / "Episode 1.mkv").write_bytes(b"video1")
    (season_dir / "Episode 2.mkv").write_bytes(b"video2")

    # Ignored directory
    export_dir = season_dir / "Subtitles_Export_123"
    export_dir.mkdir()
    (export_dir / "Episode 1.srt").write_text("sub", encoding="utf-8")

    tasks = discover_inputs(season_dir)
    assert len(tasks) == 2
    assert tasks[0].path.name == "Episode 1.mkv"
    assert tasks[1].path.name == "Episode 2.mkv"


def test_pipeline_run_video(mock_server, tmp_path: Path):
    from tests.test_translate import _make_test_config
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "normal"
    mock_cfg.logged_requests.clear()

    # Copy sample_test.mkv to tmp_path
    vid_file = tmp_path / "Anime_Ep01.mkv"
    shutil.copy2(FIXTURES_DIR / "sample_test.mkv", vid_file)

    cfg = _make_test_config(base_url)
    cfg.general.overwrite_existing = False

    store = TranslationStore(job_dir=tmp_path / "job_pipe", global_cache_dir=tmp_path)
    pipeline = Pipeline(config=cfg, store=store)

    # First run
    tasks = pipeline.run(input_path=vid_file, job_id="test_job")
    assert len(tasks) == 1
    task = tasks[0]

    assert task.stages[Stage.EXTRACT.value] == StageStatus.SUCCESS
    assert task.stages[Stage.TRANSLATE.value] == StageStatus.SUCCESS
    assert task.stages[Stage.WRITE.value] == StageStatus.SUCCESS

    # Verify translated output exists
    target_ass = tmp_path / "Anime_Ep01.fa.ass"
    assert target_ass.is_file()
    assert has_existing_translation(vid_file, "fa") is True

    # Second run: should be skipped because target exists!
    tasks_run2 = pipeline.run(input_path=vid_file, job_id="test_job")
    task2 = tasks_run2[0]
    assert task2.stages[Stage.EXTRACT.value] == StageStatus.SKIPPED
    assert task2.stages[Stage.TRANSLATE.value] == StageStatus.SKIPPED
