#!/usr/bin/env python3
"""Turn any YouTube URL form into an 11-character video id."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
CHANNEL_ID = re.compile(r'UC[0-9A-Za-z_-]{22}')
_HOSTS = {'youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com', 'youtu.be'}


def extract_video_id(text: str) -> str | None:
    text = (text or '').strip()
    if not text:
        return None
    if '://' not in text:
        text = 'https://' + text
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    host = (parsed.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if host not in _HOSTS:
        return None
    parts = [p for p in parsed.path.split('/') if p]
    candidate = None
    if host == 'youtu.be':
        candidate = parts[0] if parts else None
    elif parts and parts[0] == 'watch':
        candidate = (parse_qs(parsed.query).get('v') or [None])[0]
    elif len(parts) >= 2 and parts[0] in ('shorts', 'live', 'embed', 'v'):
        candidate = parts[1]
    if candidate and VIDEO_ID.fullmatch(candidate):
        return candidate
    return None


def watch_url(video_id: str) -> str:
    return f'https://www.youtube.com/watch?v={video_id}'


REEL_CODE = re.compile(r'[A-Za-z0-9_-]{5,40}')
_IG_HOSTS = {'instagram.com', 'm.instagram.com'}


def extract_reel_code(text: str) -> str | None:
    """instagram.com/reel/<code>/, /reels/<code>/, /p/<code>/ or /<user>/reel/<code>/ -> <code>."""
    text = (text or '').strip()
    if not text:
        return None
    if '://' not in text:
        text = 'https://' + text
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    host = (parsed.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if host not in _IG_HOSTS:
        return None
    parts = [p for p in parsed.path.split('/') if p]
    for i, part in enumerate(parts[:-1]):
        if part in ('reel', 'reels', 'p') and REEL_CODE.fullmatch(parts[i + 1]):
            return parts[i + 1]
    return None


def reel_url(code: str) -> str:
    return f'https://www.instagram.com/reel/{code}/'
