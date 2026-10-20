#!/usr/bin/env python3
"""Pure filter checks. Each returns a skip reason (str) or None when the video passes."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from config import Source
from store import parse_ts

LIVE_STATUSES = {'is_live', 'is_upcoming'}


def title_reason(title: str, source: Source) -> str | None:
    if source.exclude_title and re.search(source.exclude_title, title, re.I):
        return 'title excluded'
    if source.include_title and not re.search(source.include_title, title, re.I):
        return 'title not matched'
    return None


def age_reason(published_at: str | None, source: Source, now: datetime) -> str | None:
    published = parse_ts(published_at)
    if published and now - published > timedelta(days=source.max_age_days):
        return 'too old'
    return None


def duration_reason(duration_s: int | None, source: Source) -> str | None:
    """Unknown duration passes: better to queue than silently drop."""
    if duration_s is None:
        return None
    if duration_s < source.min_duration_s:
        return 'too short'
    if duration_s > source.max_duration_s:
        return 'too long'
    return None
