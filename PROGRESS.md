# PROGRESS

Current milestone: M0 (Scaffold)

## Done:
- **2026-11-05:** Project initialization and directory layout scaffolding matching SPEC section 3.
- **2026-11-05:** Config system implemented in `subtrans/core/config.py` with typed schemas, JSON persistence in user data dir via `platformdirs`, and API key masking.
- **2026-11-05:** Diagnostic tool `doctor` implemented in `subtrans/core/doctor.py` and CLI `subtrans/cli.py` checking FFmpeg, FFprobe, SubtitleEdit, directory write permissions, and OpenAI-compatible gateway connectivity with Persian status reporting and actionable fixes.
- **2026-11-05:** OpenAI-compatible mock server implemented in `tests/mock_llm.py` supporting all SPEC section 10 modes (normal, sse_only, drops_id, merges_lines, 429_n, length, html, garbled, mangles_tokens, and call logging).
- **2026-11-05:** Unit test suite initialized with `test_config.py` and `test_doctor.py`.
- **2026-11-05:** Automated launcher `START.bat` created with Python detection, auto-venv setup, dependency install, doctor check, and web launch.
- **2026-11-05:** Persian documentation `README_FA.md` authored.

## Next 3 steps:
1. Milestone M1: Implement subtitle file parsing and line classification (`parse.py`) using `pysubs2` and `charset-normalizer`.
2. Milestone M1: Implement tag protection engine (`protect.py`) preserving ASS/SRT styling and test token round-trips.
3. Milestone M1: Build the OpenAI-compatible HTTP client (`llm.py`) with SSE-handling, retry backoff, and batch translator (`translate.py`), backed by `mock_llm.py`.

## How to run tests:
```bash
python -m pytest tests/ -v
```

## Decisions made:
- Used `FastAPI` and `uvicorn` for the mock server and web interface to provide lightweight, native async and SSE support with clean route definitions.
- Local connections (127.0.0.1 / localhost) in HTTP clients set `trust_env=False` to prevent system V2Ray/tun proxies from intercepting local LLM gateway traffic.
- Preserved Git repository with `main` as the default branch.

## Known issues / untested on Windows:
- SubtitleEdit CLI switches for PGS/VobSub OCR need verification against current SubtitleEdit releases before M6.

## Research findings to remember:
- 9Router at `127.0.0.1:20128/v1` can return SSE `data:` streams even when `stream: false` is requested; response handler must detect `data:` prefix and assemble delta contents seamlessly.
- Windows batch scripts must use `chcp 65001` for proper UTF-8 Persian character rendering.
