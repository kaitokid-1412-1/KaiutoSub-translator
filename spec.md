# SubTrans Auto — Build Specification (v3, for an AI coding agent)

Written 5 Nov 2026. Audience: an autonomous coding agent (Hermes Agent, Antigravity, OpenCode, Cline, Claude Code, ...). Product owner: a non-programmer who speaks Persian.

## 0. Operating rules for the agent (read first)

1. The owner is not a programmer. Never ask technical questions; decide using this spec's defaults. If you truly must ask, ask in simple Persian, one question at a time, and propose a default.
2. Talk to the owner in Persian. Code, comments, identifiers and commit messages: English. All UI text and error messages: Persian.
3. Search the web whenever you are unsure (library APIs, CLI flags, tool behaviour, error messages). Never invent flags, endpoints or function names: confirm them in official docs, with `--help`, or with a tiny experiment. Section 12 lists what must be verified.
4. Work milestone by milestone (section 11). After each milestone: run tests, update `PROGRESS.md`, commit to git. The session can end at any moment (free-tier quota), so `PROGRESS.md` must let a brand-new session continue without the old chat.
5. Save quota: do not re-read or rewrite whole files without need. Test against the mock LLM server (section 10), never against real APIs, except one small final check (M6).
6. Never log or print API keys; mask them in the UI and in reports.
7. Never modify or delete the owner's original videos or subtitles.
8. Target Windows 10/11, Python 3.11+, no admin rights. Use `pathlib`, never `shell=True`, handle Persian characters and spaces in paths. Anything you cannot test on Windows must be listed in `PROGRESS.md`.
9. Keep dependencies few and maintained: `pysubs2`, `httpx`, `guessit`, `charset-normalizer`, `platformdirs`, `pytest`. For the web server use the standard library or `fastapi`+`uvicorn`, whichever gives reliable live progress with less code.

## 1. Goal and scope

**Goal:** the owner points the app at a folder (a whole season) or at single subtitle files, presses Start once, and gets Persian subtitles next to each video: resumable, cheap in API calls, styling preserved.

**In scope:** subtitle extraction from MKV/MP4, optional OCR for bitmap subtitles, LLM translation to Persian through any OpenAI-compatible endpoint, Persian post-processing, quality check, local Persian web UI, CLI, one-click launcher.

**Out of scope:** Electron, Node, the `rockbenben/subtitle-translator` project (its CLI is unverified; do not depend on it), accounts, cloud hosting, auto-updaters. Keep `target_lang` configurable but optimise for `fa`.

## 2. Environment facts

- Windows; Persian UI. A V2Ray-style system proxy is often active: HTTP clients must ignore system proxies for `127.0.0.1` and `localhost` (httpx `trust_env=False` for local URLs).
- LLM gateway: 9Router at `http://127.0.0.1:20128/v1` (OpenAI-compatible). Known quirks: it may reply with Server-Sent Events (`data:` lines) even when `stream: false` is sent; some setups only answer on `/api/v1/chat/completions`. Read the 9Router docs if needed. Treat OpenRouter, Gemini's OpenAI-compatible endpoint, DeepSeek, Ollama etc. the same way.
- Free-tier limits: assume few requests per minute and daily caps. Every unnecessary call is a cost.
- `ffmpeg` and `ffprobe` are on PATH. SubtitleEdit may or may not be installed.
- A prototype exists (Tkinter translator, relay, extractor). Use it only as reference and avoid its flaws (section 13).

## 3. Architecture

```
subtrans/
  core/  config.py probe.py extract.py ocr.py context.py glossary.py
         parse.py protect.py llm.py translate.py persian.py qc.py
         writeout.py store.py pipeline.py
  cli.py
  web/   server.py static/(index.html app.js style.css)   # Persian RTL UI
tests/   fixtures/  mock_llm.py
START.bat  README_FA.md  PROGRESS.md  requirements.txt
```

Rules: `core/` imports no UI code; CLI and web call only `pipeline`; long jobs run in a background worker; the UI follows progress by polling or SSE.

## 4. Pipeline (per input file)

Stages: DISCOVER, EXTRACT, OCR, CONTEXT, TRANSLATE, QC, WRITE. Each emits PENDING / RUNNING / SUCCESS / SKIPPED / FAILED plus a Persian message. A failure in one file never stops the queue.

### 4.1 Discover

Input is a folder (recursive) or files. Videos: `.mkv`, `.mp4`. Subtitles: `.srt`, `.ass`, `.ssa`, `.vtt`. Natural-sort episodes. Ignore folders named `Subtitles_Export_*`. Skip a video if `<stem>.fa.*` already exists, unless overwrite is on.

### 4.2 Extract

- Probe: `ffprobe -v error -select_streams s -show_entries stream=index,codec_name:stream_tags=language,title -of json <video>`.
- Text codecs: `ass`, `ssa`, `subrip`, `webvtt`, `mov_text` (convert to srt). Bitmap codecs: `hdmv_pgs_subtitle`, `dvd_subtitle`, `dvb_subtitle`, `xsub`.
- Choose the track: preferred source languages first (default `eng,en,und`); text over bitmap; deprioritise tracks whose title contains sign, song, forced or commentary. If no embedded track, look for an external subtitle with the same stem.
- If the extracted text is already mostly Persian, mark SKIPPED.
- Text track: `ffmpeg -hide_banner -loglevel error -y -i <video> -map 0:<index> -c:s copy <tmp>` (use `-c:s srt` for mov\_text).
- Bitmap track: extract the raw stream and go to 4.3.

### 4.3 OCR (optional)

Only for bitmap tracks. Preferred tool: SubtitleEdit command line. **Research the current SubtitleEdit CLI OCR switches before coding; do not trust memory.** If unsupported or not installed, mark SKIPPED with a Persian message that explains the options (install SubtitleEdit, or use another OCR tool you verified). Always run with a watchdog: timeout 180 s, kill the whole process tree, continue with the next file.

### 4.4 Context and glossary

- Series title/season/episode via `guessit` (it must handle fansub names like `[Group] Title - 05 [1080p]`). The owner may type a title or synopsis in the UI.
- One LLM call per **series**, not per episode, to produce `series_context` (short summary, tone, main characters with gender). Cache it in the job folder. Optional TMDb key for real metadata; the LLM must be told not to guess unknown facts.
- `glossary.json` (owner-editable): names to transliterate or keep, terms, free notes. After episode 1, optionally one call to list recurring proper names with chosen Persian spellings and append them, so names stay consistent across episodes.
- Tone presets stored as editable text files: Movie/TV, Anime, Documentary, Formal, Colloquial.

### 4.5 Parse and classify lines (`pysubs2`)

- Decode: BOM means UTF-8; else try UTF-8, then `charset-normalizer`, then `cp1256`, then `cp1252`.
- Skip: comment events; vector drawings (`\\p1` to `\\p9`); empty text; karaoke (`\\k`, `\\kf`, `\\ko`); events in styles matching sign, song, op, ed, karaoke, credits, title (configurable list; option `translate_signs_songs`, default false); lines that are only music symbols or numbers; lines already mostly Persian.
- SDH cues such as `[door slams]` are translated by default (option).
- Deduplicate identical normalised texts within a file and through the global cache (section 5).

### 4.6 Tag protection

Goal: 100% of inline styling survives.

1. Keep the leading run of override blocks (`{...}{...}`) aside as `lead`.
2. Replace every later override block with a token such as `[[T1]]`, `[[T2]]`. Run a quick real test with the chosen model and pick the token style that survives best; make it configurable.
3. Convert ASS hard breaks (`\\N`) to `\n` in the payload; keep `\\h` as a token. Check how `pysubs2` represents SRT italics and bold (it converts to ASS override blocks).
4. After translation: all tokens must be present exactly once. If not, retry; if still not, translate the line without tokens, restore only `lead`, flag it `degraded` in the report.
5. Final line = `lead` + translated text with tokens restored; convert `\n` back to `\\N` for ASS.

### 4.7 Batching and prompting

- Default 30 lines per call and at most about 3000 characters; both configurable.
- Rolling context: the previous 4 lines (source plus finished translation) and next 2 source lines, marked read-only.
- Payload: list of objects with integer `id` and string `text`. Expected answer: one JSON object with key `lines`, an array of objects with integer `id` and string `translated_text`.
- System prompt parts: role; `series_context`; glossary; tone preset; hard rules (keep ids, keep tokens, keep line breaks, never merge or split lines, output JSON only).
- Use `response_format` json\_object when the endpoint supports it; otherwise rely on the prompt and a robust extractor (strip code fences, take the outermost JSON object).
- Validate per batch: JSON parses; every id present exactly once; no extra ids; no empty output; tokens preserved; translation length below 4x source. Retry only the bad ids in a smaller batch (halve), up to 3 attempts, then single-line mode, then mark FAILED\_LINE (keep original text and list it in the report).

### 4.8 LLM client

- `POST {base_url}/chat/completions`, `stream: false`. If the body starts with `data:`, aggregate `choices[0].delta.content`. If the answer is HTML or 404, try the path variants once. Honour the real `finish_reason`: `length` means halve the batch and retry. Ignore `reasoning_content`.
- Retry on 429, 5xx and timeouts: delay = base 10 s x 2^attempt + jitter (10, 20, 40), honour `Retry-After`, max 3 attempts per batch.
- Quota exhausted (text such as quota, RESOURCE\_EXHAUSTED, insufficient): stop calling, mark the job PAUSED\_QUOTA, show a Persian message that progress is saved and can be resumed later. Never burn calls in a loop.
- Optional ordered `fallback_models`; switch after repeated failures. Concurrency default 1. A requests-per-minute limiter. Count calls and tokens and show them.
- Optional provider `gtx` (unofficial Google endpoint): per-line, slow, no context, labelled as an emergency option.
- **Dry run:** count lines, batches and expected calls before starting, and show it in the UI.

### 4.9 Persian post-processing (`persian.py`)

Every rule is toggleable and unit-tested.

1. Letters: Arabic kaf/yeh to Persian ک/ی; Arabic-Indic digits to Persian digits (option).
2. Punctuation: Persian comma, question mark, semicolon inside Persian text; `...` to the ellipsis character; no space before punctuation, one space after.
3. ZWNJ (half-space): می/نمی + verb, plural and comparative suffixes, common compounds. Prefer a few conservative hand-written rules; evaluate Hazm or Parsivar only if light and worth it.
4. BiDi: option `bidi_mode` = `none` | `rlm` | `rle` (add U+200F, or wrap each line in U+202B ... U+202C). Research which works best in VLC, MPC-HC and smart TVs. Default `rle`. Also generate `bidi_test.srt` so the owner can try each mode on their own player and TV and choose in the UI.
5. Re-wrap: if a line exceeds `max_chars_per_line` (default 42) and has no explicit break, balance into at most 2 lines at word boundaries. Do not touch positioned (`\\pos`) events or sources that already have breaks.
6. ASS fonts: for styles used by translated events set the font to a Persian-capable font (default Tahoma, configurable); keep size and colours. Research the correct ASS `Encoding` value for Arabic script.

### 4.10 QC pass

After translation, flag lines that are still not Persian (Latin letters present and at least as many as Persian letters), excluding glossary keep-names, acronyms, URLs and music. Re-translate only those once with a stricter prompt. Then write a report (text and JSON): totals, translated, skipped, degraded, failed lines with timestamps, API calls used.

### 4.11 Output

- Default target: `<VideoDir>/<VideoStem>.fa.srt` or `.fa.ass` (pattern configurable; option for the plain `<stem>.srt` form).
- SRT in UTF-8 with BOM by default (option for plain UTF-8).
- Write to a temp file, then `os.replace`. Never overwrite originals. If the target exists: skip, or rename the old one to `.bak`, per setting.
- Clean temp files after success.

## 5. State, resume and cache

- Job folder under the user data directory (`platformdirs`), for example `.../SubTransAuto/jobs/<job_id>/`.
- `job.json`: batch id, source, per-file stage statuses, settings snapshot without keys.
- `translations.sqlite`, table `lines(file_id, idx, src_hash, text, status, attempts, updated_at)` with primary key `(file_id, idx)`. Commit after **every** batch.
- Resume rule: on start, skip lines with status DONE and matching `src_hash`; call the API only for the rest.
- Global `cache.sqlite` keyed by (normalised source text, glossary hash, target language, prompt version) so repeated lines across episodes cost nothing.
- Stop button: finish the current request, save, mark PAUSED. A crash loses at most the in-flight batch.

## 6. Interfaces

### 6.1 CLI

- `python -m subtrans run <path> [--dry-run] [--resume JOB] [--overwrite]`
- `python -m subtrans extract <path>` and `python -m subtrans translate <subtitle>`
- `python -m subtrans doctor`: checks ffmpeg, ffprobe, SubtitleEdit, gateway reachability, model list, write permission; prints Persian status and fixes.

### 6.2 Local web UI (Persian, RTL)

- Server on `127.0.0.1`, default port 8765 (pick a free one if busy), opens the browser automatically.
- Security: random token in the URL and a cookie; reject requests whose Host is not `127.0.0.1` or `localhost`, or whose Origin does not match; no wildcard CORS; reject POSTs without the token; never return API keys.
- Works offline: no CDN assets. `dir=rtl`, font stack Tahoma, Vazirmatn (if installed), system-ui.
- Panels:
  1. Input: path box and a folder-picker button (run the native dialog in a separate process), scan result listing videos and their tracks.
  2. Settings: provider, base URL, API key (masked), model with Fetch Models (from `/models`) and Test Connection buttons, batch size, concurrency, tone preset, prompt editor, glossary editor, output options, bidi mode.
  3. Queue table: per-file stage pills (extract, OCR, context, translate, QC, write), progress bar, per-file retry and skip.
  4. Estimate before start (lines, calls, rough time).
  5. Coloured log panel and downloadable report.
  6. Start, Pause, Resume.
- Live updates by SSE or 1 s polling.

## 7. Configuration (stored as nested JSON in the user data folder)

```
general.target_lang = fa
general.output_pattern = {stem}.{lang}.{ext}
general.overwrite_existing = false
general.keep_source_subtitle = false
general.srt_encoding = utf-8-sig
extraction.source_languages = eng,en,und
extraction.skip_if_already_persian = true
ocr.enabled = true
ocr.timeout_seconds = 180
ocr.subtitleedit_path = (auto-detect)
provider.kind = openai_compatible      # or gtx
provider.base_url = http://127.0.0.1:20128/v1
provider.api_key = (set by owner)
provider.model = (set by owner)
provider.fallback_models = []
provider.request_timeout_seconds = 180
provider.concurrency = 1
provider.max_requests_per_minute = 10
translate.batch_lines = 30
translate.batch_max_chars = 3000
translate.context_before = 4
translate.context_after = 2
translate.translate_signs_songs = false
translate.translate_sdh_cues = true
translate.temperature = 0.3
translate.tone_preset = movie_tv
persian.normalize_letters = true
persian.persian_digits = true
persian.fix_punctuation = true
persian.fix_zwnj = true
persian.bidi_mode = rle                # none | rlm | rle
persian.rewrap = true
persian.max_chars_per_line = 42
persian.ass_font = Tahoma
retry.max_attempts = 3
retry.base_delay_seconds = 10
qc.enabled = true
web.host = 127.0.0.1
web.port = 8765
```

## 8. Persian error messages (minimum set)

| Situation | Message idea | Offered action |
| :-- | :-- | :-- |
| ffmpeg not found | FFmpeg پیدا نشد | Show install steps (research `winget` option) |
| Gateway unreachable | به 9Router وصل نشد؛ مطمئن شو روشن است | Test Connection button |
| 401/403 from API | کلید API نامعتبر است | Open settings |
| 429 / quota | سهمیه یا محدودیت سرعت؛ پیشرفت ذخیره شد | Resume later button |
| OCR timeout | OCR این فایل طول کشید و رد شد | Continue queue |
| No subtitle track | زیرنویسی در این ویدیو نیست | Skip |
| Bad JSON from model | پاسخ مدل خراب بود؛ دوباره تلاش می‌شود | Auto retry |
| Target exists | فایل ترجمه از قبل هست | Skip, overwrite or keep both |

## 9. Packaging and docs

- `START.bat`: find Python 3.11+ (`py -3` or `python`); if missing, print simple Persian instructions (research the official installer or `winget`); create `.venv`; install `requirements.txt`; run `python -m subtrans web`; keep the window open on errors.
- `README_FA.md`: one page in simple Persian: install, set the gateway, first run, troubleshooting, how to resume.
- Optional last step (M6): single `.exe` with PyInstaller; research first, and do not break the `.bat` route.

## 10. Testing

- Generate fixtures by script: SRT with italics and multi-line; ASS with header, styles, `{\\pos}`, mid-line `{\\i1}`, karaoke, sign style, drawings; VTT; cp1256 SRT; BOM SRT; tiny MKV built with ffmpeg (lavfi video plus text subtitle streams); a bitmap sample if easy.
- `mock_llm.py`: OpenAI-compatible fake server with modes: normal; SSE-only; drops an id; merges two lines; 429 n times; `finish_reason` length; HTML on the first path; garbled JSON; mangles tokens; logs every call.
- Tests (`pytest`): classification; tag round-trip; resume after killing the process mid-job; Persian normaliser; bidi modes; naming and output; encoding detection; OCR watchdog (fake slow executable); web security (bad Origin, bad Host, missing token get 403); dry-run estimate.

### Definition of done

1. Folder of MKVs with embedded English ASS: Start once, get `.fa.ass` next to every video, no other clicks.
2. Tag round-trip: every inline override block of a translated event is present in the output on all fixtures; degraded lines are reported.
3. Kill the process mid-job and restart: zero API calls for DONE lines (proved by the mock call log), no duplicated or overwritten lines.
4. OCR watchdog ends a hung process within timeout + 5 s and the queue continues.
5. 429 and quota cases pause cleanly with a Persian message; no crash, no call storm.
6. An SSE-only gateway works.
7. Original files are byte-identical after a run.
8. Wrong Origin, Host or token returns 403.
9. On a clean Windows PC with Python installed, double-clicking `START.bat` opens the UI, and `doctor` is green or gives clear Persian fixes.
10. Dry-run call estimate is within 15% of actual calls on the mock.

## 11. Milestones

Each milestone ends with passing tests, an updated `PROGRESS.md` and a git commit.

- **M0 Scaffold:** layout, config, `doctor`, `PROGRESS.md`, git, requirements.
- **M1 Core translation of one subtitle file:** parse, classify, protect, LLM client, translate, store, output, CLI `translate`, mock server and tests.
- **M2 Reliability and Persian quality:** resume, global cache, QC pass, report, `persian.py`, `bidi_test.srt`.
- **M3 Video pipeline:** probe and extract, discover folders, naming, skipping rules, CLI `run`.
- **M4 Web UI:** server with security, Persian panels, live progress, `START.bat`, `README_FA.md`.
- **M5 Context quality:** guessit, series context, glossary, presets, dry-run estimate, Fetch Models.
- **M6 OCR and hardening:** optional OCR with watchdog, error-message pass, one small real test with the owner's gateway (at most 50 lines), optional `.exe`.

## 12. Research checklist (verify before coding)

- `pysubs2` current API: loading with encoding, `plaintext`, override-tag handling, SRT-to-ASS conversion of italics and bold, saving.
- `ffprobe`/`ffmpeg` subtitle options for each codec; handling of MKV tracks with missing language tags.
- SubtitleEdit CLI: does it support OCR in command-line convert mode, and with which exact switches in the current version; alternatives for PGS/VobSub.
- `guessit` behaviour on anime fansub filenames.
- 9Router: endpoints, model list route, streaming behaviour, authentication.
- Gemini, OpenRouter and DeepSeek OpenAI-compatible endpoints and their JSON-mode support.
- Which BiDi marker works best for Persian SRT/ASS in VLC, MPC-HC, and common smart TVs; correct ASS `Encoding` value for Arabic script.
- Windows: Python install options, venv creation in `.bat`, PyInstaller with the chosen web stack.

## 13. Lessons from the prototype (do not repeat)

- Only leading tags were preserved; mid-line tags were lost.
- `overwrite` wrote partial translations over the original file.
- Tkinter widgets were updated from worker threads; the folder dialog opened inside a server thread.
- The relay always returned `finish_reason: stop`, hiding truncated answers, and used wildcard-style CORS with no authentication.
- The extractor returned all progress events only at the end of one long request.
- Returned ids were not validated; missing lines silently stayed English.
- Only English sources were detected as translatable.
- The retry back-off differed from the spec, and SRT was saved without BOM.

## 14. `PROGRESS.md` template

```
# PROGRESS
Current milestone: M?
Done: (bullets, with dates)
Next 3 steps: (concrete)
How to run tests: (exact commands)
Decisions made: (short)
Known issues / untested on Windows: (bullets)
Research findings to remember: (short facts with source links)
```

## 15. راهنمای مالک پروژه (فارسی)

1. یک پوشهٔ خالی بساز (مثلاً SubTransAuto) و این سند را با نام `SPEC.md` داخلش بگذار.
2. ایجنت را در همان پوشه باز کن. به آن اجازهٔ خواندن و نوشتن فایل و اجرای دستور بده و جستجوی وب را روشن کن.
3. پرامپت زیر را به ایجنت بده.
4. وقتی سهمیه تمام شد، بعد از ریست بنویس: «`PROGRESS.md` را بخوان و از همان‌جا ادامه بده.»
5. بعد از هر مرحله از ایجنت بخواه به زبان ساده بگوید چطور نتیجه را تست کنی.
6. آخر کار با یک فایل کوچک واقعی امتحان کن. اگر در پلیر یا تلویزیون علائم نگارشی جابه‌جا شد، در تنظیمات حالت `bidi` را عوض کن (فایل `bidi_test.srt` برای همین است).

**پرامپت برای ایجنت:**

```
You are a senior engineer. Read SPEC.md completely and build the project exactly as specified, milestone by milestone (M0 to M6). Follow section 0 strictly. Search the web whenever you are unsure and never invent flags or APIs. After each milestone: run the tests, update PROGRESS.md, commit, and tell me in simple Persian what was done and how I can check it. I am not a programmer, so do not ask me technical questions. Start with M0 now.
```
