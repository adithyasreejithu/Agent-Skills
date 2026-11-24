#!/usr/bin/env python3
"""Reels, phases 2 and 3: transcribe queued reels, then summarize them in batches.

  fetch      pending reel -> reel_fetch.py (yt-dlp audio + Gemini) -> transcript line -> back to pending, transcribed
  summarize  transcribed reels, grouped by creator -> one `claude -p` with no tools per batch -> JSON array
             -> mechanical checks -> reels.jsonl -> the touched <user>/<YYYY-MM>.md files are re-rendered

Claude never runs a tool here: transcripts and captions are inlined, so a batch costs one plain completion.
Both the fetcher and the runner are injectable, so everything is testable without a network or a model.
"""
from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import reel_filter
from brief import unsourced_numbers
from note import STANCES
from process import SKILL_DIR, USAGE_KEYS, TextRun, add_usage, agent_env, claude_text_runner, fail
from reelstore import ReelStore, append_jsonl, month_of, read_jsonl
from store import iso, parse_ts, utcnow, write_json

PROMPT_NAME = 'reel-prompt.md'
TYPES_NAME = 'reel-types.toml'
FETCH_SCRIPT = Path(__file__).resolve().parent / 'reel_fetch.py'
FETCH_TIMEOUT_S = 6 * 60
SUMMARY_TIMEOUT_S = 15 * 60
BATCH_CHAR_CAP = 40_000          # transcript + caption characters per call (about 10k tokens)
CAPTION_CAP = 1_500
MAX_POINTS = 4
STANCE_VALUES = (*STANCES, 'none')
COMPACT_OPEN = ('promo', 'lifestyle', 'no-speech')   # one-line entries while the types are still open
TICKER = re.compile(r'[A-Z][A-Z0-9.]{0,6}')
TYPE_NAME = re.compile(r'[a-z][a-z0-9-]{1,30}')

Fetcher = Callable[[dict, Path], dict]
TextRunner = Callable[[str], TextRun]


# ---- reel types (open during the trial, fixed afterwards) --------------------
@dataclass(frozen=True)
class ReelType:
    name: str
    description: str = ''
    fields: tuple[str, ...] = ()
    brief: str = 'include'       # include | count-only | skip
    max_points: int = MAX_POINTS
    compact: bool = False        # one line in the month file, no bullets


def load_types(path: Path | None = None) -> list[ReelType] | None:
    """None means no taxonomy yet: the model labels each reel freely (open mode)."""
    path = path or SKILL_DIR / TYPES_NAME
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return None
    types = []
    for t in data.get('type', []):
        name = str(t.get('name') or '').strip().lower()
        if not TYPE_NAME.fullmatch(name):
            raise ValueError(f'{path}: type name {name!r} must be lowercase kebab-case')
        types.append(ReelType(name, str(t.get('description') or ''), tuple(t.get('fields') or ()),
                              str(t.get('brief') or 'include'), int(t.get('max_points') or MAX_POINTS),
                              bool(t.get('compact', False))))
    return types or None


def compact_types(types: list[ReelType] | None) -> set[str]:
    return set(COMPACT_OPEN) if types is None else {t.name for t in types if t.compact}


# ---- phase 2: fetch + transcribe ---------------------------------------------
def run_reel_fetch(item: dict, work: Path) -> dict:
    """The live fetcher: reel_fetch.py in its own process (it imports the watch skill's modules)."""
    cmd = [sys.executable, str(FETCH_SCRIPT), item['url'], str(work)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              env=agent_env(), timeout=FETCH_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'kind': 'failed', 'error': f'timed out after {FETCH_TIMEOUT_S // 60} minutes'}
    lines = [l for l in (proc.stdout or '').splitlines() if l.startswith('{')]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        tail = ((proc.stderr or '') + (proc.stdout or '')).strip()[-300:]
        return {'ok': False, 'kind': 'failed', 'error': f'reel_fetch gave no result (exit {proc.returncode}): {tail}'}


@dataclass
class FetchReport:
    done: list[str] = field(default_factory=list)
    retried: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    filtered: list[tuple[str, str]] = field(default_factory=list)   # filler by rule, never downloaded
    stopped: str | None = None


def waiting_for(store: ReelStore, now: datetime, transcribed: bool) -> list[dict]:
    return [i for i in store.pending_items(now) if bool(i.get('transcribed')) == transcribed]


def _release(store: ReelStore, item: dict) -> None:
    item.pop('claimed_at', None)
    write_json(store.item_path('pending', item['video_id']), item)
    store.remove('processing', item['video_id'])


def fetch_queue(store: ReelStore, *, fetcher: Fetcher = run_reel_fetch, limit: int | None = None,
                budget_min: float | None = None, now_fn: Callable[[], datetime] = utcnow,
                clock: Callable[[], float] = time.monotonic, rules: bool = True) -> FetchReport:
    """Transcribe pending reels. With `rules`, a short reel with an empty caption is written as filler without
    being downloaded (reel_filter stage 1)."""
    report = FetchReport()
    rule_months: set = set()
    started = clock()
    for item in waiting_for(store, now_fn(), transcribed=False):
        if limit is not None and len(report.done) + len(report.retried) + len(report.failed) >= limit:
            report.stopped = f'reached the limit of {limit}'
            break
        if budget_min is not None and (clock() - started) / 60 >= budget_min:
            report.stopped = f'time budget of {budget_min} min used up'
            break
        code = item['video_id']
        if store.move(code, 'pending', 'processing') is None:
            continue
        reason = reel_filter.before_download(item.get('caption'), item.get('duration_s')) if rules else None
        if reason:
            rule_months.add(write_rule_entry(store, item, None, now_fn(), reason))
            report.filtered.append((code, reason))
            continue
        work = Path(tempfile.mkdtemp(prefix=f'reel-{code}-'))
        try:
            result = fetcher(item, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        now = now_fn()
        if result.get('ok'):
            segments = result.get('segments') or []
            store.save_transcript({
                'code': code, 'username': item.get('username'), 'creator': item.get('channel_name'),
                'taken_at': item.get('published_at'), 'caption': item.get('caption') or '',
                'duration_s': item.get('duration_s') or result.get('duration_s'), 'segments': segments,
                'speech': bool(segments), 'model': result.get('model'), 'gemini_tokens': result.get('gemini_tokens'),
                'fetched_at': iso(now)})
            item.update(transcribed=True, speech=bool(segments),
                        duration_s=item.get('duration_s') or result.get('duration_s'))
            _release(store, item)
            report.done.append(code)
            continue
        kind, error = result.get('kind') or 'failed', result.get('error') or 'unknown error'
        if kind in ('quota', 'setup', 'login'):
            # Not this reel's fault, and every later reel would hit it too: release it unchanged and stop.
            _release(store, item)
            report.stopped = f'{kind}: {error[:200]}'
            break
        if kind == 'unavailable':
            store.remove('processing', code)
            store.record_skip(code, 'unavailable', now, item.get('title'))
            report.skipped.append((code, error))
            continue
        outcome = fail(store, item, error, now)
        (report.failed if outcome == 'failed' else report.retried).append((code, error))
    if rule_months:
        render_months(store, rule_months)
    return report


def rule_entry(item: dict, row: dict | None, now: datetime, reason: str) -> dict:
    """The index entry for a reel judged filler by rule: one line from its caption, no model call."""
    caption = (row or {}).get('caption') or item.get('caption') or ''
    entry = {'type': 'filler', 'one_line': reel_filter.filler_line(caption), 'tickers': [], 'stance': 'none',
             'points': [], 'levels': [], 'fields': {}, 'on_screen': False, 'filtered': reason}
    out = full_entry(item, row, entry, now, 'rule', 'rule')
    if row is None:
        out['evidence'] = 'caption'
    return out


def write_rule_entry(store: ReelStore, item: dict, row: dict | None, now: datetime, reason: str) -> tuple[str, str]:
    entry = rule_entry(item, row, now, reason)
    index = store.load_index()
    index[entry['code']] = entry
    store.save_index(index)
    store.remove('processing', entry['code'])
    return entry.get('username') or 'unknown', month_of(entry.get('taken_at'))


# ---- phase 3: batched summaries ----------------------------------------------
def prompt_template(paths) -> str:
    for path in (paths.home / PROMPT_NAME, SKILL_DIR / PROMPT_NAME):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise FileNotFoundError(f'no {PROMPT_NAME} in {paths.home} or {SKILL_DIR}')


def transcript_text(row: dict | None) -> str:
    return ' '.join(s.get('text', '').strip() for s in (row or {}).get('segments') or []).strip()


def types_block(types: list[ReelType] | None) -> str:
    if types is None:
        return ('The reel types are not fixed yet; you are helping discover them. Give each reel a short lowercase '
                'kebab-case `type` that says what kind of reel it is (for example stock-pick, market-update, '
                'news-reaction, education, portfolio-update), reusing a label you already used whenever it fits. '
                'Use exactly `promo` for adverts, courses, giveaways and self-promotion, `lifestyle` for reels with '
                'no market content, and `no-speech` when there is no transcript and the caption says nothing '
                'useful. Add `type_reason`: one short sentence on why. Put everything in `points` and `levels`; '
                'leave `fields` as {}.')
    lines = ['Use exactly one of these types. Fill `fields` with the keys listed for that type (write "not stated" '
             'when the reel does not say). Use `other` only when nothing fits.']
    for t in types:
        keys = ', '.join(t.fields) or 'none'
        lines.append(f'- `{t.name}`: {t.description} Fields: {keys}. At most {t.max_points} points.')
    return '\n'.join(lines)


def render_reel(item: dict, row: dict | None) -> str:
    caption = (row or {}).get('caption') or item.get('caption') or ''
    if len(caption) > CAPTION_CAP:
        caption = caption[:CAPTION_CAP] + ' …'
    text = transcript_text(row) or '(no speech)'
    duration = item.get('duration_s') or (row or {}).get('duration_s')
    sponsor = reel_filter.sponsor_hint(caption, transcript_text(row))
    hint = f' sponsor_hint="{sponsor}"' if sponsor else ''
    return (f'<reel code="{item["video_id"]}" creator="{item.get("channel_name") or ""}" '
            f'date="{(item.get("published_at") or "")[:10]}" seconds="{round(duration) if duration else "?"}"{hint}>\n'
            f'<caption>{caption}</caption>\n<transcript>{text}</transcript>\n</reel>')


def build_prompt(template: str, batch: list[tuple[dict, dict | None]], types: list[ReelType] | None) -> str:
    values = {'count': len(batch), 'types_block': types_block(types),
              'creators': ', '.join(sorted({i.get('channel_name') or '?' for i, _ in batch})),
              'reels': '\n\n'.join(render_reel(i, r) for i, r in batch)}
    out = template
    for key, value in values.items():          # plain replace: captions contain braces we must not interpret
        out = out.replace('{' + key + '}', str(value))
    return out


def parse_array(text: str) -> list | None:
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.M)
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, list) else []


CALL_ACTIONS = ('buy', 'sell', 'hold', 'trim', 'watch', 'avoid')
CALL_INSTRUMENTS = ('shares', 'calls', 'puts', 'spreads', 'leveraged-etf', 'etf', 'crypto', 'unspecified')


def clean_calls(value) -> list[dict]:
    """Normalise the model's per-stock calls. Lenient: unknown words become 'watch' / 'unspecified', not a retry."""
    out = []
    for c in value if isinstance(value, list) else []:
        if not isinstance(c, dict):
            continue
        ticker = str(c.get('ticker') or '').strip().lstrip('$').upper()
        if not TICKER.fullmatch(ticker):
            continue
        action = str(c.get('action') or '').strip().lower()
        instrument = str(c.get('instrument') or '').strip().lower().replace(' ', '-').replace('_', '-')
        out.append({'ticker': ticker,
                    'action': action if action in CALL_ACTIONS else 'watch',
                    'instrument': instrument if instrument in CALL_INSTRUMENTS else 'unspecified',
                    'sector': str(c.get('sector') or '').strip().lower()[:40] or 'not stated',
                    'when': str(c.get('when') or '').strip()[:80] or 'not stated'})
    return out


def check_entry(raw: dict, sources: str, types: list[ReelType] | None) -> tuple[dict, list[str], list[str]]:
    """Normalise one model object. Returns (entry, structural problems, numbers not found in the sources)."""
    problems = []
    rtype = str(raw.get('type') or '').strip().lower().replace(' ', '-').replace('_', '-')
    allowed = None if types is None else {t.name for t in types} | {'other'}
    if not TYPE_NAME.fullmatch(rtype):
        problems.append('`type` must be a short lowercase kebab-case label')
    elif allowed is not None and rtype not in allowed:
        problems.append(f'`type` "{rtype}" is not one of: {", ".join(sorted(allowed))}')
    one_line = str(raw.get('one_line') or '').strip()
    if not one_line:
        problems.append('`one_line` is empty')
    stance = str(raw.get('stance') or 'none').strip().lower()
    if stance not in STANCE_VALUES:
        problems.append(f'`stance` must be one of {", ".join(STANCE_VALUES)}')
    tickers = []
    for t in _strings(raw.get('tickers')):
        t = t.lstrip('$').upper()
        if TICKER.fullmatch(t) and t not in tickers:
            tickers.append(t)
    rt = next((t for t in types or [] if t.name == rtype), None)
    fields = raw.get('fields') if isinstance(raw.get('fields'), dict) else {}
    if rt:
        missing = [k for k in rt.fields if k not in fields]
        if missing:
            problems.append(f'`fields` is missing {", ".join(missing)} for type {rtype}')
    calls = clean_calls(raw.get('calls'))
    entry = {'type': rtype, 'one_line': one_line, 'tickers': tickers, 'stance': stance,
             'points': _strings(raw.get('points'))[:rt.max_points if rt else MAX_POINTS],
             'levels': _strings(raw.get('levels')), 'fields': fields, 'calls': calls,
             'market_sectors': _strings(raw.get('market_sectors'))[:6], 'on_screen': bool(raw.get('on_screen'))}
    if types is None and raw.get('type_reason'):
        entry['type_reason'] = str(raw['type_reason']).strip()[:200]
    written = ' '.join([one_line, *entry['points'], *entry['levels'], json.dumps(fields, ensure_ascii=False),
                        json.dumps(calls, ensure_ascii=False)])
    return entry, problems, unsourced_numbers(written, [sources])


@dataclass
class BatchOutcome:
    entries: dict[str, dict] = field(default_factory=dict)       # code -> accepted entry
    failed: dict[str, str] = field(default_factory=dict)          # code -> why
    usage: dict = field(default_factory=dict)
    calls: int = 0


def summarize_batch(batch: list[tuple[dict, dict | None]], template: str, types: list[ReelType] | None,
                    runner: TextRunner) -> BatchOutcome:
    """One call for the batch; one retry carrying only the reels that broke a rule."""
    out = BatchOutcome()
    todo = {i['video_id']: (i, r) for i, r in batch}
    feedback: dict[str, list[str]] = {}
    numbers_only: dict[str, tuple[dict, list[str]]] = {}
    for attempt in (1, 2):
        if not todo:
            break
        pairs = list(todo.values())
        prompt = build_prompt(template, pairs, types)
        if attempt == 2:
            prompt += ('\n\nYour previous answer broke these rules. Return the JSON array again for ONLY these '
                       f'{len(pairs)} reels and fix them:\n'
                       + '\n'.join(f'- {code}: {"; ".join(p)}' for code, p in feedback.items()))
        run = runner(prompt)
        out.calls += 1
        add_usage(out.usage, run.usage)
        if run.returncode != 0:
            feedback = {code: [f'claude exit {run.returncode}: {run.text.strip()[-160:] or "no output"}'] for code in todo}
            continue
        data = parse_array(run.text)
        if data is None:
            feedback = {code: ['the answer was not a JSON array'] for code in todo}
            continue
        by_code = {str(d.get('code')): d for d in data if isinstance(d, dict)}
        feedback = {}
        for code, (item, row) in list(todo.items()):
            raw = by_code.get(code)
            if raw is None:
                feedback[code] = ['this reel is missing from the array']
                continue
            sources = ' '.join([(row or {}).get('caption') or item.get('caption') or '', transcript_text(row)])
            entry, problems, unknown = check_entry(raw, sources, types)
            if problems:
                feedback[code] = problems
                continue
            if unknown and attempt == 1:
                feedback[code] = ['numbers not in its caption or transcript: ' + ', '.join(unknown[:8])]
                numbers_only[code] = (entry, unknown)
                continue
            if unknown:
                entry['unverified_numbers'] = unknown[:8]
            out.entries[code] = entry
            del todo[code]
    for code in todo:
        if code in numbers_only:
            # The first answer was sound apart from numbers it could not source, and the retry did no better:
            # keep the first answer with those numbers flagged rather than lose the reel.
            entry, unknown = numbers_only[code]
            entry['unverified_numbers'] = unknown[:8]
            out.entries[code] = entry
        else:
            out.failed[code] = '; '.join(feedback.get(code, ['no valid answer']))[:500]
    return out


def make_batches(pairs: list[tuple[dict, dict | None]], size: int) -> list[list[tuple[dict, dict | None]]]:
    """Per creator, oldest first, at most `size` reels and about BATCH_CHAR_CAP characters per batch."""
    by_creator: dict[str, list] = defaultdict(list)
    for item, row in pairs:
        by_creator[item.get('username') or item.get('channel_name') or '?'].append((item, row))
    batches = []
    for creator in sorted(by_creator):
        group = sorted(by_creator[creator], key=lambda p: p[0].get('published_at') or '')
        current, chars = [], 0
        for item, row in group:
            weight = len(transcript_text(row)) + min(len((row or {}).get('caption') or ''), CAPTION_CAP)
            if current and (len(current) >= size or chars + weight > BATCH_CHAR_CAP):
                batches.append(current)
                current, chars = [], 0
            current.append((item, row))
            chars += weight
        if current:
            batches.append(current)
    return batches


def full_entry(item: dict, row: dict | None, entry: dict, now: datetime, batch_id: str, mode: str) -> dict:
    caption = (row or {}).get('caption') or item.get('caption') or ''
    speech = bool((row or {}).get('speech', item.get('speech')))
    return {'code': item['video_id'], 'username': item.get('username'), 'creator': item.get('channel_name'),
            'taken_at': item.get('published_at'), 'ingested_at': iso(now), 'url': item.get('url'),
            'duration_s': item.get('duration_s') or (row or {}).get('duration_s'), 'views': item.get('views'),
            **entry, 'speech': speech,
            'evidence': ('transcript+caption' if caption else 'transcript') if speech else 'caption',
            'mode': mode, 'batch': batch_id}


@dataclass
class SummaryReport:
    done: list[str] = field(default_factory=list)
    retried: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    filtered: list[tuple[str, str]] = field(default_factory=list)   # filler by rule, no model call
    batches: int = 0
    calls: int = 0
    usage: dict = field(default_factory=dict)
    months: set = field(default_factory=set)


def _log_cost(store: ReelStore, batch_id: str, batch: list, outcome: BatchOutcome, mode: str, size: int) -> None:
    gemini = [r.get('gemini_tokens') for _, r in batch if r and isinstance(r.get('gemini_tokens'), int)]
    append_jsonl(store.cost_file, {
        'ts': iso(utcnow()), 'batch': batch_id, 'mode': mode, 'batch_size': size, 'reels': len(batch),
        'accepted': len(outcome.entries), 'failed': len(outcome.failed), 'calls': outcome.calls,
        'transcript_chars': sum(len(transcript_text(r)) for _, r in batch),
        **{key: outcome.usage.get(key) for key in USAGE_KEYS}, 'gemini_tokens': sum(gemini) if gemini else None})


def summarize_pairs(store: ReelStore, pairs: list[tuple[dict, dict | None]], *, runner: TextRunner, template: str,
                    types: list[ReelType] | None, size: int, now_fn=utcnow,
                    on_fail: Callable[[dict, str], str] | None = None, rules: bool = True) -> SummaryReport:
    """Summarize (item, transcript) pairs and write every accepted entry. `on_fail` decides what a failed reel's
    queue item becomes ('retry' / 'failed'); without it (a redo) the old entry is simply kept. With `rules`, reels
    with almost no speech and an empty caption are written as filler without a model call (reel_filter stage 2)."""
    report = SummaryReport()
    if rules:
        kept = []
        for item, row in pairs:
            reason = reel_filter.before_model((row or {}).get('caption') or item.get('caption'),
                                              (row or {}).get('segments'))
            if reason:
                report.months.add(write_rule_entry(store, item, row, now_fn(), reason))
                report.filtered.append((item['video_id'], reason))
            else:
                kept.append((item, row))
        pairs = kept
    mode = 'open' if types is None else 'typed'
    stamp = now_fn().strftime('%Y-%m-%dT%H:%MZ')
    for n, batch in enumerate(make_batches(pairs, size), 1):
        batch_id = f'{stamp}#{n}'
        outcome = summarize_batch(batch, template, types, runner)
        report.batches += 1
        report.calls += outcome.calls
        add_usage(report.usage, outcome.usage)
        _log_cost(store, batch_id, batch, outcome, mode, size)
        index = store.load_index()
        now = now_fn()
        for item, row in batch:
            code = item['video_id']
            if code in outcome.entries:
                entry = full_entry(item, row, outcome.entries[code], now, batch_id, mode)
                index[code] = entry
                report.done.append(code)
                report.months.add((entry.get('username') or 'unknown', month_of(entry.get('taken_at'))))
            elif on_fail is not None:
                result = on_fail(item, outcome.failed.get(code, 'no answer'))
                (report.failed if result == 'failed' else report.retried).append((code, outcome.failed.get(code, '')))
            else:
                report.failed.append((code, outcome.failed.get(code, '')))
        store.save_index(index)
        for item, _ in batch:
            if item['video_id'] in outcome.entries:
                store.remove('processing', item['video_id'])
    return report


def summarize_queue(store: ReelStore, *, runner: TextRunner | None = None, size: int | None = None,
                    limit: int | None = None, types: list[ReelType] | None = None, open_types: bool = False,
                    template: str | None = None, now_fn=utcnow, rules: bool = True) -> SummaryReport:
    runner = runner or (lambda prompt: claude_text_runner(prompt, SUMMARY_TIMEOUT_S))
    types = None if open_types else (types if types is not None else load_types())
    items = waiting_for(store, now_fn(), transcribed=True)[:limit]
    pairs = []
    for item in items:
        if store.move(item['video_id'], 'pending', 'processing') is None:
            continue
        pairs.append((item, store.load_transcript(item.get('username') or '', item['video_id'], item.get('published_at'))))
    report = summarize_pairs(store, pairs, runner=runner, template=template or prompt_template(store.paths),
                             types=types, size=size or store.paths.reel_batch, now_fn=now_fn,
                             on_fail=lambda item, why: fail(store, item, f'summary: {why}', now_fn()), rules=rules)
    render_months(store, report.months)
    return report


def redo(store: ReelStore, since: datetime, *, runner: TextRunner | None = None, size: int | None = None,
         types: list[ReelType] | None = None, open_types: bool = False, template: str | None = None,
         now_fn=utcnow, rules: bool = True) -> SummaryReport:
    """Re-summarize already-summarized reels from their cached transcripts (no download, no Gemini)."""
    runner = runner or (lambda prompt: claude_text_runner(prompt, SUMMARY_TIMEOUT_S))
    types = None if open_types else (types if types is not None else load_types())
    index = store.load_index()
    pairs = []
    for row in store.all_transcripts():
        taken = parse_ts(row.get('taken_at'))
        if taken is None or taken < since:
            continue
        old = index.get(row['code'], {})
        item = {'video_id': row['code'], 'url': old.get('url') or f'https://www.instagram.com/reel/{row["code"]}/',
                'username': row.get('username'), 'channel_name': row.get('creator') or old.get('creator'),
                'published_at': row.get('taken_at'), 'caption': row.get('caption'),
                'duration_s': row.get('duration_s'), 'views': old.get('views'), 'speech': row.get('speech')}
        pairs.append((item, row))
    report = summarize_pairs(store, pairs, runner=runner, template=template or prompt_template(store.paths),
                             types=types, size=size or store.paths.reel_batch, now_fn=now_fn, rules=rules)
    render_months(store, report.months)
    return report


# ---- the readable month files ---------------------------------------------------
def _clock(seconds) -> str:
    if not seconds:
        return '?'
    seconds = int(round(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def render_entry(e: dict, compact: set[str]) -> list[str]:
    head = (f'### {(e.get("taken_at") or "")[:10]} · {e.get("type")} · '
            f'[{e["code"]}]({e.get("url") or ""}) · {_clock(e.get("duration_s"))}')
    tickers = ', '.join(e.get('tickers') or [])
    lead = ' · '.join(x for x in (f'**{tickers}**' if tickers else '',
                                   e.get('stance') if e.get('stance') not in (None, 'none') else '') if x)
    lines = [head, f'{lead} — {e.get("one_line")}' if lead else e.get('one_line') or '']
    if e.get('type') not in compact:
        lines += [f'- {p}' for p in e.get('points') or []]
        fields = {k: v for k, v in (e.get('fields') or {}).items() if v not in (None, '', 'not stated', [])}
        lines += [f'- {k.replace("_", " ").capitalize()}: {", ".join(map(str, v)) if isinstance(v, list) else v}'
                  for k, v in fields.items()]
        if e.get('levels'):
            lines.append('- Levels (as stated): ' + '; '.join(e['levels']))
    if e.get('unverified_numbers'):
        lines.append(f'- _Unverified numbers: {", ".join(e["unverified_numbers"])}_')
    return lines + ['']


def render_month(entries: list[dict], username: str, month: str, compact: set[str]) -> str:
    rows = sorted((e for e in entries if (e.get('username') or 'unknown') == username
                   and month_of(e.get('taken_at')) == month),
                  key=lambda e: (e.get('taken_at') or '', e['code']), reverse=True)
    creator = next((e.get('creator') for e in rows if e.get('creator')), username)
    mix = Counter(e.get('type') for e in rows)
    lines = [f'# {creator}: reels {month}', '',
             f'Generated from reels.jsonl; do not edit. {len(rows)} reel(s): '
             + ', '.join(f'{t} {n}' for t, n in mix.most_common()), '']
    for e in rows:
        lines += render_entry(e, compact)
    return '\n'.join(lines).rstrip() + '\n'


def render_months(store: ReelStore, months: set | None = None, types: list[ReelType] | None = None) -> list[Path]:
    """Re-write the given (username, month) files, or every one when `months` is None."""
    entries = list(store.load_index().values())
    if months is None:
        months = {(e.get('username') or 'unknown', month_of(e.get('taken_at'))) for e in entries}
    compact = compact_types(types if types is not None else load_types())
    written = []
    for username, month in sorted(months):
        path = store.notes_dir / username / f'{month}.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_month(entries, username, month, compact), encoding='utf-8')
        written.append(path)
    return written


# ---- trial report ------------------------------------------------------------
def _pct(part: int, whole: int) -> str:
    return f'{round(100 * part / whole)}%' if whole else '-'


def trial_report(store: ReelStore, since: datetime | None = None) -> str:
    entries = [e for e in store.load_index().values()
               if since is None or (parse_ts(e.get('taken_at')) or since) >= since]
    total = len(entries)
    lines = ['# Reels trial report', '', f'Generated {iso(utcnow())} from {total} summarized reel(s)'
             + (f' published since {since.date()}' if since else '') + '. Generated file; re-run `run.py reels trial-report`.', '']
    if not total:
        return '\n'.join(lines + ['_No reels summarized yet._']) + '\n'

    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_type[e.get('type') or '?'].append(e)
    lines += ['## Types', '', '| type | reels | share | creators | median length | with tickers | with levels | on-screen refs |',
              '|---|---|---|---|---|---|---|---|']
    for name, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        durations = [e['duration_s'] for e in group if e.get('duration_s')]
        lines.append(f'| {name} | {len(group)} | {_pct(len(group), total)} | {len({e.get("username") for e in group})} | '
                     f'{_clock(statistics.median(durations)) if durations else "?"} | '
                     f'{_pct(sum(1 for e in group if e.get("tickers")), len(group))} | '
                     f'{_pct(sum(1 for e in group if e.get("levels")), len(group))} | '
                     f'{_pct(sum(1 for e in group if e.get("on_screen")), len(group))} |')
    lines += ['', '### Examples', '']
    for name, group in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        lines.append(f'**{name}**')
        for e in sorted(group, key=lambda e: e.get('taken_at') or '', reverse=True)[:3]:
            why = f' _(why: {e["type_reason"]})_' if e.get('type_reason') else ''
            lines.append(f'- {e.get("creator")}: {e.get("one_line")}{why}')
        lines.append('')

    lines += ['## Creators', '', '| creator | reels | per week | type mix |', '|---|---|---|---|']
    by_creator: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_creator[e.get('creator') or e.get('username') or '?'].append(e)
    for name, group in sorted(by_creator.items(), key=lambda kv: -len(kv[1])):
        stamps = sorted(t for t in (parse_ts(e.get('taken_at')) for e in group) if t)
        weeks = max((stamps[-1] - stamps[0]).days / 7, 1) if len(stamps) > 1 else 1
        mix = ', '.join(f'{t} {n}' for t, n in Counter(e.get('type') for e in group).most_common())
        lines.append(f'| {name} | {len(group)} | {len(group) / weeks:.1f} | {mix} |')

    speech = sum(1 for e in entries if e.get('speech'))
    flagged = sum(1 for e in entries if e.get('unverified_numbers'))
    lines += ['', '## Evidence', '', f'- With speech: {speech} ({_pct(speech, total)}); caption only: {total - speech}.',
              f'- Refers to something on screen: {sum(1 for e in entries if e.get("on_screen"))} '
              f'({_pct(sum(1 for e in entries if e.get("on_screen")), total)}); the frames question in the plan.',
              f'- Kept with unverified numbers: {flagged} ({_pct(flagged, total)}).', '']

    costs = [r for r in _cost_rows(store) if r.get('reels')]
    if costs:
        lines += ['## Cost by batch size', '', '| mode | batch size | batches | reels | accepted | calls | $ per reel | output tokens per reel |',
                  '|---|---|---|---|---|---|---|---|']
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in costs:
            groups[(r.get('mode'), r.get('batch_size'))].append(r)
        for (mode, size), rows in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), kv[0][1] or 0)):
            reels = sum(r['reels'] for r in rows)
            cost = sum(r.get('cost_usd') or 0 for r in rows)
            out_tokens = sum(r.get('output_tokens') or 0 for r in rows)
            lines.append(f'| {mode} | {size} | {len(rows)} | {reels} | {sum(r.get("accepted", 0) for r in rows)} | '
                         f'{sum(r.get("calls", 0) for r in rows)} | {cost / reels:.4f} | {out_tokens / reels:.0f} |')
        gemini = [r.get('gemini_tokens') for r in store.all_transcripts() if isinstance(r.get('gemini_tokens'), int)]
        if gemini:
            lines += ['', f'Gemini transcription: {len(gemini)} reel(s), {statistics.mean(gemini):.0f} tokens per reel on average.']
    return '\n'.join(lines).rstrip() + '\n'


def _cost_rows(store: ReelStore) -> list[dict]:
    return read_jsonl(store.cost_file)


def since_arg(value: str, now: datetime) -> datetime:
    """`30d` or `YYYY-MM-DD` -> a UTC moment."""
    value = value.strip().lower()
    if value.endswith('d') and value[:-1].isdigit():
        return now - timedelta(days=int(value[:-1]))
    moment = parse_ts(value if 'T' in value else value + 'T00:00:00Z')
    if moment is None:
        raise ValueError(f'--since must look like 30d or 2026-09-22, got {value!r}')
    return moment
