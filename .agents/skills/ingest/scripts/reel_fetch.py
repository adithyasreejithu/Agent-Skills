#!/usr/bin/env python3
"""One reel -> timestamped transcript, using the watch skill's own downloader and Gemini audio transcription.

  python reel_fetch.py <reel url> <work dir>      prints one JSON object, always exit 0

Runs in its own process on purpose: watch and ingest both have a `config` module, so their code cannot share an
interpreter. Only the audio is downloaded; it is converted to 16 kHz mono mp3, sent to Gemini, and the work dir
is deleted afterwards whatever happens.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

WATCH_SCRIPTS = Path(__file__).resolve().parents[2] / 'watch' / 'scripts'
sys.path[0] = str(WATCH_SCRIPTS)      # replace this folder: ingest's config.py would shadow watch's

from config import get_config, load_gemini_key  # noqa: E402  (watch's)
from download import download  # noqa: E402
from gemini import transcribe_audio  # noqa: E402
from runtime import configure_stdio  # noqa: E402
from whisper import audio_duration, extract_audio  # noqa: E402


def kind_of(message: str) -> str:
    """quota / setup stop the whole run; login / unavailable / failed are about this reel."""
    low = message.lower()
    if 'gemini quota' in low or ('429' in low and 'gemini' in low):
        return 'quota'
    if 'gemini auth' in low or 'gemini network' in low or 'not installed' in low or 'cannot run' in low:
        return 'setup'
    if 'too many requests' in low or '429' in low or 'login' in low or 'sign in' in low or 'rate limit' in low:
        return 'login'
    if 'not available' in low or 'private' in low or '404' in low or 'removed' in low:
        return 'unavailable'
    return 'failed'


def fetch(url: str, work: Path) -> dict:
    key = load_gemini_key()
    if not key:
        return {'ok': False, 'kind': 'setup', 'error': 'GEMINI_API_KEY is not set (see ~/.config/watch/.env)'}
    model = get_config()['gemini_model']
    try:
        got = download(url, work, audio_only=True)
        info = got.get('info') or {}
        mp3 = extract_audio(got['video_path'], work / 'audio.mp3')
        duration = audio_duration(mp3)
        segments = transcribe_audio(mp3, key, model=model, duration=duration)
        return {'ok': True, 'segments': [dict(s) for s in segments], 'duration_s': duration, 'model': model,
                'gemini_tokens': getattr(segments, 'total_tokens', None),
                'info': {'uploader': info.get('uploader'), 'upload_date': info.get('upload_date')}}
    except SystemExit as exc:
        message = str(exc)
        if 'no audio' in message.lower():
            return {'ok': True, 'segments': [], 'duration_s': None, 'model': model, 'gemini_tokens': None,
                    'info': {}, 'note': 'no audio track'}
        return {'ok': False, 'kind': kind_of(message), 'error': message[:600]}
    except Exception as exc:             # never let a traceback replace the JSON line
        return {'ok': False, 'kind': 'failed', 'error': f'{type(exc).__name__}: {exc}'[:600]}


def main() -> int:
    configure_stdio()
    if len(sys.argv) != 3:
        print(json.dumps({'ok': False, 'kind': 'setup', 'error': 'usage: reel_fetch.py <url> <work dir>'}))
        return 0
    work = Path(sys.argv[2])
    try:
        print(json.dumps(fetch(sys.argv[1], work), ensure_ascii=False))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
