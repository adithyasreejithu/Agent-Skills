#!/usr/bin/env python3
"""Poll the vetted Instagram creators and queue their new reels. Idempotent: a second poll queues nothing.

The profile page lists reels newest first. Each reel not seen before costs one yt-dlp lookup (its date and
caption), so once a few in a row are past the age limit the rest are skipped without a lookup.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta

from config import ReelSource
from igweb import Blocked, Candidate, IgError, LoginWall, Unavailable
from poll import FAIL_FLAG_AFTER, Outcome, PollReport
from reelstore import ReelStore
from store import MANUAL_PRIORITY, NOW_PRIORITY, iso, parse_ts
from urls import extract_reel_code, reel_url

OLD_IN_A_ROW = 3                 # this many non-pinned reels past the limit and the rest are older still
META_GAP_S = (1.0, 2.5)
COOLDOWN_HOURS = 48


def page_meta(cand: Candidate) -> dict:
    return {'taken_at': cand.taken_at, 'caption': cand.caption or '', 'duration_s': cand.duration_s}


def title_of(caption: str | None, code: str) -> str:
    line = next((l.strip() for l in (caption or '').splitlines() if l.strip()), '')
    return (line[:80] + ('…' if len(line) > 80 else '')) if line else f'reel {code}'


def reel_item(code: str, meta: dict, *, name: str, username: str, priority: int, origin: str, now: datetime,
              cand: Candidate | None = None) -> dict:
    return {
        'video_id': code, 'url': reel_url(code), 'platform': 'instagram',
        'title': title_of(meta.get('caption'), code), 'caption': meta.get('caption') or '',
        'channel_name': name, 'username': username,
        'published_at': meta.get('taken_at') or (cand.taken_at if cand else None),
        'duration_s': meta.get('duration_s') or (cand.duration_s if cand else None),
        'views': cand.views if cand else None, 'pinned': bool(cand and cand.pinned),
        'discovered_at': iso(now), 'origin': origin, 'priority': priority, 'attempts': 0, 'not_before': None,
        'source': name,
    }


def _reason(meta: dict, source: ReelSource, max_age_days: int, now: datetime, pinned: bool) -> str | None:
    taken = parse_ts(meta.get('taken_at'))
    if taken and now - taken > timedelta(days=max_age_days):
        return 'pinned_old' if pinned else 'too_old'
    duration = meta.get('duration_s')
    if duration and duration < source.min_duration_s:
        return 'too_short'
    if duration and source.max_duration_s and duration > source.max_duration_s:
        return 'too_long'
    return None


def cooldown(state: dict, now: datetime) -> dict | None:
    """The active cooldown ({until, reason}) after Instagram pushed back, or None."""
    entry = state.get('ig') or {}
    until = parse_ts(entry.get('cooldown_until'))
    return {'until': entry['cooldown_until'], 'reason': entry.get('reason', '')} if until and until > now else None


def start_cooldown(state: dict, now: datetime, reason: str) -> str:
    until = iso(now + timedelta(hours=COOLDOWN_HOURS))
    state['ig'] = {'cooldown_until': until, 'reason': reason[:300], 'since': iso(now)}
    return until


def poll_reels(store: ReelStore, sources: list[ReelSource], web, now: datetime, *, days: int | None = None,
               only: str | None = None, dry_run: bool = False, max_scrolls: int | None = None,
               sleep=time.sleep) -> PollReport:
    """`days` overrides every creator's age limit for this run (the trial backfill) and reconsiders reels that an
    earlier poll skipped only for being too old. Any sign that Instagram is pushing back stops the poll and starts
    a cooldown; until it ends no poll opens the browser."""
    report = PollReport()
    state = store.load_state()
    active = cooldown(state, now)
    if active:
        report.warnings.append(f'Instagram cooldown until {active["until"]} ({active["reason"]}); '
                               'nothing polled. `reels session` shows it; `reels session --clear-cooldown` ends it')
        return report
    known = store.known_ids()
    if days is not None:
        known -= {code for code, why in store.skipped_reasons().items() if why in ('too_old', 'pinned_old')}

    for source in sources:
        if not source.enabled or (only and only.lower().lstrip('@') not in (source.username, source.name.lower())):
            continue
        ch = state['channels'].setdefault(f'ig:{source.username}', {})
        ch.update(ref=source.username, name=source.name)
        max_age = days if days is not None else source.max_age_days
        try:
            profile = web.profile(source.username, since=now - timedelta(days=max_age), max_scrolls=max_scrolls)
        except IgError as exc:
            report.errors.append(f'{source.name}: {exc}')
            if isinstance(exc, Blocked):
                until = start_cooldown(state, now, str(exc))
                report.warnings.append(f'Instagram pushed back; stopped and cooling down until {until}. Open the '
                                       'account on your phone and clear any prompt before the cooldown ends.')
                if not dry_run:
                    store.save_state(state)
                break
            ch['fail_count'] = ch.get('fail_count', 0) + 1
            ch['last_error'] = str(exc)
            if ch['fail_count'] >= FAIL_FLAG_AFTER:
                report.warnings.append(f'{source.name}: {ch["fail_count"]} failing polls in a row')
            if not dry_run:
                store.save_state(state)
            if isinstance(exc, LoginWall):
                report.warnings.append('Instagram is asking for a login; stopped polling for this run')
                break
            continue

        report.polled += 1
        ch['fail_count'] = 0
        ch.pop('last_error', None)
        ch['last_polled'] = iso(now)
        ch['last_seen'] = len(profile.candidates)
        ch['last_scrolls'] = profile.scrolls
        if not profile.candidates:
            report.warnings.append(f'{source.name}: the profile showed no reels')
        old_in_a_row = 0
        blocked = False
        for cand in profile.candidates:
            if cand.code in known:
                continue

            def outcome(result: str, detail: str, title: str = '') -> None:
                report.outcomes.append(Outcome(cand.code, title or f'reel {cand.code}', source.name, result, detail))

            def skip(reason: str, title: str = '') -> None:
                if not dry_run:
                    store.record_skip(cand.code, reason, now, title or None)
                known.add(cand.code)
                outcome('skipped', reason, title)

            if old_in_a_row >= OLD_IN_A_ROW and not cand.pinned:
                skip('too_old')          # newer reels come first, so this one is older still
                continue
            if cand.taken_at and cand.caption is not None:
                meta = page_meta(cand)   # the logged-in page already had everything: no lookup
            elif blocked:
                continue
            else:
                meta = None
            try:
                if meta is None:
                    sleep(random.uniform(*META_GAP_S))
                    meta = web.reel_meta(cand.code)
            except Unavailable:
                skip('unavailable')
                continue
            except LoginWall as exc:
                report.errors.append(f'{source.name} {cand.code}: {exc}')
                blocked = True           # every later lookup would hit the same wall
                continue
            except IgError as exc:
                outcome('error', str(exc))   # not recorded: retried next poll
                continue
            title = title_of(meta.get('caption'), cand.code)
            reason = _reason(meta, source, max_age, now, cand.pinned)
            if reason:
                if reason == 'too_old':
                    old_in_a_row += 1
                skip(reason, title)
                continue
            old_in_a_row = 0
            if not dry_run:
                store.add_pending(reel_item(cand.code, meta, name=source.name, username=source.username,
                                            priority=source.priority, origin='ig', now=now, cand=cand))
            known.add(cand.code)
            outcome('queued', f'{(meta.get("taken_at") or "")[:10]} priority {source.priority}', title)
        if not dry_run:
            store.save_state(state)
    return report


def add_reel(store: ReelStore, web, url: str, now: datetime, sources: list[ReelSource], *, now_flag: bool = False,
             force: bool = False) -> tuple[str, str, str | None]:
    """Manual add of one reel link. Returns (status, message, code) like inbox.add_manual."""
    code = extract_reel_code(url)
    if not code:
        return 'rejected', 'not an Instagram reel URL', None
    found = store.find(code)
    if found and found[0] == 'processing':
        return 'in-progress', 'already being processed', code
    if found and found[0] == 'pending':
        return 'exists', 'already queued', code
    if code in store.noted_ids() and not force:
        return 'exists', 'already summarized (use --force to redo)', code
    try:
        meta = web.reel_meta(code)
    except Unavailable as exc:
        return 'rejected', f'reel is unavailable: {exc}', code
    except IgError as exc:
        return 'rejected', f'lookup failed: {exc}', code
    username = meta.get('username') or 'unknown'
    vetted = {s.username: s for s in sources}
    name = vetted[username].name if username in vetted else (meta.get('creator_name') or username)
    if found:
        store.remove(found[0], code)
    store.add_pending(reel_item(code, meta, name=name, username=username, origin='manual', now=now,
                                priority=NOW_PRIORITY if now_flag else MANUAL_PRIORITY))
    return 'queued', f'{name} {(meta.get("taken_at") or "")[:10]}', code


def consume_reel_inbox(store: ReelStore, web, now: datetime, sources: list[ReelSource]) -> list[tuple[str, str, str | None]]:
    """<reels>/inbox/*.txt: one reel link per line (# comments); each file is archived after reading."""
    results = []
    for path in sorted(store.inbox.glob('*.txt')):
        if path.name == 'rejected.txt':
            continue
        try:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        except (OSError, UnicodeError):
            results.append(('rejected', f'cannot read {path.name}', None))
            continue
        for line in (l.strip() for l in lines):
            if line and not line.startswith('#'):
                results.append(add_reel(store, web, line, now, sources))
        archive = store.inbox / 'done' / f'{path.stem}-{now.strftime("%Y%m%dT%H%M%SZ")}.txt'
        archive.parent.mkdir(parents=True, exist_ok=True)
        path.replace(archive)
    return results
