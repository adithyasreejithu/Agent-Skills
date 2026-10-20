#!/usr/bin/env python3
"""Everything that touches the network or yt-dlp, behind one class so tests can swap in a fake."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

from urls import CHANNEL_ID

USER_AGENT = 'Mozilla/5.0 (compatible; ingest-skill/0.1)'
FEED_URL = 'https://www.youtube.com/feeds/videos.xml?channel_id={}'
HTTP_TIMEOUT = 15
YTDLP_TIMEOUT = 120
_UNAVAILABLE = re.compile(r'(video unavailable|private video|has been removed|this video is not available'
                          r'|account associated with this video has been terminated)', re.I)


class NetError(Exception):
    pass


class Unavailable(NetError):
    """The video is gone, private or blocked; retrying will not help."""


@dataclass
class FeedResult:
    status: int
    text: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _ytdlp() -> list[str]:
    found = shutil.which('yt-dlp')
    return [found] if found else [sys.executable, '-m', 'yt_dlp']


class Net:
    def fetch_feed(self, channel_id: str, etag: str | None = None, last_modified: str | None = None) -> FeedResult:
        headers = {'User-Agent': USER_AGENT}
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        request = urllib.request.Request(FEED_URL.format(channel_id), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
                body = response.read().decode('utf-8', errors='replace')
                return FeedResult(response.status, body, response.headers.get('ETag'),
                                  response.headers.get('Last-Modified'))
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return FeedResult(304)
            raise NetError(f'feed HTTP {exc.code}') from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NetError(f'feed request failed: {type(exc).__name__}') from None

    def resolve_channel(self, ref: str) -> str:
        """@handle, channel URL or UC id -> UC id (one yt-dlp call, cached by the caller)."""
        ref = ref.strip()
        if CHANNEL_ID.fullmatch(ref):
            return ref
        match = re.search(r'/channel/(UC[0-9A-Za-z_-]{22})', ref)
        if match:
            return match.group(1)
        if ref.startswith('@'):
            url = f'https://www.youtube.com/{ref}'
        elif '://' in ref or '.' in ref.split('/')[0]:
            url = ref if '://' in ref else 'https://' + ref
        else:
            url = f'https://www.youtube.com/@{ref}'
        data = self._ytdlp_json(['--flat-playlist', '--playlist-items', '1', url])
        channel_id = data.get('channel_id') or data.get('uploader_id')
        if not channel_id or not CHANNEL_ID.fullmatch(channel_id):
            raise NetError(f'could not find a channel id for {ref}')
        return channel_id

    def is_short(self, video_id: str) -> bool | None:
        """200 on /shorts/<id> means a Short; a redirect to /watch means a normal video."""
        opener = urllib.request.build_opener(_NoRedirect)
        request = urllib.request.Request(f'https://www.youtube.com/shorts/{video_id}', method='HEAD',
                                         headers={'User-Agent': USER_AGENT})
        try:
            with opener.open(request, timeout=HTTP_TIMEOUT) as response:
                return response.status == 200
        except urllib.error.HTTPError as exc:
            return False if 300 <= exc.code < 400 else None
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    def video_meta(self, url: str) -> dict:
        data = self._ytdlp_json(['--no-playlist', url])
        return {
            'title': data.get('title'),
            'channel': data.get('channel') or data.get('uploader'),
            'channel_id': data.get('channel_id'),
            'duration_s': int(data['duration']) if isinstance(data.get('duration'), (int, float)) else None,
            'live_status': data.get('live_status'),
            'upload_date': data.get('upload_date'),
        }

    def _ytdlp_json(self, args: list[str]) -> dict:
        cmd = [*_ytdlp(), '--skip-download', '--no-warnings', '--dump-single-json', *args]
        try:
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace',
                                    timeout=YTDLP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetError(f'yt-dlp did not run: {type(exc).__name__}') from None
        if result.returncode != 0:
            message = (result.stderr or '').strip().splitlines()[-1:] or ['unknown error']
            error = Unavailable if _UNAVAILABLE.search(result.stderr or '') else NetError
            raise error(f'yt-dlp failed: {message[0][:200]}')
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise NetError('yt-dlp returned unreadable output') from None
