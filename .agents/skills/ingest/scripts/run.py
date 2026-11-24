#!/usr/bin/env python3
"""Ingest CLI: discover videos, queue them, turn them into notes.

  run.py init                         create folders and a starter sources.toml
  run.py poll [--source X] [--backfill N] [--max-age-days D] [--dry-run]
  run.py process [--limit N] [--budget-min M] [--only ID] [--dry-run]   watch + write notes for queued videos
  run.py tick [same flags]            one scheduled run: poll, then process, then the morning brief
  run.py brief [--date D] [--dry-run]   (re)write a day's morning brief
  run.py analyze [--video ID ...] [--sample N] [--missing] [--render-only]   analysis-method extraction
  run.py add URL... [--now] [--priority N] [--force]
  run.py next [--limit N] [--json]    claim the best pending items
  run.py recover                      release stale claims
  run.py status [--json]
  run.py list [--skipped] [--json]    full queue; also kept in <state>/QUEUE.md after every change
  run.py source list | add REF [--name N] [--priority P]
  run.py reels ...                    Instagram reels pipeline (run.py reels -h)
Global: --home DIR overrides INGEST_HOME.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dataclasses

from config import DEFAULT_RUN_BUDGET_MIN, STARTER_SOURCES, ConfigError, load_sources, resolve_paths  # noqa: E402
from inbox import add_manual, consume_inbox  # noqa: E402
from poll import poll  # noqa: E402
import analysis  # noqa: E402
from brief import build_brief_prompt, day_batch, history_notes, write_brief  # noqa: E402
from brief import prompt_template as brief_template  # noqa: E402
from process import build_prompt, process_queue, prompt_template  # noqa: E402
from reels_cli import add_reels_parser, cmd_reels  # noqa: E402
from store import LockHeld, Store, iso, utcnow  # noqa: E402
from ytnet import Net  # noqa: E402


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure:
            try:
                reconfigure(encoding='utf-8', errors='backslashreplace')
            except (OSError, ValueError):
                pass


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog='run.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--home', help='ingest home folder (overrides INGEST_HOME)')
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    p = sub.add_parser('poll')
    p.add_argument('--source')
    p.add_argument('--backfill', type=int, metavar='N')
    p.add_argument('--max-age-days', type=int, metavar='D', help='override the age limit for this run only')
    p.add_argument('--dry-run', action='store_true')
    for name in ('process', 'tick'):
        pr = sub.add_parser(name)
        pr.add_argument('--limit', type=int, metavar='N', help='stop after N videos')
        pr.add_argument('--budget-min', type=int, default=DEFAULT_RUN_BUDGET_MIN, metavar='M')
        pr.add_argument('--only', metavar='VIDEO_ID', help='process just this queued video')
        pr.add_argument('--dry-run', action='store_true', help='print the prompt for the next video; call nothing')
        pr.add_argument('--log', action='store_true', help='write output to <logs>/<date>/run.log (for scheduled runs)')
    b = sub.add_parser('brief', help="(re)write a day's morning brief from the videos finished that day")
    b.add_argument('--date', metavar='YYYY-MM-DD', help='local run day (default: today)')
    b.add_argument('--dry-run', action='store_true', help='print the prompt; call nothing')
    b.add_argument('--log', action='store_true', help='write output to <logs>/<date>/run.log')
    an = sub.add_parser('analyze', help='extract how creators analyse (methods, sites, indicators) from finished videos')
    an.add_argument('--video', action='append', metavar='ID', help='analyse this finished video (repeatable)')
    an.add_argument('--sample', type=int, metavar='N', help='analyse N unanalysed videos, spread across channels')
    an.add_argument('--missing', action='store_true', help='analyse every finished video that has no analysis yet')
    an.add_argument('--render-only', action='store_true', help='rebuild the markdown views from the stored data; no model')
    an.add_argument('--log', action='store_true', help='write output to <logs>/<date>/run.log')
    a = sub.add_parser('add')
    a.add_argument('urls', nargs='+')
    a.add_argument('--now', action='store_true')
    a.add_argument('--priority', type=int)
    a.add_argument('--force', action='store_true')
    n = sub.add_parser('next')
    n.add_argument('--limit', type=int)
    n.add_argument('--json', action='store_true')
    rq = sub.add_parser('requeue', help='send done or failed videos back to pending to be processed again')
    rq.add_argument('ids', nargs='+')
    sub.add_parser('recover')
    ls = sub.add_parser('list')
    ls.add_argument('--skipped', action='store_true')
    ls.add_argument('--json', action='store_true')
    s = sub.add_parser('status')
    s.add_argument('--json', action='store_true')
    src = sub.add_parser('source')
    ssub = src.add_subparsers(dest='source_command', required=True)
    ssub.add_parser('list')
    sa = ssub.add_parser('add')
    sa.add_argument('ref')
    sa.add_argument('--name')
    sa.add_argument('--priority', type=int)
    add_reels_parser(sub)
    return ap


def cmd_init(paths, store) -> int:
    store.ensure()
    if not paths.sources_file.exists():
        paths.sources_file.parent.mkdir(parents=True, exist_ok=True)
        paths.sources_file.write_text(STARTER_SOURCES, encoding='utf-8')
        print(f'created {paths.sources_file}')
    print(f'home      {paths.home}\nstate     {paths.state}\nnotes     {paths.notes}\nraw       {paths.raw}\n'
          f'logs      {paths.logs}\nsources   {paths.sources_file}')
    return 0


def cmd_poll(paths, store, args, locked: bool = False) -> int:
    now = utcnow()
    store.ensure()
    _, sources = load_sources(paths.sources_file)
    if args.max_age_days is not None:
        sources = [dataclasses.replace(s, max_age_days=args.max_age_days) for s in sources]
    net = Net()
    if not locked:
        try:
            store.acquire_lock(now)
        except LockHeld as exc:
            print(f'skipped: {exc}')
            return 3
    try:
        released = store.recover_stale(now) if not args.dry_run else []
        if released:
            print(f'released {len(released)} stale claim(s): {", ".join(released)}')
        for status, message, vid in consume_inbox(store, net, now, args.dry_run):
            print(f'inbox  {status:10} {vid or "-":12} {message}')
        if not sources:
            print(f'no channels configured in {paths.sources_file}; add one with: run.py source add @handle')
        report = poll(store, sources, net, now, backfill=args.backfill, only=args.source, dry_run=args.dry_run)
    finally:
        if not args.dry_run:
            store.write_queue_md(utcnow())
        if not locked:
            store.release_lock()
    for o in report.outcomes:
        print(f'{o.result:9} {o.video_id}  {o.channel[:24]:24}  {o.title[:60]}  [{o.detail}]')
    for message in report.errors:
        print(f'error: {message}')
    for message in report.warnings:
        print(f'warning: {message}')
    label = ' (dry run, nothing written)' if args.dry_run else ''
    print(f'polled {report.polled} channel(s) ({report.not_modified} unchanged): {report.count("queued")} queued, '
          f'{report.count("deferred")} deferred, {report.count("skipped")} skipped, {len(report.errors)} error(s){label}')
    return 0


def run_process(paths, store, args) -> int:
    """Claim and process queue items. The caller holds the lock."""
    if args.dry_run:
        item = (store.pending_items(utcnow()) or [None])[0]
        if item is None:
            print('nothing pending')
            return 0
        print(build_prompt(prompt_template(paths), item, paths))
        return 0
    store.recover_stale(utcnow())
    report = process_queue(store, limit=args.limit, budget_min=args.budget_min, only=args.only)
    for vid in report.done:
        print(f'done      {vid}')
    for vid, error in report.retried:
        print(f'retry     {vid}  {error}')
    for vid, error in report.failed:
        print(f'FAILED    {vid}  {error}')
    if report.done:
        try:
            result = write_brief(store, today())
            if result is not None:
                print(f'brief     {result.path}  ({result.generated})')
        except Exception as exc:                 # a failed brief must not fail the run that made the notes
            print(f'brief failed: {type(exc).__name__}: {exc}')
    if report.done and paths.analysis:
        run_analysis_for(store, report.done)
    if report.stopped:
        print(f'stopped: {report.stopped}')
    print(f'processed: {len(report.done)} done, {len(report.retried)} will retry, {len(report.failed)} failed')
    return 1 if report.failed or report.setup_problem else 0


def run_analysis_for(store, ids) -> list:
    """Analyse freshly finished videos. A failure here must not fail the run that made the notes."""
    try:
        results = analysis.analyse_many(store, list(ids), on_result=print_analysis)
    except Exception as exc:
        print(f'analysis failed: {type(exc).__name__}: {exc}')
        return []
    return results


def print_analysis(res) -> None:
    if res.ok:
        print(f'analysis  {res.video_id}  {res.methods} method(s)  {res.seconds:.0f}s')
    elif res.skipped:
        print(f'analysis  {res.video_id}  skipped: {res.skipped}')
    else:
        print(f'analysis  {res.video_id}  FAILED (will be retried by `analyze --missing`): {"; ".join(res.problems)[:300]}')


def cmd_analyze(paths, store, args) -> int:
    def body() -> int:
        lay = analysis.layout(paths)
        if args.render_only:
            written = analysis.render(lay, paths.notes)
            print(f'rendered {len(written)} file(s) in {lay.root}')
            return 0
        ids = list(args.video or [])
        if args.sample:
            ids += [v for v in analysis.pick_sample(store, args.sample) if v not in ids]
        if args.missing:
            ids += [v for v in analysis.pending_ids(store) if v not in ids]
        if not ids:
            print('nothing to analyse (use --video, --sample N or --missing)')
            return 0
        results = analysis.analyse_many(store, ids, on_result=print_analysis)
        written = analysis.render(lay, paths.notes)
        print(f'analysed {sum(r.ok for r in results)} of {len(results)} video(s); rendered {len(written)} file(s) in {lay.root}')
        return 1 if any(not r.ok and not r.skipped for r in results) else 0
    return logged(paths, args, lambda: with_lock(store, body))


def with_lock(store, fn) -> int:
    now = utcnow()
    store.ensure()
    try:
        store.acquire_lock(now)
    except LockHeld as exc:
        print(f'skipped: {exc}')
        return 3
    try:
        return fn()
    finally:
        store.write_queue_md(utcnow())
        store.release_lock()


def logged(paths, args, fn) -> int:
    """With --log, send everything this run prints to <logs>/<date>/run.log (a scheduled task has no console)."""
    if not getattr(args, 'log', False):
        return fn()
    started = utcnow()
    target = paths.logs / started.strftime('%Y-%m-%d') / 'run.log'
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a', encoding='utf-8', errors='backslashreplace') as handle:
        handle.write(f'\n=== {started.strftime("%Y-%m-%d %H:%M:%SZ")} {args.command} ===\n')
        handle.flush()
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                code = fn()
            except Exception:
                traceback.print_exc()
                code = 1
            print(f'exit {code}')
    return code


def cmd_process(paths, store, args) -> int:
    return logged(paths, args, lambda: with_lock(store, lambda: run_process(paths, store, args)))


def today() -> date:
    """The brief's day is the reader's local date, not UTC."""
    return datetime.now().astimezone().date()


def cmd_brief(paths, store, args) -> int:
    def body() -> int:
        try:
            day = date.fromisoformat(args.date) if args.date else today()
        except ValueError:
            print(f'error: --date must be YYYY-MM-DD, got {args.date!r}')
            return 2
        if args.dry_run:
            batch = day_batch(store, day)
            if not batch:
                print(f'no videos finished on {day}')
                return 0
            print(build_brief_prompt(brief_template(paths), day, batch, history_notes(store, batch)))
            return 0
        result = write_brief(store, day)
        if result is None:
            print(f'no videos finished on {day}')
            return 0
        print(f'brief     {result.path}  ({result.generated}, {result.attempts} attempt(s))')
        for problem in result.problems:
            print(f'  problem: {problem}')
        return 1 if result.generated == 'fallback' else 0
    return logged(paths, args, body)


def cmd_tick(paths, store, args) -> int:
    """One scheduled run: poll the channels, then process whatever is queued."""
    def body() -> int:
        poll_args = argparse.Namespace(source=None, backfill=None, max_age_days=None, dry_run=args.dry_run)
        code = cmd_poll(paths, store, poll_args, locked=True)
        return max(code, run_process(paths, store, args))
    return logged(paths, args, lambda: with_lock(store, body))


def cmd_add(store, args) -> int:
    store.ensure()
    net, now = Net(), utcnow()
    code = 0
    for url in args.urls:
        status, message, vid = add_manual(store, net, url, now, now_flag=args.now, priority=args.priority, force=args.force)
        print(f'{status:11} {vid or "-":12} {message}')
        if status == 'rejected':
            code = 1
    store.write_queue_md(utcnow())
    return code


def cmd_requeue(store, args) -> int:
    code = 0
    for vid in args.ids:
        found = store.find(vid)
        if found is None or found[0] not in ('done', 'failed'):
            print(f'{vid}: not in done or failed' + (f' (it is in {found[0]})' if found else ''))
            code = 1
            continue
        stage, item = found
        if stage == 'done':       # a manifest is not a queue item; rebuild one from it
            item = {'video_id': vid, 'url': item.get('url'), 'title': item.get('title'), 'channel_name': item.get('channel'),
                    'published_at': item.get('published_at'), 'origin': 'manual', 'priority': 100,
                    'discovered_at': iso(utcnow())}
        for key in ('attempts', 'last_error', 'last_attempt_at', 'not_before', 'claimed_at'):
            item.pop(key, None)
        item['attempts'] = 0
        store.add_pending(item)
        store.remove(stage, vid)
        print(f'{vid}: back to pending (was {stage})')
    store.write_queue_md(utcnow())
    return code


def cmd_next(store, args) -> int:
    now = utcnow()
    store.ensure()
    store.recover_stale(now)
    claimed = store.claim_next(args.limit, now)
    store.write_queue_md(now)
    if args.json:
        print(json.dumps(claimed, indent=2, ensure_ascii=False))
    else:
        for item in claimed:
            print(f'{item["video_id"]}  p{item["priority"]:<5} {item["origin"]:6} {item.get("channel_name") or "-"}: {item.get("title")}')
        if not claimed:
            print('nothing pending')
    return 0


def cmd_status(store, paths, args) -> int:
    now = utcnow()
    counts = store.counts()
    nxt = store.pending_items(now)[:5]
    state = store.load_state()
    failing = {v.get('name') or k: v['fail_count'] for k, v in state['channels'].items() if v.get('fail_count')}
    if args.json:
        print(json.dumps({'counts': counts, 'next': nxt, 'failing_channels': failing}, indent=2, ensure_ascii=False))
        return 0
    print('  '.join(f'{k}={v}' for k, v in counts.items()))
    for item in nxt:
        print(f'  next  {item["video_id"]}  p{item["priority"]:<5} {item["origin"]:6} {item.get("channel_name") or "-"}: {item.get("title")}')
    for name, count in failing.items():
        print(f'  failing channel: {name} ({count} in a row)')
    return 0


def cmd_list(store, args) -> int:
    now = utcnow()
    if args.skipped:
        rows = store.recent_skips(500)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        for r in rows if not args.json else []:
            print(f'{r["date"][:10]}  {r["video_id"]}  {r["reason"]:12} {r.get("title") or ""}')
        return 0
    items = store.pending_items(now, include_deferred=True)
    if args.json:
        print(json.dumps(items, indent=2, ensure_ascii=False))
        return 0
    for n, item in enumerate(items, 1):
        minutes = f'{round(item["duration_s"] / 60)}m' if item.get('duration_s') else '?'
        print(f'{n:>3}  p{store.effective_priority(item, now):<5} {item.get("origin", ""):6} {item.get("published_at", "")[:10]}  '
              f'{minutes:>4}  {(item.get("channel_name") or "-")[:18]:18} {item.get("title")}')
    if not items:
        print('nothing pending')
    return 0


def cmd_source(paths, args) -> int:
    defaults, sources = load_sources(paths.sources_file)
    if args.source_command == 'list':
        for s in sources:
            print(f'{"on " if s.enabled else "off"} p{s.priority:<3} {s.name}  ({s.ref})')
        if not sources:
            print('no channels configured')
        return 0
    if args.ref.lower() in {s.ref.lower() for s in sources}:
        print(f'{args.ref} is already listed')
        return 1
    ref = args.ref.strip()
    key = 'channel_id' if ref.startswith('UC') and len(ref) == 24 else ('url' if '://' in ref else 'handle')
    if key == 'handle' and not ref.startswith('@'):
        ref = '@' + ref
    block = f'\n[[source]]\n{key} = {json.dumps(ref)}\nname = {json.dumps(args.name or ref)}\n'
    if args.priority is not None:
        block += f'priority = {args.priority}\n'
    paths.sources_file.parent.mkdir(parents=True, exist_ok=True)
    existing = paths.sources_file.read_text(encoding='utf-8') if paths.sources_file.exists() else STARTER_SOURCES
    paths.sources_file.write_text(existing.rstrip('\n') + '\n' + block, encoding='utf-8')
    print(f'added {ref} to {paths.sources_file}')
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = build_parser().parse_args(argv)
    try:
        paths = resolve_paths(args.home)
        store = Store(paths)
        if args.command == 'init':
            return cmd_init(paths, store)
        if args.command == 'poll':
            return cmd_poll(paths, store, args)
        if args.command == 'process':
            return cmd_process(paths, store, args)
        if args.command == 'tick':
            return cmd_tick(paths, store, args)
        if args.command == 'brief':
            return cmd_brief(paths, store, args)
        if args.command == 'analyze':
            return cmd_analyze(paths, store, args)
        if args.command == 'add':
            return cmd_add(store, args)
        if args.command == 'next':
            return cmd_next(store, args)
        if args.command == 'requeue':
            return cmd_requeue(store, args)
        if args.command == 'recover':
            released = store.recover_stale(utcnow())
            print(f'released {len(released)}: {", ".join(released)}' if released else 'nothing stale')
            return 0
        if args.command == 'status':
            return cmd_status(store, paths, args)
        if args.command == 'list':
            return cmd_list(store, args)
        if args.command == 'reels':
            return cmd_reels(paths, args, with_lock, logged)
        return cmd_source(paths, args)
    except ConfigError as exc:
        print(f'config error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
