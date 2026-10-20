#!/usr/bin/env python3
"""Manual adds: CLI `add` and the inbox drop folder share one code path. Manual items bypass every filter."""
from __future__ import annotations

from datetime import datetime

from store import MANUAL_PRIORITY, NOW_PRIORITY, Store, iso
from urls import extract_video_id, watch_url
from ytnet import NetError, Unavailable


def add_manual(store: Store, net, url: str, now: datetime, *, now_flag: bool = False,
               priority: int | None = None, force: bool = False) -> tuple[str, str, str | None]:
    """Return (status, message, video_id). Statuses: queued, updated, requeued, exists, in-progress, rejected."""
    video_id = extract_video_id(url)
    if not video_id:
        return 'rejected', 'not a YouTube video URL', None
    wanted = NOW_PRIORITY if now_flag else (MANUAL_PRIORITY if priority is None else priority)

    found = store.find(video_id)
    if found:
        stage, item = found
        if stage == 'processing':
            return 'in-progress', 'already being processed', video_id
        if stage == 'pending':
            item.update(origin='manual', priority=max(wanted, int(item.get('priority', 0))), not_before=None)
            store.add_pending(item)
            return 'updated', f'already queued; now manual priority {item["priority"]}', video_id
        if stage == 'done' and not force:
            return 'exists', 'already processed (use --force to redo)', video_id
        item.update(origin='manual', priority=wanted, attempts=0, not_before=None)
        item.pop('error', None)
        store.remove(stage, video_id)
        store.add_pending(item)
        return 'requeued', f'moved from {stage} back to pending', video_id
    if video_id in store.noted_ids() and not force:
        return 'exists', 'a note for this video already exists (use --force to redo)', video_id

    meta: dict = {}
    note = ''
    try:
        meta = net.video_meta(watch_url(video_id))
    except Unavailable:
        return 'rejected', 'video is unavailable', video_id
    except NetError as exc:
        note = f' (metadata lookup failed: {exc})'
    store.add_pending({
        'video_id': video_id,
        'url': watch_url(video_id),
        'title': meta.get('title'),
        'channel_id': meta.get('channel_id'),
        'channel_name': meta.get('channel'),
        'published_at': None,
        'discovered_at': iso(now),
        'origin': 'manual',
        'priority': wanted,
        'attempts': 0,
        'duration_s': meta.get('duration_s'),
        'not_before': None,
        'source': 'manual',
    })
    return 'queued', f'priority {wanted}{note}', video_id


def consume_inbox(store: Store, net, now: datetime, dry_run: bool = False) -> list[tuple[str, str, str | None]]:
    """Read every inbox/*.txt (one URL per line, # comments), add manual items, archive the file."""
    results = []
    for path in sorted(store.inbox.glob('*.txt')):
        if path.name == 'rejected.txt':
            continue
        try:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        except (OSError, UnicodeError):
            results.append(('rejected', f'cannot read {path.name}', None))
            continue
        rejected = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if dry_run:
                vid = extract_video_id(line)
                results.append(('would-add' if vid else 'rejected', line, vid))
                continue
            status, message, vid = add_manual(store, net, line, now)
            results.append((status, message, vid))
            if status == 'rejected':
                rejected.append(line)
        if dry_run:
            continue
        if rejected:
            with (store.inbox / 'rejected.txt').open('a', encoding='utf-8') as handle:
                handle.write('\n'.join(rejected) + '\n')
        archive = store.inbox / 'done' / f'{path.stem}-{now.strftime("%Y%m%dT%H%M%SZ")}.txt'
        archive.parent.mkdir(parents=True, exist_ok=True)
        path.replace(archive)
    return results
