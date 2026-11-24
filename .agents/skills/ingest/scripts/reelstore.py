#!/usr/bin/env python3
"""The reels queue and its two data files.

The queue is the ordinary folder Store on its own root (<home>/reels/), so reels get their own pending/,
processing/, failed/, run.lock and QUEUE.md. There are no done/ manifests: a reel is done when it has a line in
<reel_notes>/reels.jsonl, which keeps finished reels from leaving one file each.

  <reel_notes>/reels.jsonl                             one summary per reel (the source of truth)
  <reel_notes>/<username>/<YYYY-MM>.md                 generated reading view
  <raw>/reels/<username>/<YYYY-MM>.transcripts.jsonl   one transcript per reel (audio is not kept)
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from config import Paths
from store import Store


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    try:
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    os.replace(tmp, path)


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def month_of(stamp: str | None) -> str:
    return (stamp or '')[:7] or 'undated'


class ReelStore(Store):
    def __init__(self, paths: Paths):
        paths = paths.reels()
        super().__init__(replace(paths, state=paths.reels_state))
        self.notes_dir = paths.reel_notes
        self.index_file = self.notes_dir / 'reels.jsonl'
        self.cost_file = self.notes_dir / '_cost.jsonl'
        self.raw_dir = paths.raw / 'reels'

    # ---- summaries ---------------------------------------------------------
    def load_index(self) -> dict[str, dict]:
        """code -> entry; a later line for the same code replaces an earlier one."""
        return {row['code']: row for row in read_jsonl(self.index_file) if row.get('code')}

    def save_index(self, entries: dict[str, dict]) -> None:
        rows = sorted(entries.values(), key=lambda e: (e.get('taken_at') or '', e['code']))
        write_jsonl(self.index_file, rows)

    def noted_ids(self) -> set[str]:
        return set(self.load_index())

    # ---- transcripts ---------------------------------------------------------
    def transcript_file(self, username: str, taken_at: str | None) -> Path:
        return self.raw_dir / (username or 'unknown') / f'{month_of(taken_at)}.transcripts.jsonl'

    def save_transcript(self, row: dict) -> None:
        path = self.transcript_file(row.get('username') or '', row.get('taken_at'))
        rows = [r for r in read_jsonl(path) if r.get('code') != row['code']]
        write_jsonl(path, rows + [row])

    def load_transcript(self, username: str, code: str, taken_at: str | None = None) -> dict | None:
        paths = [self.transcript_file(username, taken_at)]
        paths += sorted((self.raw_dir / (username or 'unknown')).glob('*.transcripts.jsonl'))
        for path in paths:
            for row in read_jsonl(path):
                if row.get('code') == code:
                    return row
        return None

    def all_transcripts(self) -> list[dict]:
        rows = []
        for path in sorted(self.raw_dir.glob('*/*.transcripts.jsonl')):
            rows += read_jsonl(path)
        return rows

    def skipped_reasons(self) -> dict[str, str]:
        return {r['video_id']: r.get('reason') for r in reversed(self.recent_skips(10 ** 9)) if r.get('video_id')}

    def render_queue_md(self, now) -> str:
        """The base view links skipped ids to YouTube; point them at Instagram instead."""
        return super().render_queue_md(now).replace('https://www.youtube.com/watch?v=', 'https://www.instagram.com/reel/')
