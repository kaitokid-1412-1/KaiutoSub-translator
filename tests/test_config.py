"""Unit tests for configuration management."""

import json
from pathlib import Path
from subtrans.core.config import Config, load_config, save_config, mask_api_key


def test_default_config():
    cfg = Config()
    assert cfg.general.target_lang == "fa"
    assert cfg.general.output_pattern == "{stem}.{lang}.{ext}"
    assert cfg.general.overwrite_existing is False
    assert cfg.provider.kind == "openai_compatible"
    assert cfg.provider.base_url == "http://127.0.0.1:20128/v1"
    assert cfg.translate.batch_lines == 30
    assert cfg.persian.bidi_mode == "rle"


def test_mask_api_key():
    assert mask_api_key("") == ""
    assert mask_api_key("short") == "********"
    assert mask_api_key("sk-1234567890abcdef") == "sk-...cdef"


def test_save_and_load_config(tmp_path: Path):
    cfg_file = tmp_path / "test_config.json"
    cfg = Config()
    cfg.provider.api_key = "secret-key-12345"
    cfg.general.target_lang = "fa"
    cfg.translate.batch_lines = 15

    save_config(cfg, cfg_file)
    assert cfg_file.is_file()

    loaded = load_config(cfg_file)
    assert loaded.provider.api_key == "secret-key-12345"
    assert loaded.translate.batch_lines == 15
    assert loaded.general.target_lang == "fa"


def test_to_dict_masking():
    cfg = Config()
    cfg.provider.api_key = "sk-live-supersecrettoken"
    
    unmasked = cfg.to_dict(mask_secrets=False)
    assert unmasked["provider"]["api_key"] == "sk-live-supersecrettoken"

    masked = cfg.to_dict(mask_secrets=True)
    assert masked["provider"]["api_key"] != "sk-live-supersecrettoken"
    assert masked["provider"]["api_key"].startswith("sk-")
    assert masked["provider"]["api_key"].endswith("oken")
