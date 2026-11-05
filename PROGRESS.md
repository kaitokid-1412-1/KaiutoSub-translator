# PROGRESS

Current milestone: M1 (Core Subtitle Translation)

## Done:
- **2026-11-05:** Project initialization and directory layout scaffolding matching SPEC section 3.
- **2026-11-05:** Config system implemented in `subtrans/core/config.py` with typed schemas, JSON persistence in user data dir via `platformdirs`, and API key masking.
- **2026-11-05:** Diagnostic tool `doctor` implemented in `subtrans/core/doctor.py` and CLI `subtrans/cli.py` checking FFmpeg, FFprobe, SubtitleEdit, directory write permissions, and OpenAI-compatible gateway connectivity with Persian status reporting and actionable fixes.
- **2026-11-05:** OpenAI-compatible mock server implemented in `tests/mock_llm.py` supporting all SPEC section 10 modes (normal, sse_only, drops_id, merges_lines, 429_n, length, html, garbled, mangles_tokens, and call logging).
- **2026-11-05:** Unit test suite initialized with `test_config.py` and `test_doctor.py`.
- **2026-11-05:** Automated launcher `START.bat` created with Python detection, auto-venv setup, dependency install, doctor check, and web launch.
- **2026-11-05:** Persian documentation `README_FA.md` authored.
- **2026-11-05:** Subtitle parsing and line classification implemented in `subtrans/core/parse.py` (BOM/UTF-8/charset-normalizer/cp1256/cp1252 detection; classification of comments, drawings, karaoke, styles, music/digits, Persian text, and SDH cues).
- **2026-11-05:** Tag protection system implemented in `subtrans/core/protect.py` (leading override blocks separation, mid-line token replacement, `\N` newline conversion, token validation, and degraded restoration).
- **2026-11-05:** OpenAI-compatible client implemented in `subtrans/core/llm.py` (SSE data stream handling, rate limiting per minute, 429 exponential backoff with Retry-After, finish_reason length handling, ignore reasoning_content, and quota exhaustion detection).
- **2026-11-05:** Resumable SQLite storage and global cache implemented in `subtrans/core/store.py` (atomic batch commits, resume skipping DONE lines, cross-file cache lookup).
- **2026-11-05:** Safe subtitle output writer implemented in `subtrans/core/writeout.py` (atomic temporary file replacement, automatic UTF-8 BOM for SRT, backup handling).
- **2026-11-05:** Batch translation engine implemented in `subtrans/core/translate.py` (rolling context, batch splitting/halving fallback, JSON repair, in-file deduplication, tone presets).
- **2026-11-05:** CLI command `python -m subtrans translate` wired and tested.
- **2026-11-05:** Complete M1 test suite in `tests/test_parse.py`, `tests/test_protect.py`, `tests/test_store.py`, and `tests/test_translate.py` passing 23/23 tests.

## Next 3 steps:
1. Milestone M2: Implement Persian text post-processing in `subtrans/core/persian.py` (character normalisation, Persian digits, punctuation spacing, ZWNJ rules, BiDi modes rle/rlm/none, text wrapping).
2. Milestone M2: Implement Quality Control (QC pass) in `subtrans/core/qc.py` to catch untranslated Latin remnants and generate JSON/text reports.
3. Milestone M2: Generate `bidi_test.srt` for player/smart TV compatibility verification.

## How to run tests:
```bash
python -m pytest tests/ -v
```

## Decisions made:
- Used `FastAPI` and `uvicorn` for the mock server and web interface to provide lightweight, native async and SSE support with clean route definitions.
- Local connections (127.0.0.1 / localhost) in HTTP clients set `trust_env=False` to prevent system V2Ray/tun proxies from intercepting local LLM gateway traffic.
- Preserved Git repository with `main` as the default branch.
- Added heuristic in `parse.py` to prioritize `cp1256` when Arabic/Persian script is present over 0-coherence CJK false positives from `charset-normalizer`.

## Known issues / untested on Windows:
- SubtitleEdit CLI switches for PGS/VobSub OCR need verification against current SubtitleEdit releases before M6.

## Research findings to remember:
- 9Router at `127.0.0.1:20128/v1` can return SSE `data:` streams even when `stream: false` is requested; response handler must detect `data:` prefix and assemble delta contents seamlessly.
- Windows batch scripts must use `chcp 65001` for proper UTF-8 Persian character rendering.
- `pysubs2` standardizes SRT inline formatting (`<i>`, `<b>`) into SSA override tags `{\i1}` upon loading and converts them back on export.
