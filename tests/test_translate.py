"""End-to-end integration tests for translation with mock LLM server."""

import threading
import time
from pathlib import Path
import httpx
import pytest
import uvicorn

from subtrans.core.config import Config
from subtrans.core.llm import LLMClient
from subtrans.core.store import TranslationStore
from subtrans.core.translate import BatchTranslator
from tests.mock_llm import MockLLMConfig, create_mock_llm_app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def mock_server():
    mock_cfg = MockLLMConfig()
    app = create_mock_llm_app(mock_cfg)
    port = 20199
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for ready
    ready = False
    for _ in range(50):
        try:
            with httpx.Client(timeout=1.0, trust_env=False) as client:
                r = client.get(f"http://127.0.0.1:{port}/models")
                if r.status_code == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)

    assert ready, "Mock server failed to start"
    yield f"http://127.0.0.1:{port}", mock_cfg
    server.should_exit = True


def test_translate_srt_file(mock_server, tmp_path: Path):
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "normal"
    mock_cfg.logged_requests.clear()

    cfg = Config()
    cfg.provider.base_url = base_url
    cfg.provider.model = "mock-model"
    cfg.translate.batch_lines = 10
    cfg.general.overwrite_existing = True

    store = TranslationStore(job_dir=tmp_path / "job1", global_cache_dir=tmp_path)
    translator = BatchTranslator(config=cfg, store=store)

    src_sub = FIXTURES_DIR / "sample.srt"
    out_sub = tmp_path / "sample.fa.srt"

    saved_path, report = translator.translate_file(
        subtitle_path=src_sub,
        output_path=out_sub,
    )

    assert saved_path.is_file()
    assert report.total_lines == 5
    # Lines:
    # 0: Hello world -> translated
    # 1: ♪ ♫ -> skipped
    # 2: [door slams] -> translated (SDH=True)
    # 3: Persian -> skipped
    # 4: Thank you -> translated
    assert report.translated_count == 3
    assert report.skipped_count == 2
    assert report.api_calls > 0

    # Verify UTF-8 BOM was written for SRT
    content_bytes = out_sub.read_bytes()
    assert content_bytes.startswith(b"\xef\xbb\xbf")


def test_translate_ass_tag_roundtrip(mock_server, tmp_path: Path):
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "normal"
    mock_cfg.logged_requests.clear()

    cfg = Config()
    cfg.provider.base_url = base_url
    cfg.provider.model = "mock-model"
    cfg.general.overwrite_existing = True

    store = TranslationStore(job_dir=tmp_path / "job_ass", global_cache_dir=tmp_path)
    translator = BatchTranslator(config=cfg, store=store)

    src_sub = FIXTURES_DIR / "sample.ass"
    out_sub = tmp_path / "sample.fa.ass"

    saved_path, report = translator.translate_file(
        subtitle_path=src_sub,
        output_path=out_sub,
    )

    assert saved_path.is_file()
    content_text = out_sub.read_text(encoding="utf-8")

    # Override tags in line 0: {\an8}{\pos(960,100)} and {\i1} ... {\i0} must survive
    assert r"{\an8}" in content_text
    assert r"{\pos(960,100)}" in content_text
    assert r"{\i1}" in content_text
    assert r"{\i0}" in content_text


def test_resume_skips_done_lines(mock_server, tmp_path: Path):
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "normal"

    cfg = Config()
    cfg.provider.base_url = base_url
    cfg.provider.model = "mock-model"
    cfg.general.overwrite_existing = True

    store = TranslationStore(job_dir=tmp_path / "job_resume", global_cache_dir=tmp_path)
    translator = BatchTranslator(config=cfg, store=store)

    src_sub = FIXTURES_DIR / "sample.srt"
    out_sub = tmp_path / "sample_res.fa.srt"

    # Run 1: first translation
    translator.translate_file(src_sub, output_path=out_sub)
    calls_first_run = len(mock_cfg.logged_requests)

    # Run 2: resume should make 0 new API calls!
    mock_cfg.logged_requests.clear()
    translator_resumed = BatchTranslator(config=cfg, store=store)
    _, report2 = translator_resumed.translate_file(src_sub, output_path=out_sub)

    assert len(mock_cfg.logged_requests) == 0
    assert report2.cached_count >= 3


def test_sse_mode(mock_server, tmp_path: Path):
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "sse_only"
    mock_cfg.logged_requests.clear()

    cfg = Config()
    cfg.provider.base_url = base_url
    cfg.provider.model = "mock-model"
    cfg.general.overwrite_existing = True

    store = TranslationStore(job_dir=tmp_path / "job_sse", global_cache_dir=tmp_path)
    translator = BatchTranslator(config=cfg, store=store)

    src_sub = FIXTURES_DIR / "sample.srt"
    out_sub = tmp_path / "sample_sse.fa.srt"

    saved_path, report = translator.translate_file(src_sub, output_path=out_sub)
    assert saved_path.is_file()
    assert report.translated_count > 0


def test_rate_limit_429_retry(mock_server, tmp_path: Path):
    base_url, mock_cfg = mock_server
    mock_cfg.mode = "429_n"
    mock_cfg.rate_limit_count = 1
    mock_cfg.rate_limit_counter = 0

    cfg = Config()
    cfg.provider.base_url = base_url
    cfg.provider.model = "mock-model"
    cfg.retry.base_delay_seconds = 1  # Fast for test
    cfg.general.overwrite_existing = True

    store = TranslationStore(job_dir=tmp_path / "job_429", global_cache_dir=tmp_path)
    translator = BatchTranslator(config=cfg, store=store)

    src_sub = FIXTURES_DIR / "sample.srt"
    out_sub = tmp_path / "sample_429.fa.srt"

    saved_path, report = translator.translate_file(src_sub, output_path=out_sub)
    assert saved_path.is_file()
    assert report.translated_count > 0
