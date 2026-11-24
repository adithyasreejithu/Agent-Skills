#!/usr/bin/env python3
"""Phase 3: one morning brief per day, written from that day's finished notes.

Claude (`claude -p` with no tools; the notes are inlined) writes a short read and a long read. Everything around it
is deterministic: pick the day's notes -> build the prompt -> validate -> write the file (or a mechanical fallback)
-> log the token cost. The runner is injectable so the whole step is testable without a model.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, tzinfo
from pathlib import Path
from typing import Callable

from config import Paths
from note import find_note
from process import SKILL_DIR, USAGE_KEYS, TextRun, add_usage, claude_text_runner
from store import Store, iso, parse_ts, read_json, utcnow

PROMPT_NAME = 'brief-prompt.md'
BRIEF_TIMEOUT_S = 10 * 60
SHORT_BULLETS = (5, 7)
SHORT_MAX_WORDS = 180
EXEMPT_MAX = 10                 # small counts ("2 videos", "3 puts") need not appear in a note
NUMBER = re.compile(r'\d[\d,]*(?:\.\d+)?')


@dataclass
class Entry:
    manifest: dict
    note: Path
    text: str

    @property
    def channel(self) -> str:
        return self.manifest.get('channel') or '?'


BriefRun = TextRun
BriefRunner = Callable[[str], BriefRun]


@dataclass
class BriefResult:
    path: Path
    generated: str              # claude | fallback
    videos: int
    history_notes: int
    attempts: int
    problems: list[str]         # why it fell back; empty when Claude's brief passed
    usage: dict
    retry_reasons: list[str] = field(default_factory=list)   # what the first draft got wrong, when it was retried


# ---- choosing the notes ---------------------------------------------------
def local_day(value: str | None, tz: tzinfo | None = None) -> date | None:
    """The run day as the reader sees it (local time by default), not the UTC date."""
    moment = parse_ts(value)
    return moment.astimezone(tz).date() if moment else None


def done_manifests(store: Store) -> list[dict]:
    return [m for m in (read_json(p) for p in sorted(store.dirs['done'].glob('*.json'))) if m and m.get('video_id')]


def _entries(manifests: list[dict], notes_dir: Path | None = None) -> list[Entry]:
    """Each manifest with its note text. The stored path can go stale when the notes folder moves, so fall back to
    finding the note by video id in the current notes folder."""
    out = []
    for m in manifests:
        path = Path(m['note']) if m.get('note') else None
        if (path is None or not path.is_file()) and notes_dir is not None:
            path = find_note(notes_dir, m['video_id']) or path
        if path is None:
            continue
        try:
            out.append(Entry(m, path, path.read_text(encoding='utf-8')))
        except OSError:
            continue
    return out


def day_batch(store: Store, day: date, tz: tzinfo | None = None) -> list[Entry]:
    """Every video finished on `day`, so a second run that day rebuilds the brief with all of them."""
    chosen = [m for m in done_manifests(store) if local_day(m.get('ingested_at'), tz) == day]
    chosen.sort(key=lambda m: (m.get('channel') or '', m.get('published_at') or ''))
    return _entries(chosen, store.paths.notes)


def history_notes(store: Store, batch: list[Entry]) -> list[Entry]:
    """Each batch creator's most recent earlier video that is not itself in the batch."""
    in_batch = {e.manifest['video_id'] for e in batch}
    first: dict[str, str] = {}
    for e in batch:
        published = e.manifest.get('published_at') or ''
        first[e.channel] = min(first.get(e.channel, published), published)
    everything = done_manifests(store)
    picks = []
    for channel, earliest in sorted(first.items()):
        older = [m for m in everything if m.get('channel') == channel and m['video_id'] not in in_batch
                 and (m.get('published_at') or '') < earliest]
        if older:
            picks.append(max(older, key=lambda m: m.get('published_at') or ''))
    return _entries(picks, store.paths.notes)


# ---- the prompt -------------------------------------------------------------
def prompt_template(paths: Paths) -> str:
    for path in (paths.home / PROMPT_NAME, SKILL_DIR / PROMPT_NAME):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise FileNotFoundError(f'no {PROMPT_NAME} in {paths.home} or {SKILL_DIR}')


def note_body(text: str) -> str:
    """Drop the "Stored data" line: a local path, of no use to the model or the reader."""
    return '\n'.join(line for line in text.splitlines() if not line.startswith('- Stored data:')).strip()


def _render(entries: list[Entry], tag: str) -> str:
    return '\n\n'.join(f'<{tag} video_id="{e.manifest["video_id"]}">\n{note_body(e.text)}\n</{tag}>' for e in entries)


HISTORY_ON = ('Earlier notes, one per creator: their most recent video before today\'s. Use them only to say what '
              'changed.\n\n{notes}')
HISTORY_NONE = 'No earlier notes are on file for these creators.'
CHANGED_BULLET = '- **Changed:** what differs from their previous video (only when it matters)\n'
CHANGED_SECTION = ('### What changed since their last video\n'
                   'Per creator, compare today with their earlier note: positions that appeared or disappeared, strikes '
                   'or levels that moved, stance flips. You see only that one earlier video, so write "not in their last '
                   'video", never "new" on its own. For a creator with no earlier note, write "No earlier video on '
                   'file."\n\n')


def build_brief_prompt(template: str, day: date, batch: list[Entry], history: list[Entry]) -> str:
    """`history` is each creator's earlier note; empty when nothing earlier exists."""
    block = HISTORY_ON.format(notes=_render(history, 'earlier_note')) if history else HISTORY_NONE
    values = {'date': day.isoformat(), 'video_count': len(batch),
              'channels': ', '.join(sorted({e.channel for e in batch})), 'notes': _render(batch, 'note'),
              'history_block': block, 'changed_bullet': CHANGED_BULLET, 'changed_section': CHANGED_SECTION}
    out = template
    for key, value in values.items():          # plain replace: the notes contain braces we must not interpret
        out = out.replace('{' + key + '}', str(value))
    return out


def retry_prompt(prompt: str, problems: list[str]) -> str:
    return (prompt + '\n\nYour previous draft broke these rules. Write the whole brief again and fix them:\n'
            + '\n'.join(f'- {p}' for p in problems))


# ---- checking what came back ----------------------------------------------
def clean_body(text: str) -> str:
    """Keep only the sections we asked for: drop chatter before "## Short read" and any Videos list we add ourselves."""
    start = text.find('## Short read')
    body = text[start:] if start >= 0 else text
    body = re.split(r'^## Videos\s*$', body, maxsplit=1, flags=re.M)[0]
    return body.strip()


def _sections(body: str) -> dict[str, str]:
    parts = re.split(r'^## (.+?)\s*$', body, flags=re.M)
    return {parts[i].strip().lower(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def _numbers(text: str) -> list[str]:
    return [m.group().replace(',', '') for m in NUMBER.finditer(text)]


def unsourced_numbers(text: str, sources: list[str]) -> list[str]:
    """Numbers in `text` that no source note contains, allowing rounding to the precision written."""
    pool = {float(n) for source in sources for n in _numbers(source)}
    missing = []
    for raw in _numbers(text):
        value = float(raw)
        if '.' not in raw and value <= EXEMPT_MAX:
            continue
        decimals = len(raw.split('.')[1]) if '.' in raw else 0
        tolerance = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(value - known) <= tolerance for known in pool):
            missing.append(raw)
    return missing


def validate_brief(body: str, batch: list[Entry], sources: list[str]) -> list[str]:
    """Return a list of problems; empty means the brief meets the contract."""
    problems = []
    found = _sections(body)
    short, long = found.get('short read'), found.get('long read')
    if short is None:
        problems.append('missing "## Short read"')
    else:
        bullets = [line for line in short.splitlines() if line.startswith('- ')]
        low, high = SHORT_BULLETS
        if not low <= len(bullets) <= high:
            problems.append(f'the short read has {len(bullets)} bullets; it needs {low} to {high}')
        words = len(short.split())
        if words > SHORT_MAX_WORDS:
            problems.append(f'the short read is {words} words; the limit is {SHORT_MAX_WORDS}')
        unknown = unsourced_numbers(short, sources)
        if unknown:
            problems.append('short-read numbers not found in any note: ' + ', '.join(unknown[:8]))
    if long is None:
        problems.append('missing "## Long read"')
    else:
        subs = [h.lower() for h in re.findall(r'^###\s+(.+?)\s*$', long, re.M)]
        for need in ('Market dashboard', 'Stocks', 'Options', 'Calendar'):
            if need.lower() not in subs:
                problems.append(f'the long read is missing "### {need}"')
        if not any('what changed' in h for h in subs):
            problems.append('the long read is missing "### What changed since their last video"')
        for channel in sorted({e.channel for e in batch}):
            if channel.lower() not in long.lower():
                problems.append(f'the long read never names "{channel}"')
    return problems


# ---- writing the file -----------------------------------------------------
def video_lines(batch: list[Entry], brief_dir: Path) -> list[str]:
    lines = []
    for e in batch:
        m = e.manifest
        link = Path(os.path.relpath(e.note, brief_dir)).as_posix()
        tickers = ', '.join(m.get('tickers') or []) or 'none tagged'
        lines.append(f'- **{e.channel}**: [{m.get("title")}]({link}) ({m.get("stance") or "no stance"}; tickers: {tickers})')
    return lines


def fallback_body(batch: list[Entry], reason: str) -> str:
    """What the reader gets when Claude's brief is missing or keeps failing the checks: still one line per creator."""
    lines = ['## Short read', f'_The written brief is unavailable ({reason[:160]}). This is the mechanical summary._', '']
    for channel in sorted({e.channel for e in batch}):
        mine = [e.manifest for e in batch if e.channel == channel]
        stances = ', '.join(sorted({m.get('stance') or 'no stance' for m in mine}))
        tickers = list(dict.fromkeys(t for m in mine for t in m.get('tickers') or []))
        lines.append(f'- **{channel}**: {len(mine)} video(s); stance {stances}; tickers: {", ".join(tickers) or "none tagged"}')
    lines += ['', '## Long read', '_Not generated. Open the notes listed under "Videos"._']
    return '\n'.join(lines)


def assemble(day: date, batch: list[Entry], generated: str, body: str, brief_dir: Path) -> str:
    channels = ', '.join(sorted({e.channel for e in batch}))
    head = ['---', f'date: {day.isoformat()}', f'videos: {len(batch)}', f'channels: [{channels}]',
            f'generated: {generated}', '---', '',
            f'# Morning brief {day.isoformat()}', '']
    return '\n'.join(head + [body.strip(), '', '## Videos', *video_lines(batch, brief_dir)]) + '\n'


_add_usage = add_usage


def claude_brief_runner(prompt: str) -> BriefRun:
    # No tools at all: the notes are in the prompt, and the brief is pure writing.
    return claude_text_runner(prompt, BRIEF_TIMEOUT_S)


def write_brief(store: Store, day: date, *, runner: BriefRunner = claude_brief_runner,
                template: str | None = None, tz: tzinfo | None = None) -> BriefResult | None:
    """Write <briefs>/<day>.md from every video finished that day. None when nothing finished."""
    batch = day_batch(store, day, tz)
    if not batch:
        return None
    history = history_notes(store, batch)
    sources = [e.text for e in batch + history]
    prompt = build_brief_prompt(template or prompt_template(store.paths), day, batch, history)
    usage: dict = {}
    body, problems, attempts, first_problems = None, [], 0, []
    for attempts in (1, 2):
        if attempts == 2:
            first_problems = problems
        run = runner(prompt if attempts == 1 else retry_prompt(prompt, problems))
        _add_usage(usage, run.usage)
        if run.returncode != 0:
            problems = [f'claude exit {run.returncode}: {run.text.strip()[-200:] or "no output"}']
            continue
        candidate = clean_body(run.text)
        problems = validate_brief(candidate, batch, sources)
        if not problems:
            body = candidate
            break
    generated = 'claude' if body is not None else 'fallback'
    path = store.paths.briefs / f'{day.isoformat()}.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = assemble(day, batch, generated, body if body is not None else fallback_body(batch, problems[0]),
                    path.parent)
    path.write_text(text, encoding='utf-8')
    result = BriefResult(path, generated, len(batch), len(history), attempts,
                         [] if body is not None else problems, usage, first_problems)
    log_cost(store.paths.briefs, day, result)
    return result


def log_cost(brief_dir: Path, day: date, r: BriefResult) -> None:
    """One JSON line per brief in <briefs>/_cost.jsonl, so the token cost can be followed day by day."""
    entry = {'ts': iso(utcnow()), 'date': day.isoformat(), 'file': r.path.name,
             'videos': r.videos, 'history_notes': r.history_notes, 'generated': r.generated, 'attempts': r.attempts,
             **{key: r.usage.get(key) for key in USAGE_KEYS}, 'retry_reasons': r.retry_reasons}
    with (brief_dir / '_cost.jsonl').open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry) + '\n')

