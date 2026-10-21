#!/usr/bin/env python3
"""Ingest settings: folder locations, source list, defaults.

Precedence for every folder setting (first match wins):
  CLI flag -> environment -> ./ingest.env (project) -> ~/.config/ingest/.env (user) -> built-in default.
Relative paths resolve against the current directory. Nothing here is secret; API keys stay with `watch`.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

USER_CONFIG = Path.home() / '.config' / 'ingest' / '.env'
PROJECT_CONFIG_NAME = 'ingest.env'
STALE_CLAIM_HOURS = 2
DEFAULT_RUN_BUDGET_MIN = 180


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Paths:
    home: Path
    notes: Path
    digests: Path
    raw: Path
    state: Path
    logs: Path
    sources_file: Path
    testing: bool = False          # run videos through watch --testing and label them (training)
    labels: Path | None = None     # where training label files live when testing is on


@dataclass(frozen=True)
class Defaults:
    priority: int = 50
    skip_shorts: bool = True
    min_duration_s: int = 240
    max_duration_s: int = 5400
    max_age_days: int = 7


@dataclass(frozen=True)
class Source:
    ref: str                      # what the user wrote: @handle, URL or UC... id
    name: str
    priority: int
    skip_shorts: bool
    min_duration_s: int
    max_duration_s: int
    max_age_days: int
    include_title: str | None = None
    exclude_title: str | None = None
    enabled: bool = True
    tags: tuple[str, ...] = ()
    channel_id: str | None = None


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines; no expansion, so Windows paths work. Last assignment wins."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        key, value = raw.split('=', 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', key):
            continue
        if len(value) >= 2 and value[0] in ('"', "'") and value.endswith(value[0]):
            value = value[1:-1]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def read_env_file(path: Path) -> dict[str, str]:
    try:
        return parse_env(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise ConfigError(f'Cannot read {path}; check permissions and save it as UTF-8.') from None


def _absolute(value: str, cwd: Path) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    return path if path.is_absolute() else (cwd / path)


def resolve_paths(cli_home: str | None = None, env: dict[str, str] | None = None,
                  cwd: Path | None = None, user_config: Path | None = None) -> Paths:
    cwd = Path.cwd() if cwd is None else cwd
    env = dict(os.environ) if env is None else env
    project = read_env_file(cwd / PROJECT_CONFIG_NAME)
    user = read_env_file(USER_CONFIG if user_config is None else user_config)

    def pick(key: str) -> str | None:
        for source in (env, project, user):
            if source.get(key):
                return source[key]
        return None

    home_value = cli_home or pick('INGEST_HOME')
    home = _absolute(home_value, cwd) if home_value else cwd / 'queue'

    def folder(key: str, default: Path) -> Path:
        value = pick(key)
        return _absolute(value, cwd) if value else default

    notes = folder('INGEST_NOTES_DIR', home / 'notes')
    return Paths(
        home=home,
        notes=notes,
        digests=folder('INGEST_DIGESTS_DIR', notes / '_digests'),
        raw=folder('INGEST_RAW_DIR', home / 'raw'),
        state=folder('INGEST_STATE_DIR', home),
        logs=folder('INGEST_LOGS_DIR', home / 'logs'),
        sources_file=folder('INGEST_SOURCES_FILE', home / 'sources.toml'),
        testing=(pick('INGEST_TESTING') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
        labels=folder('INGEST_LABELS_DIR', cwd / 'training' / 'labels'),
    )


STARTER_SOURCES = """\
# Channels to follow. Defaults below apply to every channel unless overridden in its block.
# Add a channel with:  python run.py source add @handle --name "Channel Name"

[defaults]
priority       = 50       # 0-100; higher is processed first (manual adds are always higher)
skip_shorts    = true
min_duration_s = 240      # ignore videos under 4 minutes
max_duration_s = 5400     # ignore videos over 90 minutes
max_age_days   = 7        # ignore videos older than this when first seen

# [[source]]
# handle   = "@OptionsWithRyan"     # or url = "https://www.youtube.com/@..." or channel_id = "UC..."
# name     = "Options With Ryan"
# priority = 60
# tags     = ["options", "stocks"]
# include_title = "earnings|outlook"   # optional regex; title must match
# exclude_title = "giveaway|live q&a"  # optional regex; video is skipped if it matches
# max_duration_s = 7200
# enabled = false
"""


def _int(table: dict, key: str, default: int, where: str) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f'{where}: {key} must be a non-negative whole number.')
    return value


def _bool(table: dict, key: str, default: bool, where: str) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f'{where}: {key} must be true or false.')
    return value


def _regex(table: dict, key: str, where: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f'{where}: {key} must be a string.')
    try:
        re.compile(value)
    except re.error as exc:
        raise ConfigError(f'{where}: {key} is not a valid regex ({exc}).') from None
    return value


def load_sources(path: Path) -> tuple[Defaults, list[Source]]:
    """A missing file means zero config: built-in defaults and no channels."""
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return Defaults(), []
    except (OSError, UnicodeError):
        raise ConfigError(f'Cannot read {path}.') from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f'{path} is not valid TOML: {exc}') from None

    table = data.get('defaults', {})
    d = Defaults(
        priority=_int(table, 'priority', 50, '[defaults]'),
        skip_shorts=_bool(table, 'skip_shorts', True, '[defaults]'),
        min_duration_s=_int(table, 'min_duration_s', 240, '[defaults]'),
        max_duration_s=_int(table, 'max_duration_s', 5400, '[defaults]'),
        max_age_days=_int(table, 'max_age_days', 7, '[defaults]'),
    )
    sources: list[Source] = []
    seen: set[str] = set()
    for index, s in enumerate(data.get('source', []), 1):
        where = f'[[source]] #{index}'
        ref = s.get('channel_id') or s.get('handle') or s.get('url')
        if not isinstance(ref, str) or not ref.strip():
            raise ConfigError(f'{where}: needs one of handle, url or channel_id.')
        ref = ref.strip()
        if ref.lower() in seen:
            raise ConfigError(f'{where}: {ref} is listed twice.')
        seen.add(ref.lower())
        tags = s.get('tags', [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ConfigError(f'{where}: tags must be a list of strings.')
        sources.append(Source(
            ref=ref,
            name=str(s.get('name') or ref),
            priority=_int(s, 'priority', d.priority, where),
            skip_shorts=_bool(s, 'skip_shorts', d.skip_shorts, where),
            min_duration_s=_int(s, 'min_duration_s', d.min_duration_s, where),
            max_duration_s=_int(s, 'max_duration_s', d.max_duration_s, where),
            max_age_days=_int(s, 'max_age_days', d.max_age_days, where),
            include_title=_regex(s, 'include_title', where),
            exclude_title=_regex(s, 'exclude_title', where),
            enabled=_bool(s, 'enabled', True, where),
            tags=tuple(tags),
            channel_id=ref if re.fullmatch(r'UC[0-9A-Za-z_-]{22}', ref) else None,
        ))
    return d, sources
