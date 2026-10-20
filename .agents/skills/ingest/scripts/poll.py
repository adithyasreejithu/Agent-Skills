#!/usr/bin/env python3
"""Poll channel feeds, filter, and queue new videos. Idempotent: a second poll queues nothing."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config import Source
from feed import FeedError, parse_feed
from filters import LIVE_STATUSES, age_reason, duration_reason, title_reason
from store import Store, iso, parse_ts
from ytnet import NetError, Unavailable

DEFER_HOURS = 6
FEED_WINDOW = 15
FAIL_FLAG_AFTER = 3


@dataclass
class Outcome:
    video_id: str
    title: str
    channel: str
    result: str          # queued | deferred | skipped | error
    detail: str = ''


@dataclass
class PollReport:
    polled: int = 0
    not_modified: int = 0
    outcomes: list[Outcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def count(self, result: str) -> int:
        return sum(1 for o in self.outcomes if o.result == result)


def _item(entry: dict, source: Source, meta: dict | None, now: datetime, not_before: str | None = None) -> dict:
    meta = meta or {}
    return {
        'video_id': entry['video_id'],
        'url': entry['url'],
        'title': entry['title'] or meta.get('title'),
        'channel_id': entry.get('channel_id'),
        'channel_name': entry.get('channel_name') or source.name,
        'published_at': entry.get('published_at'),
        'discovered_at': iso(now),
        'origin': 'rss',
        'priority': source.priority,
        'attempts': 0,
        'duration_s': meta.get('duration_s'),
        'not_before': not_before,
        'source': source.name,
    }


def process_entry(entry: dict, source: Source, store: Store, net, now: datetime, dry_run: bool) -> Outcome:
    vid, title = entry['video_id'], entry['title']
    channel = entry.get('channel_name') or source.name

    def skip(reason: str) -> Outcome:
        if not dry_run:
            store.record_skip(vid, reason, now, title)
        return Outcome(vid, title, channel, 'skipped', reason)

    reason = title_reason(title, source) or age_reason(entry.get('published_at'), source, now)
    if reason:
        return skip(reason)
    if source.skip_shorts and net.is_short(vid):
        return skip('short')
    try:
        meta = net.video_meta(entry['url'])
    except Unavailable:
        return skip('unavailable')
    except NetError as exc:
        return Outcome(vid, title, channel, 'error', str(exc))   # not recorded: retried next poll
    if meta.get('live_status') in LIVE_STATUSES:
        hold = iso(now + timedelta(hours=DEFER_HOURS))
        if not dry_run:
            store.add_pending(_item(entry, source, meta, now, not_before=hold))
        return Outcome(vid, title, channel, 'deferred', f'{meta["live_status"]}, hold until {hold}')
    reason = duration_reason(meta.get('duration_s'), source)
    if reason:
        return skip(reason)
    if not dry_run:
        store.add_pending(_item(entry, source, meta, now))
    return Outcome(vid, title, channel, 'queued', f'priority {source.priority}')


def recheck_deferred(store: Store, sources_by_channel: dict[str, Source], net, now: datetime,
                     report: PollReport, dry_run: bool) -> None:
    """Upcoming/live videos wait in pending/ with `not_before`; once due, check they have aired."""
    for item in store.pending_items(now, include_deferred=True):
        hold = parse_ts(item.get('not_before'))
        if not hold or hold > now:
            continue
        try:
            meta = net.video_meta(item['url'])
        except Unavailable:
            if not dry_run:
                store.remove('pending', item['video_id'])
                store.record_skip(item['video_id'], 'unavailable', now, item.get('title'))
            continue
        except NetError as exc:
            report.errors.append(f'{item["video_id"]}: {exc}')
            continue
        if dry_run:
            continue
        if meta.get('live_status') in LIVE_STATUSES:
            item['not_before'] = iso(now + timedelta(hours=DEFER_HOURS))
            store.add_pending(item)
            continue
        source = sources_by_channel.get(item.get('channel_id') or '')
        reason = duration_reason(meta.get('duration_s'), source) if source else None
        if reason:
            store.remove('pending', item['video_id'])
            store.record_skip(item['video_id'], reason, now, item.get('title'))
            continue
        item['not_before'] = None
        item['duration_s'] = meta.get('duration_s')
        store.add_pending(item)
        report.outcomes.append(Outcome(item['video_id'], item.get('title') or '', item.get('channel_name') or '',
                                       'queued', 'aired; released'))


def poll(store: Store, sources: list[Source], net, now: datetime, *, backfill: int | None = None,
         only: str | None = None, dry_run: bool = False, sleep=time.sleep) -> PollReport:
    report = PollReport()
    state = store.load_state()
    known = store.known_ids()
    sources_by_channel: dict[str, Source] = {}
    first_source = True

    for source in sources:
        if not source.enabled:
            continue
        if only and only.lower() not in {source.ref.lower(), source.name.lower()}:
            continue
        if not first_source:
            sleep(random.uniform(1.0, 2.0))
        first_source = False

        channel_id = source.channel_id or state['refs'].get(source.ref)
        try:
            if not channel_id:
                channel_id = net.resolve_channel(source.ref)
                if not dry_run:
                    state['refs'][source.ref] = channel_id
        except NetError as exc:
            report.errors.append(f'{source.name}: {exc}')
            continue
        sources_by_channel[channel_id] = source
        ch = state['channels'].setdefault(channel_id, {})
        ch.update(ref=source.ref, name=source.name)

        try:
            result = net.fetch_feed(channel_id, ch.get('etag'), ch.get('last_modified'))
            entries = [] if result.status == 304 else parse_feed(result.text or '')
        except (NetError, FeedError) as exc:
            ch['fail_count'] = ch.get('fail_count', 0) + 1
            ch['last_error'] = str(exc)
            report.errors.append(f'{source.name}: {exc}')
            if ch['fail_count'] >= FAIL_FLAG_AFTER:
                report.warnings.append(f'{source.name}: {ch["fail_count"]} failing polls in a row')
            if not dry_run:
                store.save_state(state)
            continue

        report.polled += 1
        ch['fail_count'] = 0
        ch.pop('last_error', None)
        ch['last_polled'] = iso(now)
        if result.status == 304:
            report.not_modified += 1
            if not dry_run:
                store.save_state(state)
            continue

        new = [e for e in entries if e['video_id'] not in known]
        first_poll = not ch.get('first_polled')
        if not first_poll and len(entries) >= FEED_WINDOW and len(new) == len(entries):
            report.warnings.append(f'{source.name}: all {len(entries)} feed entries are new; older uploads may have been missed')

        to_process = new
        if first_poll:
            keep = backfill or 0
            to_process, backlog = new[:keep], new[keep:]
            for entry in backlog:
                if not dry_run:
                    store.record_skip(entry['video_id'], 'backlog', now, entry['title'])
                known.add(entry['video_id'])
                report.outcomes.append(Outcome(entry['video_id'], entry['title'], source.name, 'skipped', 'backlog'))

        errored = False
        for entry in to_process:
            outcome = process_entry(entry, source, store, net, now, dry_run)
            report.outcomes.append(outcome)
            if outcome.result == 'error':
                errored = True
            else:
                known.add(entry['video_id'])

        if not dry_run:
            ch['first_polled'] = True
            # Only remember the validators when every entry was handled; otherwise a 304 next time
            # would hide the entries that still need a retry.
            if errored:
                ch.pop('etag', None)
                ch.pop('last_modified', None)
            else:
                if result.etag:
                    ch['etag'] = result.etag
                if result.last_modified:
                    ch['last_modified'] = result.last_modified
            store.save_state(state)

    recheck_deferred(store, sources_by_channel, net, now, report, dry_run)
    return report
