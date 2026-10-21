#!/usr/bin/env python3
"""Folder-based queue state. No database: every item is a small JSON file and moving it is the state change.

  pending/<id>.json     waiting
  processing/<id>.json  claimed by a run (stale after STALE_CLAIM_HOURS)
  failed/<id>.json      gave up
  done/<id>.json        handoff manifest (written in phase 2)
  skipped.jsonl         append-only record of videos deliberately not queued
  state.json            per-channel etag / last poll / failure count
  run.lock              one run at a time
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import STALE_CLAIM_HOURS, Paths
from urls import VIDEO_ID

AGING_CAP_DAYS = 20
MANUAL_PRIORITY = 100
NOW_PRIORITY = 1000
STAGES = ('pending', 'processing', 'failed', 'done')


class LockHeld(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def write_json(path: Path, obj) -> None:
    """Atomic replace so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


class Store:
    def __init__(self, paths: Paths):
        self.paths = paths
        root = paths.state
        self.dirs = {name: root / name for name in STAGES}
        self.inbox = root / 'inbox'
        self.skipped_file = root / 'skipped.jsonl'
        self.state_file = root / 'state.json'
        self.lock_file = root / 'run.lock'
        self.queue_md = root / 'QUEUE.md'

    def ensure(self) -> None:
        for folder in (*self.dirs.values(), self.inbox, self.inbox / 'done', self.paths.logs):
            folder.mkdir(parents=True, exist_ok=True)

    # ---- channel state -------------------------------------------------
    def load_state(self) -> dict:
        state = read_json(self.state_file, {}) or {}
        state.setdefault('channels', {})
        state.setdefault('refs', {})
        return state

    def save_state(self, state: dict) -> None:
        write_json(self.state_file, state)

    # ---- items ---------------------------------------------------------
    def item_path(self, stage: str, video_id: str) -> Path:
        return self.dirs[stage] / f'{video_id}.json'

    def find(self, video_id: str) -> tuple[str, dict] | None:
        for stage in STAGES:
            item = read_json(self.item_path(stage, video_id))
            if item is not None:
                return stage, item
        return None

    def skipped_ids(self) -> set[str]:
        ids = set()
        try:
            with self.skipped_file.open(encoding='utf-8') as handle:
                for line in handle:
                    try:
                        ids.add(json.loads(line)['video_id'])
                    except (json.JSONDecodeError, KeyError):
                        continue
        except FileNotFoundError:
            pass
        return ids

    def noted_ids(self) -> set[str]:
        """Ids that already have a note: filename is `<id>-slug.md` or `<id>.md`."""
        ids = set()
        try:
            names = [p.name for p in self.paths.notes.iterdir() if p.suffix == '.md']
        except FileNotFoundError:
            return ids
        for name in names:
            head = name[:11]
            rest = name[11:]
            if VIDEO_ID.fullmatch(head) and (rest == '.md' or rest.startswith('-')):
                ids.add(head)
        return ids

    def known_ids(self) -> set[str]:
        ids = self.skipped_ids() | self.noted_ids()
        for stage in STAGES:
            try:
                ids.update(p.stem for p in self.dirs[stage].glob('*.json'))
            except FileNotFoundError:
                pass
        return ids

    def add_pending(self, item: dict) -> None:
        write_json(self.item_path('pending', item['video_id']), item)

    def remove(self, stage: str, video_id: str) -> None:
        self.item_path(stage, video_id).unlink(missing_ok=True)

    def move(self, video_id: str, src: str, dst: str) -> dict | None:
        source, target = self.item_path(src, video_id), self.item_path(dst, video_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
        except FileNotFoundError:
            return None
        return read_json(target)

    def record_skip(self, video_id: str, reason: str, now: datetime, title: str | None = None) -> None:
        self.skipped_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {'video_id': video_id, 'reason': reason, 'date': iso(now), 'title': title}
        with self.skipped_file.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')

    # ---- ordering and claiming ----------------------------------------
    @staticmethod
    def effective_priority(item: dict, now: datetime) -> int:
        priority = int(item.get('priority', 0))
        if item.get('origin') == 'rss':
            queued = parse_ts(item.get('discovered_at')) or now
            priority += min(max((now - queued).days, 0), AGING_CAP_DAYS)
        return priority

    def pending_items(self, now: datetime, include_deferred: bool = False) -> list[dict]:
        items = []
        for path in self.dirs['pending'].glob('*.json'):
            item = read_json(path)
            if not item or 'video_id' not in item:
                continue
            hold = parse_ts(item.get('not_before'))
            if hold and hold > now and not include_deferred:
                continue
            items.append(item)
        items.sort(key=lambda i: i.get('published_at') or '', reverse=True)
        items.sort(key=lambda i: -self.effective_priority(i, now))
        return items

    def claim_next(self, limit: int | None, now: datetime) -> list[dict]:
        """Move the best pending items to processing/. Manual items are never held back by `limit`."""
        claimed = []
        taken = 0
        for item in self.pending_items(now):
            manual = item.get('origin') == 'manual'
            if limit is not None and not manual and taken >= limit:
                continue
            moved = self.move(item['video_id'], 'pending', 'processing')
            if moved is None:
                continue
            moved['claimed_at'] = iso(now)
            write_json(self.item_path('processing', moved['video_id']), moved)
            claimed.append(moved)
            if not manual:
                taken += 1
        return claimed

    def claim_one(self, now: datetime) -> dict | None:
        """Claim the single best due item (the processing loop takes one at a time so it can stop on budget)."""
        for item in self.pending_items(now):
            moved = self.move(item['video_id'], 'pending', 'processing')
            if moved is None:
                continue
            moved['claimed_at'] = iso(now)
            write_json(self.item_path('processing', moved['video_id']), moved)
            return moved
        return None

    def recover_stale(self, now: datetime) -> list[str]:
        released = []
        cutoff = timedelta(hours=STALE_CLAIM_HOURS)
        for path in self.dirs['processing'].glob('*.json'):
            item = read_json(path)
            if not item:
                continue
            claimed = parse_ts(item.get('claimed_at'))
            if claimed is None:
                claimed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if now - claimed < cutoff:
                continue
            moved = self.move(path.stem, 'processing', 'pending')
            if moved is not None:
                moved.pop('claimed_at', None)
                write_json(self.item_path('pending', path.stem), moved)
                released.append(path.stem)
        return released

    # ---- run lock ------------------------------------------------------
    def acquire_lock(self, now: datetime) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'pid': os.getpid(), 'started': iso(now)})
        for attempt in (1, 2):
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                existing = read_json(self.lock_file, {}) or {}
                started = parse_ts(existing.get('started'))
                if attempt == 1 and (started is None or now - started >= timedelta(hours=STALE_CLAIM_HOURS)):
                    self.lock_file.unlink(missing_ok=True)  # stale: previous run died
                    continue
                raise LockHeld(f'another run holds {self.lock_file} (pid {existing.get("pid")}, since {existing.get("started")})')
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(payload)
            return

    def release_lock(self) -> None:
        existing = read_json(self.lock_file, {}) or {}
        if existing.get('pid') == os.getpid():
            self.lock_file.unlink(missing_ok=True)

    # ---- reporting -----------------------------------------------------
    def counts(self) -> dict[str, int]:
        counts = {stage: len(list(self.dirs[stage].glob('*.json'))) for stage in STAGES}
        counts['skipped'] = len(self.skipped_ids())
        counts['inbox_files'] = len(list(self.inbox.glob('*.txt')))
        return counts

    # ---- human-readable view -------------------------------------------
    def recent_skips(self, limit: int = 25) -> list[dict]:
        rows = []
        try:
            with self.skipped_file.open(encoding='utf-8') as handle:
                for line in handle:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        return rows[-limit:][::-1]

    def render_queue_md(self, now: datetime) -> str:
        def row(i: int, item: dict) -> str:
            minutes = f'{round(item["duration_s"] / 60)} min' if item.get('duration_s') else '?'
            title = (item.get('title') or item['video_id']).replace('|', '/')
            hold = f' (waits until {item["not_before"]})' if item.get('not_before') else ''
            return (f'| {i} | {self.effective_priority(item, now)} | {item.get("origin", "")} | '
                    f'{item.get("channel_name") or "-"} | {(item.get("published_at") or "")[:10]} | {minutes} | '
                    f'[{title}]({item.get("url", "")}){hold} |')

        header = '| # | priority | origin | channel | published | length | video |\n|---|---|---|---|---|---|---|'
        counts = self.counts()
        lines = [f'# Ingest queue', '', f'Updated {iso(now)}. Generated file; do not edit.', '',
                 '  '.join(f'**{k}** {v}' for k, v in counts.items()), '']
        sections = [('Pending (in the order they will be processed)', self.pending_items(now, include_deferred=True)),
                    ('Processing', [read_json(p) for p in sorted(self.dirs['processing'].glob('*.json'))]),
                    ('Failed', [read_json(p) for p in sorted(self.dirs['failed'].glob('*.json'))])]
        for title, items in sections:
            items = [i for i in items if i]
            lines += [f'## {title}', '']
            if items:
                lines += [header, *(row(n, i) for n, i in enumerate(items, 1))]
            else:
                lines.append('_none_')
            lines.append('')
        skips = self.recent_skips()
        lines += ['## Recently skipped (newest first, last 25)', '']
        if skips:
            lines += ['| date | reason | video |', '|---|---|---|']
            lines += [f'| {s.get("date", "")[:10]} | {s.get("reason")} | '
                      f'[{(s.get("title") or s["video_id"]).replace("|", "/")}](https://www.youtube.com/watch?v={s["video_id"]}) |'
                      for s in skips]
        else:
            lines.append('_none_')
        return '\n'.join(lines) + '\n'

    def write_queue_md(self, now: datetime) -> None:
        self.queue_md.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.queue_md.with_name(self.queue_md.name + '.tmp')
        tmp.write_text(self.render_queue_md(now), encoding='utf-8')
        os.replace(tmp, self.queue_md)
