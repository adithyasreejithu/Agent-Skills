#!/usr/bin/env python3
"""The note contract: what a finished summary must look like before the queue calls it done.

A note is `<notes_dir>/<video_id>-<slug>.md`: YAML-ish frontmatter, one H1, then sections.
The checker is deliberately mechanical (keys, headings, filename); it cannot judge whether the analysis is good.
"""
from __future__ import annotations

import re
from pathlib import Path

REQUIRED_KEYS = ('video_id', 'channel', 'title', 'published', 'ingested', 'source', 'evidence')
REQUIRED_HEADINGS = ('Market view', 'Positions and plans')
EVIDENCE = ('captions', 'frames', 'captions+frames', 'gemini')
STANCES = ('bullish', 'bearish', 'neutral', 'mixed')


def split_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """Return (fields, body) or None when the file does not open with a --- block."""
    lines = text.lstrip('﻿').splitlines()
    if not lines or lines[0].strip() != '---':
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() == '---':
            fields = {}
            for line in lines[1:end]:
                if ':' in line and not line.startswith((' ', '#')):
                    key, value = line.split(':', 1)
                    fields[key.strip()] = value.strip().strip('"\'')
            return fields, '\n'.join(lines[end + 1:])
    return None


def parse_list(value: str) -> list[str]:
    """`[NVDA, AMD]` or `NVDA, AMD` -> ['NVDA', 'AMD']."""
    return [part.strip().strip('"\'') for part in value.strip().strip('[]').split(',') if part.strip().strip('"\'')]


def validate(text: str, video_id: str, filename: str | None = None) -> list[str]:
    """Return a list of problems; empty means the note meets the contract."""
    problems = []
    if filename is not None and not (filename.startswith(video_id + '-') or filename == video_id + '.md'):
        problems.append(f'filename must start with "{video_id}-" (got {filename})')
    parsed = split_frontmatter(text)
    if parsed is None:
        return problems + ['missing frontmatter block (--- ... ---) at the top of the file']
    fields, body = parsed
    for key in REQUIRED_KEYS:
        if not fields.get(key):
            problems.append(f'frontmatter is missing "{key}"')
    if fields.get('video_id') and fields['video_id'] != video_id:
        problems.append(f'frontmatter video_id "{fields["video_id"]}" does not match {video_id}')
    if fields.get('evidence') and fields['evidence'] not in EVIDENCE:
        problems.append(f'evidence must be one of {", ".join(EVIDENCE)}')
    if fields.get('stance') and fields['stance'] not in STANCES:
        problems.append(f'stance must be one of {", ".join(STANCES)}')
    if not re.search(r'^# \S', body, re.M):
        problems.append('missing a "# Title" heading')
    headings = {h.strip().lower() for h in re.findall(r'^##\s+(.+?)\s*$', body, re.M)}
    for heading in REQUIRED_HEADINGS:
        if heading.lower() not in headings:
            problems.append(f'missing section "## {heading}"')
    if len(body.strip()) < 400:
        problems.append('body is under 400 characters; the note looks empty')
    return problems


def find_note(notes_dir: Path, video_id: str) -> Path | None:
    """The newest note file for a video id, or None."""
    try:
        matches = [p for p in notes_dir.iterdir()
                   if p.suffix == '.md' and (p.name.startswith(video_id + '-') or p.name == video_id + '.md')]
    except FileNotFoundError:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def summarize(text: str) -> dict:
    """Pull the fields the handoff manifest and digest need."""
    parsed = split_frontmatter(text)
    fields = parsed[0] if parsed else {}
    return {'tickers': parse_list(fields.get('tickers', '')), 'stance': fields.get('stance') or None,
            'evidence': fields.get('evidence') or None}
