#!/usr/bin/env python3
"""Phase 2: turn claimed queue items into notes.

Claude (via `claude -p`) does the watching and writing; everything around it is deterministic:
claim -> run -> find the note -> validate -> write the done/ manifest (or retry / fail). brief.py then
writes the day's morning brief.
The runner is injectable so the whole loop is testable without a model.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from config import DEFAULT_RUN_BUDGET_MIN, Paths
from note import find_note, label_problems, summarize, validate
from store import Store, iso, read_json, utcnow, write_json

MAX_ATTEMPTS = 3
RETRY_DELAY_HOURS = 6
VIDEO_TIMEOUT_S = 25 * 60
SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPT_NAME = 'summary-prompt.md'
TESTING_PROMPT_NAME = 'summary-prompt-testing.md'
# Scoped on purpose: run python scripts, read frames, write the note. No web fetch, no arbitrary shell.
ALLOWED_TOOLS = ('Bash(python *)', 'Bash(py *)', 'Bash(uv run *)',
                 'PowerShell(python *)', 'PowerShell(py *)', 'PowerShell(uv run *)', 'Read', 'Write', 'Edit', 'Glob', 'Grep')

Runner = Callable[[dict, str, Path], 'RunResult']


@dataclass
class RunResult:
    returncode: int
    output: str = ''


@dataclass
class ProcessReport:
    done: list[str] = field(default_factory=list)
    retried: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    stopped: str | None = None
    rate_limited: bool = False
    setup_problem: bool = False


def prompt_template(paths: Paths, env: dict | None = None) -> str:
    """Prompt precedence: INGEST_PROMPT_FILE -> <home>/summary-prompt.md -> the skill's bundled copy."""
    env = os.environ if env is None else env
    candidates = []
    if env.get('INGEST_PROMPT_FILE'):
        candidates.append(Path(env['INGEST_PROMPT_FILE']))
    name = TESTING_PROMPT_NAME if paths.testing else PROMPT_NAME
    candidates += [paths.home / name, SKILL_DIR / name]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise FileNotFoundError(f'no {PROMPT_NAME} found (looked in {", ".join(str(c) for c in candidates)})')


def build_prompt(template: str, item: dict, paths: Paths) -> str:
    values = {
        'video_id': item['video_id'], 'url': item.get('url') or f'https://www.youtube.com/watch?v={item["video_id"]}',
        'title': item.get('title') or '', 'channel': item.get('channel_name') or '',
        'published': (item.get('published_at') or '')[:10], 'duration_min': round((item.get('duration_s') or 0) / 60),
        'notes_dir': paths.notes.as_posix(), 'raw_dir': paths.raw.as_posix(), 'skill_dir': SKILL_DIR.as_posix(),
        'watch_dir': (SKILL_DIR.parent / 'watch').as_posix(), 'today': iso(utcnow())[:10],
        'labels_dir': (paths.labels or Path('training/labels')).as_posix(),
        'specs_dir': ((paths.labels or Path('training/labels')).parent / 'specs').as_posix(),
    }
    out = template
    for key, value in values.items():          # plain replace: the template contains braces we must not interpret
        out = out.replace('{' + key + '}', str(value))
    return out


def agent_env(env: dict | None = None) -> dict:
    """The agent's `python` and `yt-dlp` must be this interpreter's. A scheduled task has no venv activated, so
    without this they resolve to the global Python (no yt-dlp) and watch fails with FileNotFoundError."""
    env = dict(os.environ if env is None else env)
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env.get('PATH', '')
    if sys.prefix != sys.base_prefix:
        env['VIRTUAL_ENV'] = sys.prefix
    return env


def claude_runner(item: dict, prompt: str, log_path: Path) -> RunResult:
    exe = shutil.which('claude')
    if not exe:
        return RunResult(127, 'claude CLI not found on PATH')
    cmd = [exe, '-p', '--permission-mode', 'acceptEdits', '--no-session-persistence',
           '--allowedTools', *ALLOWED_TOOLS]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=agent_env(),
                              timeout=VIDEO_TIMEOUT_S, input=prompt)   # stdin: multi-line argv is truncated by claude.cmd on Windows
    except subprocess.TimeoutExpired:
        return RunResult(124, f'timed out after {VIDEO_TIMEOUT_S // 60} minutes')
    return RunResult(proc.returncode, (proc.stdout or '') + (('\n[stderr]\n' + proc.stderr) if proc.stderr else ''))


USAGE_KEYS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens',
              'cost_usd', 'duration_ms')


@dataclass
class TextRun:
    returncode: int
    text: str = ''
    usage: dict = field(default_factory=dict)


def claude_text_runner(prompt: str, timeout_s: int = 10 * 60) -> TextRun:
    """`claude -p` with no tools at all: everything it needs is in the prompt and it only writes text back.
    Used by the briefs and the batched reel summaries."""
    exe = shutil.which('claude')
    if not exe:
        return TextRun(127, 'claude CLI not found on PATH')
    cmd = [exe, '-p', '--output-format', 'json', '--no-session-persistence', '--tools', '']
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=agent_env(),
                              timeout=timeout_s, input=prompt)   # stdin: multi-line argv is truncated by claude.cmd
    except subprocess.TimeoutExpired:
        return TextRun(124, f'timed out after {timeout_s // 60} minutes')
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return TextRun(proc.returncode or 1, ((proc.stdout or '') + (proc.stderr or '')).strip()[-500:])
    usage = dict(data.get('usage') or {})
    usage.update(cost_usd=data.get('total_cost_usd'), duration_ms=data.get('duration_ms'))
    code = proc.returncode or (1 if data.get('is_error') else 0)
    return TextRun(code, data.get('result') or '', usage)


def add_usage(total: dict, more: dict) -> None:
    for key in USAGE_KEYS:
        if isinstance(more.get(key), (int, float)):
            total[key] = total.get(key, 0) + more[key]


def watch_result(store: Store, video_id: str, since: float | None = None) -> dict:
    """watch's own record of the run (<raw>/<id>/result.json). Ignored if it predates `since` (a previous run's)."""
    path = store.paths.raw / video_id / 'result.json'
    try:
        if since is not None and path.stat().st_mtime < since - 1:
            return {}
    except OSError:
        return {}
    return read_json(path, {}) or {}


def complete(store: Store, item: dict, note_path: Path, now: datetime) -> dict:
    """Write the handoff manifest and drop the item from processing/. Assumes the note already validated."""
    video_id = item['video_id']
    extra = summarize(note_path.read_text(encoding='utf-8'))
    result = watch_result(store, video_id)
    raw = store.paths.raw / video_id
    manifest = {
        'video_id': video_id, 'title': item.get('title'), 'channel': item.get('channel_name'), 'url': item.get('url'),
        'published_at': item.get('published_at'), 'origin': item.get('origin'), 'priority': item.get('priority'),
        'note': note_path.as_posix(), 'raw_dir': raw.as_posix() if raw.exists() else None,
        'watch_engine': result.get('engine'), 'transcript_kind': result.get('transcript_kind'),
        'watch_events': result.get('event_kinds') or [],
        'ingested_at': iso(now), 'attempts': int(item.get('attempts', 0)) + 1, **extra,
        'training_status': 'labeled' if store.paths.testing else 'new',
    }
    write_json(store.item_path('done', video_id), manifest)
    store.remove('processing', video_id)
    return manifest


def fail(store: Store, item: dict, error: str, now: datetime, max_attempts: int = MAX_ATTEMPTS) -> str:
    """Count the attempt; back to pending (held for the next run) until max_attempts, then failed/."""
    video_id = item['video_id']
    item['attempts'] = int(item.get('attempts', 0)) + 1
    item['last_error'] = error[:500]
    item['last_attempt_at'] = iso(now)
    item.pop('claimed_at', None)
    if item['attempts'] >= max_attempts:
        write_json(store.item_path('failed', video_id), item)
        store.remove('processing', video_id)
        return 'failed'
    item['not_before'] = iso(now + timedelta(hours=RETRY_DELAY_HOURS))
    write_json(store.item_path('pending', video_id), item)
    store.remove('processing', video_id)
    return 'retry'


def _mentions_429(text: str) -> bool:
    low = text.lower()
    return 'http error 429' in low or 'too many requests' in low


def result_line(output: str) -> str:
    """The agent's final `RESULT: ...` line. Only this line is trusted: the prose around it may say "not a 429"."""
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith('RESULT:')]
    return lines[-1] if lines else ''


def blocker(output: str, watch: dict) -> tuple[str, str] | None:
    """A failure that is not the video's fault: (kind, reason) where kind is 'rate_limit' or 'setup'. Else None."""
    errors = ' | '.join(str(e) for e in watch.get('errors') or [])
    if 'cannot run' in errors.lower() or 'filenotfounderror' in errors.lower():
        return 'setup', f'watch could not run a tool on this machine: {errors[:200]}'
    if _mentions_429(errors) or _mentions_429(result_line(output)):
        return 'rate_limit', 'YouTube rate limit (HTTP 429); try again later'
    if watch.get('caption_status') == 'fetch_failed':
        # Upstream reports no reason for most failed caption requests; throttling is by far the usual one.
        return 'rate_limit', 'caption request failed (likely YouTube rate limiting); try again later' + \
            (f': {errors[:200]}' if errors else '')
    return None


def check_result(store: Store, item: dict, result: RunResult, started: float) -> tuple[Path | None, str]:
    """Locate and validate the note this run should have written. Returns (note_path, error)."""
    video_id = item['video_id']
    note = find_note(store.paths.notes, video_id)
    if note is None or note.stat().st_mtime < started - 1:
        tail = result.output.strip().splitlines()[-1][:200] if result.output.strip() else 'no output'
        return None, f'no new note written (exit {result.returncode}: {tail})'
    problems = validate(note.read_text(encoding='utf-8'), video_id, note.name)
    if problems:
        return None, 'note failed the contract: ' + '; '.join(problems)
    if store.paths.testing:
        problems = label_problems(store.paths.labels, video_id)
        if problems:
            return None, 'testing run incomplete: ' + '; '.join(problems)
    return note, ''


def process_queue(store: Store, now_fn: Callable[[], datetime] = utcnow, *, runner: Runner = claude_runner,
                  limit: int | None = None, budget_min: int = DEFAULT_RUN_BUDGET_MIN, only: str | None = None,
                  template: str | None = None, clock: Callable[[], float] = time.monotonic) -> ProcessReport:
    report = ProcessReport()
    template = template or prompt_template(store.paths)
    started_run = clock()
    handled = 0
    while True:
        if limit is not None and handled >= limit:
            report.stopped = f'reached the limit of {limit}'
            break
        if (clock() - started_run) / 60 >= budget_min:
            report.stopped = f'time budget of {budget_min} min used up'
            break
        now = now_fn()
        item = store.claim_one(now) if only is None else _claim_specific(store, only, now)
        if item is None:
            break
        handled += 1
        log_path = store.paths.logs / now.strftime('%Y-%m-%d') / f'{item["video_id"]}.log'
        started = time.time()
        result = runner(item, build_prompt(template, item, store.paths), log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(f'exit {result.returncode}\n\n{result.output}', encoding='utf-8')
        note, error = check_result(store, item, result, started)
        blocked = None if note is not None else blocker(result.output, watch_result(store, item['video_id'], started))
        if note is not None:
            complete(store, item, note, now_fn())
            report.done.append(item['video_id'])
        elif blocked:
            # YouTube throttling or a broken setup: not the video's fault, and every later video would hit it too.
            # Release it unchanged (no attempt counted) and stop the run.
            item.pop('claimed_at', None)
            write_json(store.item_path('pending', item['video_id']), item)
            store.remove('processing', item['video_id'])
            report.rate_limited = blocked[0] == 'rate_limit'
            report.setup_problem = blocked[0] == 'setup'
            report.stopped = blocked[1]
            break
        else:
            outcome = fail(store, item, error, now_fn())
            (report.failed if outcome == 'failed' else report.retried).append((item['video_id'], error))
        if only is not None:
            break
    return report


def _claim_specific(store: Store, video_id: str, now: datetime) -> dict | None:
    moved = store.move(video_id, 'pending', 'processing')
    if moved is None:
        return None
    moved['claimed_at'] = iso(now)
    write_json(store.item_path('processing', video_id), moved)
    return moved
