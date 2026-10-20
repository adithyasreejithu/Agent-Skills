#!/usr/bin/env python3
"""Parse a YouTube channel Atom feed. Pure: takes text, returns dicts (HTTP lives in ytnet.py)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

NS = {
    'a': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
    'media': 'http://search.yahoo.com/mrss/',
}


class FeedError(Exception):
    pass


def _text(node, path: str) -> str | None:
    found = node.find(path, NS)
    return found.text.strip() if found is not None and found.text else None


def parse_feed(text: str) -> list[dict]:
    """Return entries newest-first as dicts. Entries without a video id are dropped."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise FeedError(f'feed is not valid XML: {exc}') from None
    if root.tag != '{%s}feed' % NS['a']:
        raise FeedError('feed root is not an Atom <feed>')
    channel_name = _text(root, 'a:author/a:name')
    channel_id = _text(root, 'yt:channelId')
    entries = []
    for e in root.findall('a:entry', NS):
        video_id = _text(e, 'yt:videoId')
        if not video_id:
            continue
        link = e.find('a:link[@rel="alternate"]', NS)
        stats = e.find('media:group/media:community/media:statistics', NS)
        views = stats.get('views') if stats is not None else None
        entries.append({
            'video_id': video_id,
            'title': _text(e, 'a:title') or '',
            'url': link.get('href') if link is not None else f'https://www.youtube.com/watch?v={video_id}',
            'published_at': _text(e, 'a:published'),
            'channel_id': _text(e, 'yt:channelId') or channel_id,
            'channel_name': _text(e, 'a:author/a:name') or channel_name,
            'description': _text(e, 'media:group/media:description') or '',
            'views': int(views) if views and views.isdigit() else None,
        })
    entries.sort(key=lambda x: x['published_at'] or '', reverse=True)
    return entries
