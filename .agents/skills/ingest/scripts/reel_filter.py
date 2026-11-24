"""Cheap checks that spot filler reels before any model sees them (tested in plan/reels/FINDINGS.md, section 4).

  stage 1, before download   a reel under SHORT_S seconds whose caption carries no information
  stage 2, before Claude     a reel with fewer than FEW_WORDS spoken words whose caption carries no information

Both become a one-line `filler` entry written by Python. A sponsor marker is only a hint for the model: sponsored
reels are often long speech that still names stocks, so they are never filtered out by rule.
"""
from __future__ import annotations

import re

SHORT_S = 12
FEW_WORDS = 20
INFO_CAPTION_CHARS = 150

_HASHTAG = re.compile(r'#\S+')
_DOLLAR_TICKER = re.compile(r'\$[A-Za-z]{1,5}\b')
_CAPS_WORD = re.compile(r'\b[A-Z]{2,5}\b')
_SPONSOR = re.compile(r'#ad\b|#sponsored\b|#\w*partner\b|\bsponsored\b|paid (?:partnership|advertisement|promotion)'
                      r'|disseminated on behalf of|\bfor sponsoring\b|\bbrought to you by\b'
                      r'|\buse (?:my )?code\b|\bpromo code\b|\bdiscount code\b', re.I)


def caption_has_info(caption: str | None) -> bool:
    """A caption says something when, hashtags aside, it has a digit, a $TICKER, two or more capitalised
    ticker-like words, or more than INFO_CAPTION_CHARS characters."""
    caption = caption or ''
    body = _HASHTAG.sub('', caption)
    return (any(ch.isdigit() for ch in body) or bool(_DOLLAR_TICKER.search(caption))
            or len(_CAPS_WORD.findall(body)) >= 2 or len(body.strip()) > INFO_CAPTION_CHARS)


def words_spoken(segments) -> int:
    return sum(len(str(s.get('text') or '').split()) for s in segments or [])


def before_download(caption: str | None, duration_s: float | None) -> str | None:
    """Stage 1: the reason this reel is filler, judged from its page details alone, or None."""
    if duration_s and duration_s < SHORT_S and not caption_has_info(caption):
        return f'under {SHORT_S} s, caption has no information'
    return None


def before_model(caption: str | None, segments) -> str | None:
    """Stage 2: the reason this transcribed reel is filler, or None."""
    words = words_spoken(segments)
    if words < FEW_WORDS and not caption_has_info(caption):
        return f'{words} word(s) spoken, caption has no information'
    return None


def sponsor_hint(caption: str | None, transcript: str = '') -> str | None:
    match = _SPONSOR.search(f'{caption or ""}\n{transcript}')
    return match.group(0) if match else None


def filler_line(caption: str | None) -> str:
    """The one line a rule-filtered reel gets: its caption's first line, without hashtags."""
    first = next((l.strip() for l in _HASHTAG.sub('', caption or '').splitlines() if l.strip()), '')
    return f'No market content (filtered by rule); caption: "{first[:100]}"' if first else \
        'No market content (filtered by rule); no caption.'
