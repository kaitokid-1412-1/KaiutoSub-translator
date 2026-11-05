"""Media probing utilities using ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TEXT_CODECS = {"ass", "ssa", "subrip", "webvtt", "mov_text"}
BITMAP_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}

DEPENALIZED_TITLE_WORDS = {"sign", "signs", "song", "songs", "forced", "commentary"}


@dataclass
class SubtitleTrack:
    index: int
    codec_name: str
    language: str = "und"
    title: str = ""
    is_text: bool = True
    is_bitmap: bool = False

    @property
    def extension(self) -> str:
        if self.codec_name in ("ass", "ssa"):
            return "ass"
        elif self.codec_name == "webvtt":
            return "vtt"
        elif self.codec_name in ("subrip", "mov_text"):
            return "srt"
        elif self.codec_name == "hdmv_pgs_subtitle":
            return "sup"
        elif self.codec_name == "dvd_subtitle":
            return "sub"
        return "srt"


def probe_subtitles(video_path: Path) -> List[SubtitleTrack]:
    """Probe subtitle streams inside a video container using ffprobe.
    
    Executes ffprobe in subprocess without shell=True, handling spaces and Unicode paths.
    """
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise FileNotFoundError("ffprobe پیدا نشد. لطفاً مطمئن شوید FFmpeg در PATH نصب است.")

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        str(video_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        data = json.loads(proc.stdout)
    except Exception as e:
        return []

    streams = data.get("streams", [])
    tracks: List[SubtitleTrack] = []

    for s in streams:
        idx = int(s.get("index", 0))
        codec = s.get("codec_name", "").lower()
        tags = s.get("tags") or {}
        lang = (tags.get("language") or "und").lower()
        title = tags.get("title") or ""

        is_text = codec in TEXT_CODECS
        is_bitmap = codec in BITMAP_CODECS

        tracks.append(SubtitleTrack(
            index=idx,
            codec_name=codec,
            language=lang,
            title=title,
            is_text=is_text,
            is_bitmap=is_bitmap,
        ))

    return tracks


def choose_best_subtitle_track(
    tracks: List[SubtitleTrack],
    preferred_languages: str = "eng,en,und",
) -> Optional[SubtitleTrack]:
    """Select optimal subtitle track according to SPEC section 4.2.
    
    Priority:
    1. Preferred languages list (eng, en, und).
    2. Text track over bitmap track.
    3. Deprioritize tracks with sign/song/forced/commentary in title.
    """
    if not tracks:
        return None

    pref_langs = [l.strip().lower() for l in preferred_languages.split(",") if l.strip()]

    def track_score(track: SubtitleTrack) -> Tuple[int, int, int]:
        # 1. Title penalty: 1 if clean, 0 if contains sign/song/forced/commentary
        title_lower = track.title.lower()
        has_penalty = any(w in title_lower for w in DEPENALIZED_TITLE_WORDS)
        title_score = 0 if has_penalty else 1

        # 2. Text over bitmap: 2 for text, 1 for bitmap, 0 for unknown
        type_score = 2 if track.is_text else (1 if track.is_bitmap else 0)

        # 3. Language preference: index in pref_langs (lower index = higher priority)
        try:
            lang_rank = pref_langs.index(track.language)
        except ValueError:
            lang_rank = 999  # Not in preferred list

        # Sort key: higher is better, so negate lang_rank
        return (type_score, title_score, -lang_rank)

    # Sort tracks descending by score
    sorted_tracks = sorted(tracks, key=track_score, reverse=True)
    return sorted_tracks[0]

