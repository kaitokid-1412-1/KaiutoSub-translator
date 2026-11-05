"""Configuration management for SubTrans Auto."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import platformdirs

APP_NAME = "SubTransAuto"


@dataclass
class GeneralConfig:
    target_lang: str = "fa"
    output_pattern: str = "{stem}.{lang}.{ext}"
    overwrite_existing: bool = False
    keep_source_subtitle: bool = False
    srt_encoding: str = "utf-8-sig"


@dataclass
class ExtractionConfig:
    source_languages: str = "eng,en,und"
    skip_if_already_persian: bool = True


@dataclass
class OcrConfig:
    enabled: bool = True
    timeout_seconds: int = 180
    subtitleedit_path: str = ""
    engine: str = "paddleocr"  # paddleocr | tesseract | nocr | binaryocr
    use_gpu: bool = True  # True: GPU accelerated; False: CPU normal version
    language: str = "en"


@dataclass
class ProviderConfig:
    kind: str = "openai_compatible"  # or gtx
    base_url: str = "http://127.0.0.1:20128/v1"
    api_key: str = ""
    model: str = ""
    fallback_models: List[str] = field(default_factory=list)
    request_timeout_seconds: int = 180
    concurrency: int = 1
    max_requests_per_minute: int = 10


@dataclass
class TranslateConfig:
    batch_lines: int = 30
    batch_max_chars: int = 3000
    context_before: int = 4
    context_after: int = 2
    translate_signs_songs: bool = False
    translate_sdh_cues: bool = True
    temperature: float = 0.3
    tone_preset: str = "movie_tv"
    custom_prompt: Optional[str] = None
    presets_dir: Optional[str] = None


@dataclass
class PersianConfig:
    normalize_letters: bool = True
    persian_digits: bool = True
    fix_punctuation: bool = True
    fix_zwnj: bool = True
    bidi_mode: str = "rle"  # none | rlm | rle
    rewrap: bool = True
    max_chars_per_line: int = 42
    ass_font: str = "Tahoma"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay_seconds: int = 10


@dataclass
class QcConfig:
    enabled: bool = True


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    persian: PersianConfig = field(default_factory=PersianConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    qc: QcConfig = field(default_factory=QcConfig)
    web: WebConfig = field(default_factory=WebConfig)

    def to_dict(self, mask_secrets: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if mask_secrets and self.provider.api_key:
            data["provider"]["api_key"] = mask_api_key(self.provider.api_key)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        return cls(
            general=GeneralConfig(**data.get("general", {})),
            extraction=ExtractionConfig(**data.get("extraction", {})),
            ocr=OcrConfig(**data.get("ocr", {})),
            provider=ProviderConfig(**data.get("provider", {})),
            translate=TranslateConfig(**data.get("translate", {})),
            persian=PersianConfig(**data.get("persian", {})),
            retry=RetryConfig(**data.get("retry", {})),
            qc=QcConfig(**data.get("qc", {})),
            web=WebConfig(**data.get("web", {})),
        )


def mask_api_key(key: str) -> str:
    """Mask an API key for safe UI display and logs."""
    if not key:
        return ""
    if len(key) <= 8:
        return "********"
    return f"{key[:3]}...{key[-4:]}"


def get_user_data_dir() -> Path:
    """Get the application data directory."""
    dir_path = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_config_path(custom_path: Optional[Path] = None) -> Path:
    """Get the path to config.json."""
    if custom_path:
        return custom_path
    return get_user_data_dir() / "config.json"


def load_config(custom_path: Optional[Path] = None) -> Config:
    """Load configuration from disk or create default if not found."""
    path = get_config_path(custom_path)
    if not path.is_file():
        cfg = Config()
        save_config(cfg, path)
        return cfg

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config.from_dict(data)
    except Exception:
        # Return default if file is corrupted
        return Config()


def save_config(config: Config, custom_path: Optional[Path] = None) -> Path:
    """Save configuration to disk."""
    path = get_config_path(custom_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(mask_secrets=False), f, indent=2, ensure_ascii=False)
    return path
