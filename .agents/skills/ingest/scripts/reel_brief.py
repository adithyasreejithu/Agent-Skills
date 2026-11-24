#!/usr/bin/env python3
"""The reels brief: one file per day, <briefs>/<day>.reels.md, written from that day's reel summaries.

Separate from the video brief for now; the entries are compact JSON so they can later be inlined into it.
Claude (`claude -p`, no tools) writes the short read and the per-creator section from the summaries. The ticker
table and the list of reels are built here, mechanically, so they are always complete and cost nothing.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, tzinfo
from pathlib import Path
from typing import Callable

from brief import _sections, local_day, retry_prompt, unsourced_numbers
from process import SKILL_DIR, USAGE_KEYS, TextRun, add_usage, claude_text_runner
from reels import ReelType, load_types
from reelstore import ReelStore, append_jsonl
from store import iso, utcnow

PROMPT_NAME = 'reel-brief-prompt.md'
BRIEF_TIMEOUT_S = 10 * 60
SHORT_BULLETS = (3, 5)
SHORT_MAX_WORDS = 120
SKIP_OPEN = ('promo', 'lifestyle', 'no-speech')
PROMPT_KEYS = ('code', 'creator', 'taken_at', 'type', 'one_line', 'tickers', 'stance', 'points', 'levels', 'fields')


@dataclass
class ReelBriefResult:
    path: Path
    generated: str
    reels: int
    included: int
    attempts: int
    problems: list[str]
    usage: dict = field(default_factory=dict)


def brief_rules(types: list[ReelType] | None) -> tuple[set[str], set[str]]:
    """(skip, count-only) type names."""
    if types is None:
        return set(SKIP_OPEN), set()
    return {t.name for t in types if t.brief == 'skip'}, {t.name for t in types if t.brief == 'count-only'}


def day_entries(store: ReelStore, day: date, tz: tzinfo | None = None) -> list[dict]:
    rows = [e for e in store.load_index().values() if local_day(e.get('ingested_at'), tz) == day]
    return sorted(rows, key=lambda e: (e.get('creator') or '', e.get('taken_at') or ''))


def prompt_template(paths) -> str:
    for path in (paths.home / PROMPT_NAME, SKILL_DIR / PROMPT_NAME):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise FileNotFoundError(f'no {PROMPT_NAME} in {paths.home} or {SKILL_DIR}')


def build_prompt(template: str, day: date, included: list[dict], counted: dict[str, int]) -> str:
    compact = '\n'.join(json.dumps({k: e.get(k) for k in PROMPT_KEYS if e.get(k) not in (None, [], {}, '')},
                                   ensure_ascii=False) for e in included)
    counts = ', '.join(f'{k}: {v}' for k, v in sorted(counted.items())) or 'none'
    values = {'date': day.isoformat(), 'reel_count': len(included),
              'creators': ', '.join(sorted({e.get('creator') or '?' for e in included})),
              'reels': compact, 'counted': counts}
    out = template
    for key, value in values.items():
        out = out.replace('{' + key + '}', str(value))
    return out


def clean_body(text: str) -> str:
    start = text.find('## Short read')
    body = text[start:] if start >= 0 else text
    return re.split(r'^## (?:Tickers mentioned|Reels)\s*$', body, maxsplit=1, flags=re.M)[0].strip()


def validate(body: str, included: list[dict]) -> list[str]:
    problems = []
    found = _sections(body)
    short, by_creator = found.get('short read'), found.get('by creator')
    sources = [json.dumps(e, ensure_ascii=False) for e in included]
    if short is None:
        problems.append('missing "## Short read"')
    else:
        bullets = [l for l in short.splitlines() if l.startswith('- ')]
        low, high = SHORT_BULLETS
        if not low <= len(bullets) <= high:
            problems.append(f'the short read has {len(bullets)} bullets; it needs {low} to {high}')
        if len(short.split()) > SHORT_MAX_WORDS:
            problems.append(f'the short read is {len(short.split())} words; the limit is {SHORT_MAX_WORDS}')
        unknown = unsourced_numbers(short, sources)
        if unknown:
            problems.append('short-read numbers not found in any reel summary: ' + ', '.join(unknown[:8]))
    if by_creator is None:
        problems.append('missing "## By creator"')
    else:
        subs = [h.lower() for h in re.findall(r'^###\s+(.+?)\s*$', by_creator, re.M)]
        for creator in sorted({e.get('creator') or '?' for e in included}):
            if not any(creator.lower() in h for h in subs):
                problems.append(f'"## By creator" has no "### {creator}" section')
        unknown = unsourced_numbers(by_creator, sources)
        if unknown:
            problems.append('by-creator numbers not found in any reel summary: ' + ', '.join(unknown[:8]))
    return problems


def tickers_table(included: list[dict]) -> list[str]:
    rows: dict[str, dict] = defaultdict(lambda: {'creators': set(), 'stances': set(), 'levels': []})
    for e in included:
        for t in e.get('tickers') or []:
            rows[t]['creators'].add(e.get('creator') or '?')
            if e.get('stance') not in (None, 'none'):
                rows[t]['stances'].add(e['stance'])
            # A one-ticker reel's levels are that ticker's; otherwise only levels that name the ticker.
            sole = len(e.get('tickers') or []) == 1
            rows[t]['levels'] += [l for l in e.get('levels') or [] if sole or t in l.upper()]
    if not rows:
        return ['_No tickers today._']
    lines = ['| ticker | creators | stance | levels as stated |', '|---|---|---|---|']
    for t in sorted(rows, key=lambda k: (-len(rows[k]['creators']), k)):
        r = rows[t]
        lines.append(f'| {t} | {", ".join(sorted(r["creators"]))} | {", ".join(sorted(r["stances"])) or "-"} | '
                     f'{"; ".join(dict.fromkeys(r["levels"])).replace("|", "/") or "-"} |')
    return lines


def reel_lines(entries: list[dict], brief_dir: Path, notes_dir: Path) -> list[str]:
    lines = []
    for e in entries:
        month = notes_dir / (e.get('username') or 'unknown') / f'{(e.get("taken_at") or "undated")[:7]}.md'
        link = Path(os.path.relpath(month, brief_dir)).as_posix()
        lines.append(f'- {(e.get("taken_at") or "")[:10]} · **{e.get("creator")}** · {e.get("type")} · '
                     f'[{e["code"]}]({e.get("url")}) ([notes]({link})): {e.get("one_line")}')
    return lines


def fallback_body(included: list[dict], counted: dict[str, int], reason: str) -> str:
    lines = ['## Short read', f'_The written brief is unavailable ({reason[:160]}). This is the mechanical summary._', '']
    by_creator: dict[str, list[dict]] = defaultdict(list)
    for e in included:
        by_creator[e.get('creator') or '?'].append(e)
    for creator, rows in sorted(by_creator.items()):
        tickers = list(dict.fromkeys(t for e in rows for t in e.get('tickers') or []))
        lines.append(f'- **{creator}**: {len(rows)} reel(s); tickers: {", ".join(tickers) or "none"}')
    lines += ['', '## By creator']
    for creator, rows in sorted(by_creator.items()):
        lines += ['', f'### {creator}', *(f'- {e.get("type")}: {e.get("one_line")}' for e in rows)]
    if counted:
        lines += ['', 'Not summarized here: ' + ', '.join(f'{k} {v}' for k, v in sorted(counted.items()))]
    return '\n'.join(lines)


def assemble(day: date, entries: list[dict], included: list[dict], generated: str, body: str,
             brief_dir: Path, notes_dir: Path) -> str:
    creators = ', '.join(sorted({e.get('creator') or '?' for e in entries}))
    head = ['---', f'date: {day.isoformat()}', f'reels: {len(entries)}', f'included: {len(included)}',
            f'creators: [{creators}]', f'generated: {generated}', '---', '', f'# Reels brief {day.isoformat()}', '']
    return '\n'.join(head + [body.strip(), '', '## Tickers mentioned', *tickers_table(included), '',
                             '## Reels', *reel_lines(entries, brief_dir, notes_dir)]) + '\n'


def write_reel_brief(store: ReelStore, day: date, *, runner: Callable[[str], TextRun] | None = None,
                     template: str | None = None, types: list[ReelType] | None = None,
                     tz: tzinfo | None = None) -> ReelBriefResult | None:
    """Write <briefs>/<day>.reels.md from every reel summarized that day. None when there were none."""
    runner = runner or (lambda prompt: claude_text_runner(prompt, BRIEF_TIMEOUT_S))
    entries = day_entries(store, day, tz)
    if not entries:
        return None
    skip, count_only = brief_rules(types if types is not None else load_types())
    included = [e for e in entries if e.get('type') not in skip | count_only]
    counted: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.get('type') in skip | count_only:
            counted[e.get('type')] += 1
    path = store.paths.briefs / f'{day.isoformat()}.reels.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    usage: dict = {}
    body, problems, attempts = None, [], 0
    if included:
        prompt = build_prompt(template or prompt_template(store.paths), day, included, counted)
        for attempts in (1, 2):
            run = runner(prompt if attempts == 1 else retry_prompt(prompt, problems))
            add_usage(usage, run.usage)
            if run.returncode != 0:
                problems = [f'claude exit {run.returncode}: {run.text.strip()[-200:] or "no output"}']
                continue
            candidate = clean_body(run.text)
            problems = validate(candidate, included)
            if not problems:
                body = candidate
                break
    else:
        problems = ['every reel today was a type the brief leaves out']
    generated = 'claude' if body is not None else 'fallback'
    text = assemble(day, entries, included, generated,
                    body if body is not None else fallback_body(included, counted, problems[0]),
                    path.parent, store.notes_dir)
    path.write_text(text, encoding='utf-8')
    result = ReelBriefResult(path, generated, len(entries), len(included), attempts,
                             [] if body is not None else problems, usage)
    append_jsonl(store.paths.briefs / '_cost.jsonl', {
        'ts': iso(utcnow()), 'date': day.isoformat(), 'file': path.name, 'kind': 'reels', 'reels': len(entries),
        'included': len(included), 'generated': generated, 'attempts': attempts,
        **{key: usage.get(key) for key in USAGE_KEYS}})
    return result
