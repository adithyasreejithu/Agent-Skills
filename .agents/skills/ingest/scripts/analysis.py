#!/usr/bin/env python3
"""Analysis-method extraction: how creators analyse on screen, kept as a living master list.

For each finished video a second agent pass reads the transcript and frames and writes ONE observation
(`_data/observations/<id>.json`): which analysis methods the creator ran, step by step, on which sites or software,
looking at which indicators, and why. Python validates it, merges new methods/steps/tools into the registry, and
regenerates three readable views from the data (never hand-edited):

  <analysis>/methods.md          master list: one row per method, linking to its file
  <analysis>/methods/<id>.md     the step-by-step method, with every video that used it as evidence
  <analysis>/tools.md            tracker: websites/software and indicators

`_data/` is the source of truth, so re-running a video replaces its observation and nothing is ever duplicated.
The model is injectable, and a failed pass never fails the video.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from config import Paths
from note import find_note
from process import RunResult, claude_runner
from store import Store, read_json, write_json

PROMPT_NAME = 'analysis-prompt.md'
SKILL_DIR = Path(__file__).resolve().parent.parent
TAGS = ('explicit', 'visual', 'inference')
TOOL_KINDS = ('website', 'software', 'app', 'data-service', 'other')
DOMAINS = ('stocks', 'options')         # which kind of analysis a method is: stock/market/portfolio vs option contracts
DOMAIN_TITLES = {'stocks': 'Stock methods', 'options': 'Options methods'}
MAX_NAME_WORDS = 8
NOT_A_TOOL = re.compile(r'spoken|prepared (graphic|slide)|screenshot|image viewer|the creator|voice', re.I)
TIME_RE = re.compile(r'^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})')
Runner = Callable[[dict, str, Path], RunResult]


# ---- paths --------------------------------------------------------------------
@dataclass(frozen=True)
class Layout:
    root: Path

    @property
    def data(self) -> Path: return self.root / '_data'
    @property
    def inbox(self) -> Path: return self.data / 'inbox'
    @property
    def observations(self) -> Path: return self.data / 'observations'
    @property
    def registry(self) -> Path: return self.data / 'methods.json'
    @property
    def tools(self) -> Path: return self.data / 'tools.json'
    @property
    def methods_dir(self) -> Path: return self.root / 'methods'
    @property
    def master(self) -> Path: return self.root / 'methods.md'
    @property
    def tracker(self) -> Path: return self.root / 'tools.md'


def layout(paths: Paths) -> Layout:
    return Layout(paths.analysis_root())


# ---- small helpers ------------------------------------------------------------
def slug(text: str, limit: int = 48) -> str:
    """Lowercase-hyphen id, cut at a word boundary so file names never end mid-word."""
    full = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    if len(full) <= limit:
        return full
    cut = full[:limit]
    return cut.rsplit('-', 1)[0] if '-' in cut and full[limit] != '-' else cut.strip('-')


def tool_key(name: str) -> str:
    """'TradingView', 'tradingview' and 'Trading View' are one tool."""
    return re.sub(r'[^a-z0-9]+', '', (name or '').lower())


def seconds(at: str | None) -> int | None:
    m = TIME_RE.match((at or '').strip())
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def load_registry(lay: Layout) -> dict:
    return read_json(lay.registry, None) or {'methods': {}}


def load_tools(lay: Layout) -> dict:
    return read_json(lay.tools, None) or {'tools': {}, 'indicators': {}}


def load_observations(lay: Layout) -> list[dict]:
    out = []
    try:
        files = sorted(lay.observations.glob('*.json'))
    except FileNotFoundError:
        return out
    for f in files:
        obs = read_json(f)
        if obs and obs.get('video_id'):
            out.append(obs)
    return out


def analysed_ids(lay: Layout) -> set[str]:
    try:
        return {p.stem for p in lay.observations.glob('*.json')}
    except FileNotFoundError:
        return set()


# ---- validation ---------------------------------------------------------------
def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_observation(obs, registry: dict, video_id: str) -> list[str]:
    """Problems with an observation, empty when it is usable. `registry` is the current method registry."""
    if not isinstance(obs, dict):
        return ['the file is not a JSON object']
    problems = []
    if obs.get('video_id') != video_id:
        problems.append(f'video_id must be "{video_id}"')
    methods = obs.get('methods')
    if not isinstance(methods, list):
        return problems + ['"methods" must be a list']
    if not methods:
        if obs.get('no_analysis') is True and _text(obs.get('reason')):
            return problems
        return problems + ['no methods: either describe one or set "no_analysis": true with a "reason"']
    known = registry.get('methods', {})
    for i, method in enumerate(methods, 1):
        where = f'methods[{i}]'
        if not isinstance(method, dict):
            problems.append(f'{where} must be an object')
            continue
        mid, new = method.get('method_id'), method.get('new_method')
        existing = known.get(mid) if mid else None
        if bool(mid) == bool(new):
            problems.append(f'{where}: give exactly one of "method_id" (an existing id) or "new_method"')
        elif mid and existing is None:
            problems.append(f'{where}: method_id "{mid}" is not in the registry')
        elif new and not (isinstance(new, dict) and _text(new.get('name')) and _text(new.get('description'))):
            problems.append(f'{where}: new_method needs "name" and "description"')
        elif new and new.get('domain') not in DOMAINS:
            problems.append(f'{where}: new_method needs "domain", one of {", ".join(DOMAINS)}')
        elif new and len(new['name'].split()) > MAX_NAME_WORDS:
            problems.append(f'{where}: new_method name is {len(new["name"].split())} words; '
                            f'use at most {MAX_NAME_WORDS} (aim for 4-6)')
        elif new and slug(new['name']) in known:
            existing = known[slug(new['name'])]      # same name as an existing method: treated as that method
        steps = method.get('steps')
        if not isinstance(steps, list) or not steps:
            problems.append(f'{where}: "steps" must be a non-empty list')
            continue
        step_ids = {s['id'] for s in (existing or {}).get('steps', [])}
        for j, step in enumerate(steps, 1):
            at = f'{where}.steps[{j}]'
            if not isinstance(step, dict):
                problems.append(f'{at} must be an object')
                continue
            sid, nstep = step.get('step_id'), step.get('new_step')
            if bool(sid) == bool(nstep):
                problems.append(f'{at}: give exactly one of "step_id" (an existing step of this method) or "new_step"')
            elif sid and sid not in step_ids:
                problems.append(f'{at}: step_id "{sid}" is not a step of this method')
            elif nstep and not (isinstance(nstep, dict) and _text(nstep.get('title')) and _text(nstep.get('does'))
                                and _text(nstep.get('why'))):
                problems.append(f'{at}: new_step needs "title", "does" and "why"')
            if nstep and isinstance(nstep, dict) and slug(nstep.get('title', '')):
                step_ids.add(slug(nstep['title']))
            if seconds(step.get('at')) is None:
                problems.append(f'{at}: "at" must start with a timestamp like 12:34')
            for key in ('does', 'why'):
                if not _text(step.get(key)):
                    problems.append(f'{at}: "{key}" is empty')
            if step.get('tag') not in TAGS:
                problems.append(f'{at}: "tag" must be one of {", ".join(TAGS)}')
            if not isinstance(step.get('tools', []), list) or not isinstance(step.get('indicators', []), list):
                problems.append(f'{at}: "tools" and "indicators" must be lists of names')
        for k, rule in enumerate(method.get('rules') or [], 1):
            if not (isinstance(rule, dict) and _text(rule.get('text')) and rule.get('tag') in TAGS):
                problems.append(f'{where}.rules[{k}] needs "text" and a "tag" of {", ".join(TAGS)}')
    for key in ('tools', 'indicators'):
        for entry in obs.get(key) or []:
            if not (isinstance(entry, dict) and _text(entry.get('name'))):
                problems.append(f'every entry of "{key}" needs a "name"')
    names = [n for m in methods if isinstance(m, dict) for st in m.get('steps') or [] if isinstance(st, dict)
             for n in (st.get('tools') or []) if isinstance(n, str)]
    names += [e['name'] for e in obs.get('tools') or [] if isinstance(e, dict) and _text(e.get('name'))]
    for name in sorted(set(names)):
        if NOT_A_TOOL.search(name):
            problems.append(f'tool "{name}" is not a site or software; use the real name, or "Unidentified <what it looks like>"')
    return problems


# ---- merging ------------------------------------------------------------------
def merge(lay: Layout, obs: dict, meta: dict) -> dict:
    """Fold one validated observation into the registry and tool list; store it. Idempotent per video id."""
    registry, tools = load_registry(lay), load_tools(lay)
    known = registry['methods']
    resolved_methods = []
    for method in obs.get('methods') or []:
        if method.get('method_id'):
            mid = method['method_id']
        else:
            mid = slug(method['new_method']['name'])
            known.setdefault(mid, {'id': mid, 'name': method['new_method']['name'].strip(),
                                   'domain': method['new_method'].get('domain', 'stocks'),
                                   'description': method['new_method']['description'].strip(), 'steps': []})
        steps = known[mid]['steps']
        resolved_steps = []
        for step in method['steps']:
            if step.get('step_id'):
                sid = step['step_id']
            else:
                new = step['new_step']
                sid = slug(new['title'])
                if not any(s['id'] == sid for s in steps):
                    entry = {'id': sid, 'title': new['title'].strip(), 'does': new['does'].strip(), 'why': new['why'].strip()}
                    after = new.get('after')
                    index = next((n + 1 for n, s in enumerate(steps) if s['id'] == after), len(steps))
                    steps.insert(index, entry)
            tool_names = [_canonical(tools['tools'], n) for n in step.get('tools') or []]
            indicator_names = [_canonical(tools['indicators'], n) for n in step.get('indicators') or []]
            resolved_steps.append({**step, 'step_id': sid, 'new_step': None, 'tools': tool_names,
                                   'indicators': indicator_names})
        resolved_methods.append({**method, 'method_id': mid, 'new_method': None, 'steps': resolved_steps})
    for kind in ('tools', 'indicators'):
        for entry in obs.get(kind) or []:
            _canonical(tools[kind], entry['name'], entry)
    stored = {**meta, **{k: obs[k] for k in ('no_analysis', 'reason') if k in obs}, 'video_id': obs['video_id'],
              'methods': resolved_methods, 'tools': obs.get('tools') or [], 'indicators': obs.get('indicators') or []}
    write_json(lay.observations / f'{obs["video_id"]}.json', stored)
    _prune(lay, registry)
    write_json(lay.registry, registry)
    write_json(lay.tools, tools)
    return stored


def _canonical(table: dict, name: str, entry: dict | None = None) -> str:
    """The display name this tool/indicator is known by; the first spelling seen wins."""
    key = tool_key(name)
    row = table.setdefault(key, {'name': name.strip()})
    if entry:
        for field_name in ('kind', 'url', 'used_for', 'measures', 'how_used', 'platform'):
            if _text(entry.get(field_name)) and not row.get(field_name):
                row[field_name] = entry[field_name].strip()
    return row['name']


def _prune(lay: Layout, registry: dict) -> None:
    """Drop methods and steps that no stored observation uses any more (a re-run can retire a proposal)."""
    used_methods: dict[str, set[str]] = {}
    for obs in load_observations(lay):
        for m in obs.get('methods') or []:
            used_methods.setdefault(m['method_id'], set()).update(s['step_id'] for s in m['steps'])
    registry['methods'] = {mid: {**m, 'steps': [s for s in m['steps'] if s['id'] in used_methods[mid]]}
                           for mid, m in registry['methods'].items() if mid in used_methods}


# ---- rendering ----------------------------------------------------------------
def _published(obs: dict) -> str:
    return (obs.get('published_at') or '')[:10]


def _video_link(obs: dict, notes_dir: Path | None, from_dir: Path, at: str | None = None) -> str:
    title = (obs.get('title') or obs['video_id']).replace('|', '/')
    url = obs.get('url') or f'https://www.youtube.com/watch?v={obs["video_id"]}'
    secs = seconds(at) if at else None
    link = f'[{title}]({url}{("&t=" + str(secs) + "s") if secs is not None else ""})'
    note = find_note(notes_dir, obs['video_id']) if notes_dir else None
    if note is not None:
        link += f' ([note]({_rel(note, from_dir)}))'
    return link


def _rel(target: Path, from_dir: Path) -> str:
    import os
    return os.path.relpath(target, from_dir).replace('\\', '/')


def render(lay: Layout, notes_dir: Path | None = None, today: date | None = None) -> list[Path]:
    """Rebuild methods.md, methods/<id>.md and tools.md from _data/. Returns the files written."""
    registry, tools, observations = load_registry(lay), load_tools(lay), load_observations(lay)
    stamp = (today or date.today()).isoformat()
    by_method: dict[str, list[tuple[dict, dict]]] = {}
    for obs in observations:
        for m in obs.get('methods') or []:
            by_method.setdefault(m['method_id'], []).append((obs, m))
    written = []

    def put(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(path)
        written.append(path)

    def uniq(values) -> list[str]:
        seen, out = set(), []
        for v in values:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return out

    rows = []
    for mid, method in sorted(registry['methods'].items(), key=lambda kv: kv[1]['name'].lower()):
        uses = by_method.get(mid, [])
        steps = [s for _, m in uses for s in m['steps']]
        videos = sorted({o['video_id'] for o, _ in uses})
        dates = sorted(_published(o) for o, _ in uses if _published(o))
        platforms = uniq(t for s in steps for t in s.get('tools') or [])
        indicators = uniq(i for s in steps for i in s.get('indicators') or [])
        rows.append((method, len(videos), dates[-1] if dates else '', platforms, indicators))

        lines = [f'# {method["name"]}', '', f'_Generated {stamp} from `_data/`. Do not edit by hand._', '',
                 method['description'], '',
                 f'- **Type:** {method.get("domain", "stocks")} analysis',
                 f'- **Seen in:** {len(videos)} video(s){f", {dates[0]} to {dates[-1]}" if dates else ""}',
                 f'- **Sites/software:** {", ".join(platforms) or "none recorded"}',
                 f'- **Indicators:** {", ".join(indicators) or "none recorded"}', '', '## Step by step', '']
        for n, step in enumerate(method['steps'], 1):
            lines += [f'### {n}. {step["title"]}', '', f'- **Does:** {step["does"]}', f'- **Why:** {step["why"]}', '']
            seen = [(o, s) for o, m in uses for s in m['steps'] if s['step_id'] == step['id']]
            if seen:
                lines.append(f'Seen in {len({o["video_id"] for o, _ in seen})} video(s):')
                lines.append('')
            for o, s in sorted(seen, key=lambda p: (_published(p[0]), seconds(p[1].get('at')) or 0)):
                lines.append(f'- {_video_link(o, notes_dir, lay.methods_dir, s.get("at"))}, {s.get("at")} '
                             f'**[{s["tag"]}]** {s["does"]} _Why:_ {s["why"]}')
                for label, key in (('Data', 'data'), ('Tools', 'tools'), ('Indicators', 'indicators')):
                    items = s.get(key)
                    if items:
                        lines.append(f'  - {label}: {"; ".join(items) if isinstance(items, list) else items}')
                if _text(s.get('conclusion')):
                    lines.append(f'  - Conclusion: {s["conclusion"]}')
            lines.append('')
        rules = [(o, r) for o, m in uses for r in m.get('rules') or []]
        if rules:
            lines += ['## Rules of thumb', '']
            for o, r in sorted(rules, key=lambda p: _published(p[0])):
                lines.append(f'- {r["text"]} **[{r["tag"]}]** ({_video_link(o, notes_dir, lay.methods_dir)})')
            lines.append('')
        lines += ['## Videos using this method', '']
        for o in sorted({id(o): o for o, _ in uses}.values(), key=lambda o: _published(o), reverse=True):
            lines.append(f'- {_published(o)} {o.get("channel") or ""}: {_video_link(o, notes_dir, lay.methods_dir)}')
        put(lay.methods_dir / f'{mid}.md', '\n'.join(lines) + '\n')

    none = [o for o in observations if not o.get('methods')]
    lines = ['# Analysis methods: master list', '',
             f'_Generated {stamp} from `_data/`. Do not edit by hand. Each row links to the full step-by-step file._', '',
             f'{len(rows)} method(s) from {len(observations) - len(none)} video(s) '
             f'({len(none)} more showed no analysis workflow).', '']
    for domain in DOMAINS:
        group = [r for r in rows if r[0].get('domain', 'stocks') == domain]
        lines += [f'## {DOMAIN_TITLES[domain]} ({len(group)})', '']
        if not group:
            lines += ['_None yet._', '']
            continue
        lines += ['| Method | What it is | Sites/software | Indicators | Videos | Last seen |', '|---|---|---|---|---|---|']
        for method, count, last, platforms, indicators in sorted(group, key=lambda r: (-r[1], r[0]['name'].lower())):
            short = method['description'].replace('|', '/').replace('\n', ' ')
            short = short if len(short) <= 220 else short[:217].rstrip() + '...'
            lines.append(f'| [{method["name"]}](methods/{method["id"]}.md) | {short} | {", ".join(platforms[:5])} | '
                         f'{", ".join(indicators[:6])} | {count} | {last} |')
        lines.append('')
    lines += ['Tracker of sites, software and indicators: [tools.md](tools.md).']
    put(lay.master, '\n'.join(lines) + '\n')

    # tracker: aggregate per tool / indicator
    usage: dict[str, dict[str, dict]] = {'tools': {}, 'indicators': {}}
    for obs in observations:
        for m in obs.get('methods') or []:
            for s in m['steps']:
                for kind in ('tools', 'indicators'):
                    for name in s.get(kind) or []:
                        u = usage[kind].setdefault(name, {'videos': set(), 'methods': set(), 'dates': []})
                        u['videos'].add(obs['video_id'])
                        u['methods'].add(m['method_id'])
                        if _published(obs):
                            u['dates'].append(_published(obs))

    def method_links(ids) -> str:
        return ', '.join(f'[{registry["methods"][i]["name"]}](methods/{i}.md)' for i in sorted(ids) if i in registry['methods'])

    def domains_of(ids) -> str:
        found = {registry['methods'][i].get('domain', 'stocks') for i in ids if i in registry['methods']}
        return ' + '.join(d for d in DOMAINS if d in found)

    def table(kind: str, head: str, cols) -> list[str]:
        out = [head, '|' + '---|' * (len(cols) + 6)]
        table_rows = []
        for key, row in tools[kind].items():
            u = usage[kind].get(row['name'])
            if u:
                table_rows.append((row, u))
        for row, u in sorted(table_rows, key=lambda p: (-len(p[1]['videos']), p[0]['name'].lower())):
            cells = [(row.get(c) or '').replace('|', '/').replace('\n', ' ') for c in cols]
            dates = sorted(u['dates'])
            out.append('| ' + ' | '.join([row['name'], *cells, domains_of(u['methods']), method_links(u['methods']),
                                           str(len(u['videos'])),
                                           dates[0] if dates else '', dates[-1] if dates else '']) + ' |')
        return out

    lines = ['# Sites, software and indicators', '', f'_Generated {stamp} from `_data/`. Do not edit by hand._', '',
             '## Websites and software', '',
             *table('tools', '| Name | Kind | URL | Used for | Type | Methods | Videos | First seen | Last seen |',
                    ('kind', 'url', 'used_for')),
             '', '## Indicators', '',
             *table('indicators', '| Name | What it measures | How it is used | Platform | Type | Methods | Videos | First seen | Last seen |',
                    ('measures', 'how_used', 'platform')), '']
    put(lay.tracker, '\n'.join(lines))
    return written


# ---- the model pass -----------------------------------------------------------
def prompt_template(paths: Paths) -> str:
    for path in (paths.home / PROMPT_NAME, SKILL_DIR / PROMPT_NAME):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise FileNotFoundError(f'no {PROMPT_NAME} in {paths.home} or {SKILL_DIR}')


def registry_digest(lay: Layout) -> str:
    """What the model needs to match against: existing methods with their steps, and the known tool names."""
    registry, tools = load_registry(lay), load_tools(lay)
    if not registry['methods']:
        return '(no methods recorded yet: every workflow you find is a new method)'
    lines = []
    for mid, m in registry['methods'].items():
        lines.append(f'- method_id `{mid}`: {m["name"]}. {m["description"]}')
        lines += [f'    - step_id `{s["id"]}`: {s["title"]}: {s["does"]}' for s in m['steps']]
    lines.append('Known sites/software: ' + (', '.join(sorted(r['name'] for r in tools['tools'].values())) or 'none'))
    lines.append('Known indicators: ' + (', '.join(sorted(r['name'] for r in tools['indicators'].values())) or 'none'))
    return '\n'.join(lines)


def build_prompt(template: str, manifest: dict, paths: Paths, lay: Layout, problems: list[str] | None = None) -> str:
    vid = manifest['video_id']
    values = {'video_id': vid, 'title': manifest.get('title') or '', 'channel': manifest.get('channel') or '',
              'url': manifest.get('url') or '', 'raw_dir': (paths.raw / vid).as_posix(),
              'out_path': (lay.inbox / f'{vid}.json').as_posix(), 'registry': registry_digest(lay),
              'skill_dir': SKILL_DIR.as_posix()}
    text = template
    for key, value in values.items():
        text = text.replace('{' + key + '}', value)
    if problems:
        text += ('\n\n## Your previous attempt was rejected\nFix every problem below, then write the file again:\n'
                 + '\n'.join(f'- {p}' for p in problems) + '\n')
    return text


@dataclass
class AnalysisResult:
    video_id: str
    ok: bool = False
    methods: int = 0
    problems: list[str] = field(default_factory=list)
    seconds: float = 0.0
    skipped: str = ''


def manifest_meta(manifest: dict) -> dict:
    return {'title': manifest.get('title'), 'channel': manifest.get('channel'), 'url': manifest.get('url'),
            'published_at': manifest.get('published_at')}


def run_analysis(store: Store, manifest: dict, *, runner: Runner = claude_runner, template: str | None = None,
                 attempts: int = 2) -> AnalysisResult:
    """One video: ask the model, validate, merge. Never raises for a model or file problem."""
    paths = store.paths
    lay = layout(paths)
    vid = manifest['video_id']
    result = AnalysisResult(vid)
    raw = paths.raw / vid
    if not (raw / 'transcript.txt').is_file():
        result.skipped = 'no transcript.txt on disk'
        return result
    template = template or prompt_template(paths)
    started = time.monotonic()
    problems: list[str] = []
    for attempt in range(attempts):
        inbox = lay.inbox / f'{vid}.json'
        inbox.unlink(missing_ok=True)
        prompt = build_prompt(template, manifest, paths, lay, problems or None)
        log = paths.logs / date.today().isoformat() / f'{vid}.analysis.log'
        out = runner(manifest, prompt, log)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f'attempt {attempt + 1}, exit {out.returncode}\n\n{out.output}', encoding='utf-8')
        if not inbox.is_file():
            problems = [f'no file was written at {inbox.as_posix()} (exit {out.returncode})']
            continue
        try:
            obs = json.loads(inbox.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, UnicodeError) as exc:
            problems = [f'the file is not valid JSON: {exc}']
            continue
        problems = validate_observation(obs, load_registry(lay), vid)
        if not problems:
            stored = merge(lay, obs, manifest_meta(manifest))
            inbox.unlink(missing_ok=True)
            result.ok, result.methods = True, len(stored['methods'])
            break
    result.problems = problems if not result.ok else []
    result.seconds = time.monotonic() - started
    return result


def pending_ids(store: Store) -> list[str]:
    """Done videos that have no observation yet, oldest first."""
    lay = layout(store.paths)
    have = analysed_ids(lay)
    manifests = [m for m in (read_json(p) for p in sorted(store.dirs['done'].glob('*.json'))) if m and m.get('video_id')]
    manifests.sort(key=lambda m: m.get('published_at') or '')
    return [m['video_id'] for m in manifests if m['video_id'] not in have]


def pick_sample(store: Store, n: int) -> list[str]:
    """n not-yet-analysed videos spread across channels (round-robin), only those whose frames are still on disk."""
    by_channel: dict[str, list[str]] = {}
    for vid in pending_ids(store):
        raw = store.paths.raw / vid
        if (raw / 'transcript.txt').is_file() and (raw / 'sheets').is_dir():
            manifest = read_json(store.item_path('done', vid)) or {}
            by_channel.setdefault(manifest.get('channel') or '', []).append(vid)
    picks: list[str] = []
    queues = [list(reversed(v)) for _, v in sorted(by_channel.items())]     # newest first within a channel
    while len(picks) < n and any(queues):
        for q in queues:
            if q and len(picks) < n:
                picks.append(q.pop())
    return picks


def analyse_many(store: Store, ids: list[str], *, runner: Runner = claude_runner, notes_dir: Path | None = None,
                 on_result: Callable[[AnalysisResult], None] | None = None) -> list[AnalysisResult]:
    """Analyse each id (a done video), re-rendering after each so a long run is useful before it finishes."""
    lay = layout(store.paths)
    template = prompt_template(store.paths)
    results = []
    for vid in ids:
        manifest = read_json(store.item_path('done', vid))
        if not manifest:
            res = AnalysisResult(vid, skipped='not in done/')
        else:
            res = run_analysis(store, manifest, runner=runner, template=template)
            if res.ok:
                render(lay, notes_dir or store.paths.notes)
        results.append(res)
        if on_result:
            on_result(res)
    return results
