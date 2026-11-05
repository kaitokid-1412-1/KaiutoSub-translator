"""Unit tests for system doctor diagnostics."""

from unittest.mock import patch
import pytest
from subtrans.core.config import Config
from subtrans.core.doctor import (
    check_ffmpeg,
    check_ffprobe,
    check_subtitle_edit,
    check_write_permission,
    check_gateway,
    run_diagnostics,
    format_diagnostics_persian,
)


def test_check_ffmpeg():
    item = check_ffmpeg()
    assert item.name == "ffmpeg"
    assert item.persian_title == "ابزار FFmpeg"
    # ffmpeg should be installed on this environment
    assert item.ok is True


def test_check_ffprobe():
    item = check_ffprobe()
    assert item.name == "ffprobe"
    assert item.persian_title == "ابزار FFprobe"
    assert item.ok is True


def test_check_write_permission():
    item = check_write_permission()
    assert item.name == "write_permission"
    assert item.ok is True


def test_check_gateway_unreachable():
    cfg = Config()
    cfg.provider.base_url = "http://127.0.0.1:59999/v1"
    item = check_gateway(cfg)
    assert item.name == "gateway"
    assert item.ok is False
    assert item.fix_suggestion is not None
    assert "9Router" in item.fix_suggestion or "روشن" in item.fix_suggestion


def test_format_diagnostics_persian():
    items = [
        check_ffmpeg(),
        check_ffprobe(),
    ]
    formatted = format_diagnostics_persian(items)
    assert "گزارش سلامت سیستم" in formatted
    assert "FFmpeg" in formatted
    assert "FFprobe" in formatted
