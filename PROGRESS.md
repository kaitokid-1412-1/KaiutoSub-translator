# PROGRESS

Current milestone: M6 (OCR & Hardening Complete)

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
- **2026-11-05:** Persian post-processing engine implemented in `subtrans/core/persian.py` (letter normalization ك/ي, Persian digits conversion while preserving tag brackets, punctuation/ellipsis spacing, regex-based ZWNJ rules, BiDi formatting with none/rlm/rle modes, line re-wrapping at 42 chars, and ASS font/encoding=178 styling).
- **2026-11-05:** Quality Control (QC) module implemented in `subtrans/core/qc.py` (suspicious Latin remnant detection, automatic re-translation of flagged lines with stricter prompt, JSON/Persian text report generation).
- **2026-11-05:** Generated `bidi_test.srt` at repository root for player and TV display validation.
- **2026-11-05:** Media probing implemented in `subtrans/core/probe.py` using `ffprobe` (JSON parsing, text vs bitmap classification, track prioritization with language preferences and sign/song depenalization).
- **2026-11-05:** Subtitle extraction implemented in `subtrans/core/extract.py` using `ffmpeg` (stream copying, mov_text to srt conversion, external subtitle detection fallback, Persian skip checks).
- **2026-11-05:** Pipeline orchestrator implemented in `subtrans/core/pipeline.py` (recursive input discovery, natural episode sorting, skipping existing `.fa.*` subtitles, non-blocking queue processing with per-stage events).
- **2026-11-05:** CLI commands `python -m subtrans run` and `python -m subtrans extract` implemented with Persian progress display.
- **2026-11-05:** Pipeline and extraction tests in `tests/test_pipeline.py` passing; global test suite expanded to 39/39 passing tests.
- **2026-11-05:** Web server implemented in `subtrans/web/server.py` with Host/Origin validation, token authentication (header/cookie/query), masked API keys, free port detection, and SSE progress streaming.
- **2026-11-05:** Persian RTL UI implemented in `static/index.html`, `static/style.css`, and `static/app.js` (Folder picker subprocess, model fetch & test, dry-run estimate, queue table with stage pills, live log console).
- **2026-11-05:** Web security and API tests implemented in `tests/test_web.py`; all 47/47 tests passing.
- **2026-11-05:** Milestone M5 implemented: `guessit` metadata parser for anime fansubs and TV series filenames in `subtrans/core/context.py`.
- **2026-11-05:** Series context generator and JSON cache (`series_context.json`) with character gender/role detection to guide Persian pronouns and verbs.
- **2026-11-05:** Glossary management (`glossary.json`) in `subtrans/core/glossary.py` supporting custom transliterations, keep-terms, and automatic name extraction from initial episodes.
- **2026-11-05:** Editable text-file tone presets in `user_data_dir/presets/` with support for custom user presets and system prompt overrides.
- **2026-11-05:** Web UI updated with Context stage pill, custom prompt textarea, and glossary inputs.
- **2026-11-05:** Milestone M6 implemented: Bitmap subtitle OCR support (`subtrans/core/ocr.py`) with support for both modern `seconv` and classic `SubtitleEdit.exe`.
- **2026-11-05:** Subprocess watchdog implemented with automatic process-tree termination on timeout and queue continuation without hangs.
- **2026-11-05:** Complete Persian error messages verified matching SPEC section 8 (FFmpeg missing, Gateway unreachable, 401/403, 429/quota clean pause, OCR timeout, No subtitle track, Bad JSON auto-retry, and Target exists rules).
- **2026-11-05:** Full test suite expanded to 59/59 passing tests across all modules.

## Next 3 steps:
1. End-to-end verification with owner's live local 9Router gateway.
2. Optional PyInstaller packaging if standalone single-file distribution is requested.
3. Final review of repository status.

## How to run tests:
```bash
python -m pytest tests/ -v
```

## Decisions made:
- Used `FastAPI` and `uvicorn` for the mock server and web interface to provide lightweight, native async and SSE support with clean route definitions.
- Local connections (127.0.0.1 / localhost) in HTTP clients set `trust_env=False` to prevent system V2Ray/tun proxies from intercepting local LLM gateway traffic.
- Preserved Git repository with `main` as the default branch.
- Added heuristic in `parse.py` to prioritize `cp1256` when Arabic/Persian script is present over 0-coherence CJK false positives from `charset-normalizer`.
- Set ASS style `Encoding=178` (Arabic script) and default font to `Tahoma` during Persian subtitle generation.
- QC pass excludes non-translatable lines (music/numbers, drawings, comments) and ASS escape sequences from Latin residue checks.
- Subtitle extraction automatically infers target extension (`.fa.ass` or `.fa.srt`) from the extracted subtitle stream rather than the video container format.
- Run folder picker dialog via `tkinter` in an isolated child process to never block the async event loop of the web server.
- Call LLM for `series_context` once per job/series, persisting it in `series_context.json` so all subsequent episodes share narrative consistency without incurring extra tokens.
- Save tone presets as plain text files in the app data directory so users can edit descriptions directly with Notepad or any text editor.
- Implemented watchdog subprocess termination in `ocr.py` using `proc.kill()` and `proc.communicate(timeout=5)` so hung OCR jobs never block the file queue.

## Known issues / untested on Windows:
- Standalone `.exe` packaging with PyInstaller requires large bundle size (>80MB) due to bundled ffmpeg/fastapi dependencies; `.bat` route with auto-venv is recommended and fully operational.

## Research findings to remember:
- 9Router at `127.0.0.1:20128/v1` can return SSE `data:` streams even when `stream: false` is requested; response handler must detect `data:` prefix and assemble delta contents seamlessly.
- Windows batch scripts must use `chcp 65001` for proper UTF-8 Persian character rendering.
- `pysubs2` standardizes SRT inline formatting (`<i>`, `<b>`) into SSA override tags `{\i1}` upon loading and converts them back on export.
- Standard ASS `Encoding` attribute value for Arabic/Persian script is `178`.
- `guessit` extracts `title`, `season`, `episode`, and `release_group` cleanly from both fansub brackets (`[Group] Show - 05`) and standard scene formats (`Show.S01E03`).
- Subtitle Edit CLI command syntax: modern `seconv <input> subrip --ocr-engine:tesseract --overwrite` vs legacy `SubtitleEdit.exe /convert <input> subrip /ocrengine:tesseract /overwrite`. Both formats are supported dynamically in `ocr.py`.
