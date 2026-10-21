# Local patches to the upstream `watch` skill

Upstream: https://github.com/bradautomates/claude-video, `skills/watch/`.
Based on: **v0.3.2** (commit `03ceb42`, 2026-09-25). Earlier base: v0.2.0 plus local edits.

This file is the checklist for the next upstream upgrade: copy upstream's `SKILL.md` and `scripts/` over this
folder, then re-apply everything below. Files not listed are identical to upstream.
`skills-lock.json` still carries the hash of the original upstream install; it does not describe this folder.

## New files (ours entirely, upstream does not have them)
- `scripts/testing.py`: training mode (cue frames at several offsets, contact sheets, label skeletons).
- `PATCHES.md`, and the tests in `tests/watch/`.

## `scripts/watch.py`
- **Storage.** `REPO_ROOT`, `WATCH_OUTPUT` (`WATCH_OUTPUT_DIR` overrides), `default_work_dir()` and `display_path()`:
  videos go to `watch-output/video-data/<video-id>/` instead of a temp dir. `--out-dir` keeps upstream behavior.
  Also writes `transcript.txt` beside the frames and prints `Stored in watch-output` in the report.
- **Testing mode.** `--testing`, `--testing-cap`, `--testing-offsets`; the cue-selection block before frame
  extraction; contact sheets and label files after it; the `## Testing mode` report section. Forces the local
  engine (`--testing` with `--engine gemini` is an error). Cue frames are keyed by `requested_timestamp_seconds`
  because 0.3.x stamps frames with their real time. Control frames are capped at `CONTROL_FRAMES`.
- **Routing.** `choose_backend()`: with `WATCH_WHISPER_BACKEND=auto`, YouTube without captions never uploads
  audio, and any other source uses Gemini audio when `GEMINI_API_KEY` exists. Explicit `--whisper` wins.
- **Gemini audio backend.** `--whisper gemini`; the `gemini` branch of the transcription block (audio extracted
  locally, only audio is uploaded); coverage, gap and token checks.
- **Run log.** `LOG_FILE` (`WATCH_LOG_FILE`), `RUN`, `log_event()`, `write_run_log()`, the `## Run log` report
  section, and the wrapper in the `__main__` block. One JSON line per run in `watch-output/watch-log.jsonl`.
- **Result file.** `write_result_file()` writes `<work>/result.json` on every local run (`--result-json PATH` adds a
  copy) with the log fields plus `event_kinds`, `transcript_kind` and `caption_status`
  (`available|none|fetch_failed|not-applicable`). Requested by the ingest skill, which reads it instead of the report.

## `scripts/gemini.py`
- `upload_file(..., mime=)` override (upstream hardcodes video).
- `TRANSCRIBE_PROMPT`, `parse_timestamped_lines()` (accepts `[MM:SS.s] text` and `[a --> b] text`),
  `transcribe_audio()`, `transcribe_long_audio()` (5-minute chunks, reuses `whisper.plan_chunks/split_audio/
  transcribe_chunks`), token counts on the returned segments.

## `scripts/config.py`
- `BACKENDS` and the error message accept `gemini`.

## `scripts/download.py`
- `clean_title()` (ASCII, no emoji) used by `_summary`, and `upload_date` added to `_summary`.
- `select_caption()`: when a language is requested, prefer the `-orig` track over YouTube's auto-translated one
  (the translated `en` track returns HTTP 429 on subtitle download).

## `SKILL.md`
- Option table: `--testing*`, `--out-dir` default, `--whisper ...|gemini`.
- "Engine routing (this repo's policy)" section, including the run-log rules and the model-test notes.
- "Storage and clean up" paragraph (replaces upstream's work-dir wording).

## Settings (not in the repo; `~/.config/watch/.env`)
`WATCH_ENGINE=local`, `WATCH_GEMINI_MODEL=gemini-3.5-flash-lite`, `WATCH_SUB_LANG=en`, `GEMINI_API_KEY`.

## After an upgrade, check
1. `python -m unittest discover -s tests/watch` passes.
2. `watch.py <reel> --detail efficient` shows `via gemini audio` and writes a `watch-log.jsonl` line.
3. `watch.py <youtube url> --testing` produces one sheet per cue and keeps the existing label file.
