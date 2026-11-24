#!/usr/bin/env python3
"""`run.py reels ...`: the Instagram reels pipeline. Separate queue, separate lock, separate brief.

  reels init                                  create <home>/reels/ and a starter reel-sources.toml
  reels login                                 log the burner account in by hand (visible browser); saves the session
  reels session [--clear-cooldown] [--forget] login, cooldown and per-creator poll state
  reels source list | add USER [--name N] [--priority P]
  reels poll [--user U] [--days D] [--dry-run]   headless browser on the vetted creators -> pending
  reels add URL... [--now] [--force]          queue reel links by hand (also <home>/reels/inbox/*.txt)
  reels fetch [--limit N]                     download audio + Gemini transcript
  reels summarize [--limit N] [--batch-size B] [--open-types] [--redo --since 30d] [--dry-run]
  reels process [--limit N] [--budget-min M]  fetch, then summarize
  reels tick                                  poll + process + reels brief (for the scheduler)
  reels brief [--date YYYY-MM-DD] [--dry-run]
  reels trial [--days 30] [--user U]          backfill poll + fetch (step A of the trial)
  reels trial-report [--since 30d] [--out F]  type / creator / cost tables -> plan/reels/TRIAL.md
  reels render                                rebuild every month file from reels.jsonl
  reels status | list [--skipped] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from config import STARTER_REEL_SOURCES, clean_username, load_reel_sources
from ig_poll import add_reel, consume_reel_inbox, cooldown, poll_reels
from igweb import IgError, IgWeb, read_session
from igweb import login as ig_login
from reel_brief import build_prompt as brief_prompt, brief_rules, day_entries, prompt_template as brief_template
from reel_brief import write_reel_brief
from reels import (build_prompt, fetch_queue, load_types, make_batches, prompt_template, redo, render_months,
                   since_arg, summarize_queue, trial_report, waiting_for)
from reelstore import ReelStore
from store import iso, utcnow

DEFAULT_TRIAL_DAYS = 30
TRIAL_SCROLLS = 25


def add_reels_parser(sub) -> None:
    r = sub.add_parser('reels', help='Instagram reels: poll vetted creators, transcribe, batch summaries, brief',
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    rs = r.add_subparsers(dest='reels_command', required=True)
    rs.add_parser('init')
    src = rs.add_parser('source')
    ssub = src.add_subparsers(dest='source_command', required=True)
    ssub.add_parser('list')
    sa = ssub.add_parser('add')
    sa.add_argument('username', help='@user, user, or the profile URL')
    sa.add_argument('--name')
    sa.add_argument('--priority', type=int)

    def browser_flags(p):
        p.add_argument('--headful', action='store_true', help='show the browser window (debugging)')

    rs.add_parser('login', help='log the burner account in by hand in a visible browser; saves the session')
    se = rs.add_parser('session', help='show the saved login, the cooldown and per-creator poll state')
    se.add_argument('--clear-cooldown', action='store_true', help='end a cooldown early (only after checking the account)')
    se.add_argument('--forget', action='store_true', help='stop using the saved login')

    def scroll_flag(p, default_help):
        p.add_argument('--max-scrolls', type=int, metavar='N', help=f'logged in: scrolls per creator at most ({default_help})')

    p = rs.add_parser('poll')
    p.add_argument('--user', help='poll just this creator')
    p.add_argument('--days', type=int, metavar='D', help='age limit for this run (overrides max_age_days)')
    p.add_argument('--dry-run', action='store_true')
    browser_flags(p)
    scroll_flag(p, 'default 4')
    a = rs.add_parser('add')
    a.add_argument('urls', nargs='+')
    a.add_argument('--now', action='store_true')
    a.add_argument('--force', action='store_true')
    f = rs.add_parser('fetch')
    f.add_argument('--limit', type=int, metavar='N')
    f.add_argument('--no-rules', action='store_true', help='download every reel, even short ones with empty captions')
    s = rs.add_parser('summarize')
    s.add_argument('--limit', type=int, metavar='N', help='at most N reels')
    s.add_argument('--batch-size', type=int, metavar='B', help='reels per call (default INGEST_REEL_BATCH or 15)')
    s.add_argument('--open-types', action='store_true', help='let the model name the types (trial step B)')
    s.add_argument('--redo', action='store_true', help='re-summarize reels already done, from cached transcripts')
    s.add_argument('--since', default=f'{DEFAULT_TRIAL_DAYS}d', help='with --redo: 30d or YYYY-MM-DD (default 30d)')
    s.add_argument('--dry-run', action='store_true', help='print the first batch prompt; call nothing')
    s.add_argument('--no-rules', action='store_true', help='send every reel to the model, even near-silent filler')
    for name in ('process', 'tick'):
        pr = rs.add_parser(name)
        pr.add_argument('--limit', type=int, metavar='N')
        pr.add_argument('--budget-min', type=float, default=120, metavar='M', help='time budget for fetching')
        pr.add_argument('--log', action='store_true', help='write output to <logs>/<date>/run.log')
        if name == 'tick':
            browser_flags(pr)
    b = rs.add_parser('brief')
    b.add_argument('--date', metavar='YYYY-MM-DD')
    b.add_argument('--dry-run', action='store_true')
    b.add_argument('--log', action='store_true')
    t = rs.add_parser('trial')
    t.add_argument('--days', type=int, default=DEFAULT_TRIAL_DAYS)
    t.add_argument('--user')
    t.add_argument('--no-fetch', action='store_true', help='only poll; fetch later with `reels fetch`')
    browser_flags(t)
    scroll_flag(t, f'default {TRIAL_SCROLLS}; it stops earlier once it reaches --days back')
    tr = rs.add_parser('trial-report')
    tr.add_argument('--since', help='30d or YYYY-MM-DD (default: everything)')
    tr.add_argument('--out', default='plan/reels/TRIAL.md')
    rs.add_parser('render')
    st = rs.add_parser('status')
    st.add_argument('--json', action='store_true')
    ls = rs.add_parser('list')
    ls.add_argument('--skipped', action='store_true')
    ls.add_argument('--json', action='store_true')


def _web(args, paths) -> IgWeb:
    """Logged in when a burner login has been saved (and INGEST_IG_LOGIN is not off), otherwise logged out."""
    headful = getattr(args, 'headful', False) or os.environ.get('INGEST_IG_HEADFUL', '').lower() in ('1', 'true', 'yes')
    profile = paths.ig_profile_dir if paths.ig_login and read_session(paths.ig_profile_dir) else None
    return IgWeb(headless=not headful, profile_dir=profile)


def do_login(paths) -> int:
    try:
        session = ig_login(paths.ig_profile_dir)
    except IgError as exc:
        print(f'login not saved: {exc}')
        return 1
    print(f'login saved in {paths.ig_profile_dir} (account id {session.get("account_id") or "?"}).\n'
          'Polls now run logged in. Check it with: run.py reels poll --user <one creator> --dry-run')
    return 0


def do_session(store: ReelStore, paths, args) -> int:
    session = read_session(paths.ig_profile_dir)
    state = store.load_state()
    if args.clear_cooldown and state.pop('ig', None) is not None:
        store.save_state(state)
        print('cooldown cleared')
    if args.forget:
        target = paths.ig_profile_dir / 'ig-session.json'
        target.unlink(missing_ok=True)
        print(f'polls will run logged out again (removed {target}; the browser profile itself is kept, delete '
              f'{paths.ig_profile_dir} to remove the login completely)')
        session = None
    mode = 'off (INGEST_IG_LOGIN=0)' if not paths.ig_login else ('saved' if session else 'none saved')
    print(f'login     {mode}' + (f', account id {session.get("account_id")}, saved {session.get("saved_at")}'
                                 if session else ''))
    print(f'profile   {paths.ig_profile_dir}')
    active = cooldown(state, utcnow())
    print(f'cooldown  {"until " + active["until"] + " (" + active["reason"] + ")" if active else "none"}')
    for key, ch in sorted(state['channels'].items()):
        if key.startswith('ig:'):
            print(f'  @{ch.get("ref")}: last poll {ch.get("last_polled", "never")}, {ch.get("last_seen", 0)} reels seen, '
                  f'{ch.get("last_scrolls", 0)} scroll(s)' + (f', failing x{ch["fail_count"]}' if ch.get('fail_count') else ''))
    return 0


def _today() -> date:
    return datetime.now().astimezone().date()


# ---- steps ------------------------------------------------------------------------
def do_poll(store: ReelStore, paths, args, days=None, user=None, dry_run=False, max_scrolls=None) -> int:
    sources = load_reel_sources(paths.reel_sources_file)
    now = utcnow()
    store.ensure()
    with _web(args, paths) as web:
        web.debug_dir = paths.logs / now.strftime('%Y-%m-%d') / 'ig-pages'
        print(f'browsing {"logged in (burner)" if web.logged_in else "logged out (latest 12 reels per creator)"}')
        if not dry_run:
            for status, message, code in consume_reel_inbox(store, web, now, sources):
                print(f'inbox  {status:10} {code or "-":12} {message}')
        if not sources:
            print(f'no creators in {paths.reel_sources_file}; add one with: run.py reels source add <username>')
            return 0
        report = poll_reels(store, sources, web, now, days=days, only=user, dry_run=dry_run, max_scrolls=max_scrolls)
    for o in report.outcomes:
        print(f'{o.result:9} {o.video_id:12} {o.channel[:20]:20} {o.title[:60]}  [{o.detail}]')
    for message in report.errors:
        print(f'error: {message}')
    for message in report.warnings:
        print(f'warning: {message}')
    label = ' (dry run, nothing written)' if dry_run else ''
    print(f'polled {report.polled} creator(s): {report.count("queued")} queued, {report.count("skipped")} skipped, '
          f'{report.count("error")} lookup error(s), {len(report.errors)} error(s){label}')
    return 1 if report.errors and not report.polled else 0


def do_fetch(store: ReelStore, limit=None, budget_min=None, rules=True) -> int:
    report = fetch_queue(store, limit=limit, budget_min=budget_min, rules=rules)
    for code in report.done:
        print(f'transcribed {code}')
    for code, why in report.filtered:
        print(f'filler    {code}  {why}')
    for code, why in report.skipped:
        print(f'skipped   {code}  {why[:160]}')
    for code, why in report.retried:
        print(f'retry     {code}  {why[:160]}')
    for code, why in report.failed:
        print(f'FAILED    {code}  {why[:160]}')
    if report.stopped:
        print(f'stopped: {report.stopped}')
    print(f'fetched: {len(report.done)} transcribed, {len(report.filtered)} filler by rule (not downloaded), '
          f'{len(report.retried)} will retry, {len(report.failed)} failed')
    return 1 if report.failed or (report.stopped and not report.stopped.startswith(('reached', 'time'))) else 0


def _print_summary(report) -> None:
    for code, why in report.filtered:
        print(f'filler    {code}  {why}')
    for code, why in report.retried:
        print(f'retry     {code}  {why[:160]}')
    for code, why in report.failed:
        print(f'FAILED    {code}  {why[:160]}')
    cost = report.usage.get('cost_usd')
    per = f', ${cost / len(report.done):.4f} per reel' if cost and report.done else ''
    print(f'summarized: {len(report.done)} done in {report.batches} batch(es), {report.calls} call(s), '
          f'{len(report.filtered)} filler by rule (no model call), {len(report.retried)} will retry, '
          f'{len(report.failed)} failed' + (f'; ${cost:.4f}{per}' if isinstance(cost, (int, float)) else ''))


def do_summarize(store: ReelStore, args) -> int:
    open_types = getattr(args, 'open_types', False)
    size = getattr(args, 'batch_size', None)
    if getattr(args, 'dry_run', False):
        items = waiting_for(store, utcnow(), transcribed=True)[:args.limit]
        pairs = [(i, store.load_transcript(i.get('username') or '', i['video_id'], i.get('published_at'))) for i in items]
        batches = make_batches(pairs, size or store.paths.reel_batch)
        if not batches:
            print('nothing transcribed and waiting')
            return 0
        print(build_prompt(prompt_template(store.paths), batches[0], None if open_types else load_types()))
        print(f'\n[{len(batches)} batch(es), {len(pairs)} reel(s) waiting; this is the first]')
        return 0
    if getattr(args, 'redo', False):
        report = redo(store, since_arg(args.since, utcnow()), size=size, open_types=open_types,
                      rules=not getattr(args, 'no_rules', False))
    else:
        report = summarize_queue(store, size=size, limit=getattr(args, 'limit', None), open_types=open_types,
                                 rules=not getattr(args, 'no_rules', False))
    _print_summary(report)
    return 1 if report.failed else 0


def do_brief(store: ReelStore, day: date, dry_run=False) -> int:
    if dry_run:
        entries = day_entries(store, day)
        skip, count_only = brief_rules(load_types())
        included = [e for e in entries if e.get('type') not in skip | count_only]
        if not included:
            print(f'no reels to brief on {day}')
            return 0
        print(brief_prompt(brief_template(store.paths), day, included, {}))
        return 0
    result = write_reel_brief(store, day)
    if result is None:
        print(f'no reels summarized on {day}')
        return 0
    print(f'brief     {result.path}  ({result.generated}, {result.included}/{result.reels} reels, '
          f'{result.attempts} attempt(s))')
    for problem in result.problems:
        print(f'  problem: {problem}')
    return 1 if result.generated == 'fallback' and result.included else 0


def do_status(store: ReelStore, paths, args) -> int:
    now = utcnow()
    counts = store.counts()
    counts.pop('done', None)
    counts['summarized'] = len(store.load_index())
    counts['to_fetch'] = len(waiting_for(store, now, transcribed=False))
    counts['to_summarize'] = len(waiting_for(store, now, transcribed=True))
    failing = {v.get('name') or k: v['fail_count'] for k, v in store.load_state()['channels'].items()
               if v.get('fail_count')}
    if args.json:
        print(json.dumps({'counts': counts, 'failing_creators': failing}, indent=2))
        return 0
    print('  '.join(f'{k}={v}' for k, v in counts.items()))
    for name, count in failing.items():
        print(f'  failing creator: {name} ({count} in a row)')
    return 0


def do_list(store: ReelStore, args) -> int:
    if args.skipped:
        rows = store.recent_skips(500)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return 0
        for r in rows:
            print(f'{r["date"][:10]}  {r["video_id"]:12} {r["reason"]:12} {r.get("title") or ""}')
        return 0
    items = store.pending_items(utcnow(), include_deferred=True)
    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0
    for n, i in enumerate(items, 1):
        step = 'summarize' if i.get('transcribed') else 'fetch'
        print(f'{n:>3}  {step:9} {(i.get("published_at") or "")[:10]}  {i["video_id"]:12} '
              f'{(i.get("channel_name") or "-")[:18]:18} {i.get("title")}')
    if not items:
        print('nothing pending')
    return 0


def do_source(paths, args) -> int:
    sources = load_reel_sources(paths.reel_sources_file)
    if args.source_command == 'list':
        for s in sources:
            print(f'{"on " if s.enabled else "off"} p{s.priority:<3} {s.name}  (@{s.username}, max age {s.max_age_days}d)')
        if not sources:
            print('no creators configured')
        return 0
    username = clean_username(args.username)
    if not username:
        print(f'{args.username!r} is not a valid Instagram username')
        return 1
    if username in {s.username for s in sources}:
        print(f'{username} is already listed')
        return 1
    block = f'\n[[creator]]\nusername = {json.dumps(username)}\nname = {json.dumps(args.name or username)}\n'
    if args.priority is not None:
        block += f'priority = {args.priority}\n'
    path = paths.reel_sources_file
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding='utf-8') if path.exists() else STARTER_REEL_SOURCES
    path.write_text(existing.rstrip('\n') + '\n' + block, encoding='utf-8')
    print(f'added {username} to {path}')
    return 0


# ---- dispatch -----------------------------------------------------------------------
def cmd_reels(paths, args, with_lock, logged) -> int:
    paths = paths.reels()
    store = ReelStore(paths)
    command = args.reels_command
    if command == 'init':
        store.ensure()
        if not paths.reel_sources_file.exists():
            paths.reel_sources_file.parent.mkdir(parents=True, exist_ok=True)
            paths.reel_sources_file.write_text(STARTER_REEL_SOURCES, encoding='utf-8')
            print(f'created {paths.reel_sources_file}')
        print(f'queue     {store.paths.state}\nreel notes {store.notes_dir}\ntranscripts {store.raw_dir}\n'
              f'sources   {paths.reel_sources_file}\nbriefs    {paths.briefs}')
        return 0
    if command == 'source':
        return do_source(paths, args)
    if command == 'login':
        return do_login(paths)
    if command == 'session':
        return do_session(store, paths, args)
    if command == 'status':
        return do_status(store, paths, args)
    if command == 'list':
        return do_list(store, args)
    if command == 'render':
        written = render_months(store)
        print(f'rendered {len(written)} month file(s) in {store.notes_dir}')
        return 0
    if command == 'trial-report':
        since = since_arg(args.since, utcnow()) if args.since else None
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(trial_report(store, since), encoding='utf-8')
        print(f'wrote {out}')
        return 0
    if command == 'brief':
        try:
            day = date.fromisoformat(args.date) if args.date else _today()
        except ValueError:
            print(f'error: --date must be YYYY-MM-DD, got {args.date!r}')
            return 2
        return logged(paths, args, lambda: do_brief(store, day, args.dry_run))
    if command == 'poll' and args.dry_run:
        return do_poll(store, paths, args, days=args.days, user=args.user, dry_run=True, max_scrolls=args.max_scrolls)
    if command == 'add':
        sources, now = load_reel_sources(paths.reel_sources_file), utcnow()

        def add() -> int:
            code_out = 0
            with _web(args, paths) as web:
                for url in args.urls:
                    status, message, code = add_reel(store, web, url, now, sources, now_flag=args.now, force=args.force)
                    print(f'{status:11} {code or "-":12} {message}')
                    code_out = 1 if status == 'rejected' else code_out
            return code_out
        return with_lock(store, add)
    if command == 'summarize' and args.dry_run:
        return do_summarize(store, args)

    def body() -> int:
        if command == 'poll':
            return do_poll(store, paths, args, days=args.days, user=args.user, max_scrolls=args.max_scrolls)
        if command == 'fetch':
            return do_fetch(store, limit=args.limit, rules=not args.no_rules)
        if command == 'summarize':
            return do_summarize(store, args)
        if command == 'trial':
            code = do_poll(store, paths, args, days=args.days, user=args.user,
                           max_scrolls=args.max_scrolls or TRIAL_SCROLLS)
            if not args.no_fetch:
                code = max(code, do_fetch(store))
            print('\nnext: `run.py reels summarize --open-types`, then `run.py reels trial-report`')
            return code
        # process / tick
        code = do_poll(store, paths, args) if command == 'tick' else 0
        code = max(code, do_fetch(store, limit=args.limit, budget_min=args.budget_min))
        summary = summarize_queue(store)
        _print_summary(summary)
        code = max(code, 1 if summary.failed else 0)
        if command == 'tick' and summary.done:
            try:
                code = max(code, do_brief(store, _today()))
            except Exception as exc:          # a failed brief must not fail the run that made the summaries
                print(f'brief failed: {type(exc).__name__}: {exc}')
        return code

    return logged(paths, args, lambda: with_lock(store, body))
