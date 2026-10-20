from __future__ import annotations

import _path  # noqa: F401
from config import Defaults, Paths, Source
from ytnet import FeedResult, NetError, Unavailable

CHANNEL = 'UCQnIfbieTyf53CZBiyLAkjg'


def make_paths(root) -> Paths:
    return Paths(home=root / 'queue', notes=root / 'notes', digests=root / 'notes' / '_digests',
                 raw=root / 'raw', state=root / 'queue', logs=root / 'queue' / 'logs',
                 sources_file=root / 'queue' / 'sources.toml')


def make_source(**overrides) -> Source:
    d = Defaults()
    values = dict(ref='@OptionsWithRyan', name='Options With Ryan', priority=d.priority, skip_shorts=True,
                  min_duration_s=d.min_duration_s, max_duration_s=d.max_duration_s, max_age_days=10_000,
                  channel_id=CHANNEL)
    values.update(overrides)
    return Source(**values)


class FakeNet:
    """Stands in for ytnet.Net. `metas` maps video_id -> meta dict (or 'gone' / 'error').

    Ids without an entry get a normal 10-minute video.
    """

    def __init__(self, feed_xml: str | None = None, metas=None, shorts=(), etag='etag-1'):
        self.feed_xml = feed_xml
        self.metas = metas or {}
        self.shorts = set(shorts)
        self.etag = etag
        self.feed_error: str | None = None
        self.calls: list[tuple] = []

    def fetch_feed(self, channel_id, etag=None, last_modified=None):
        self.calls.append(('feed', channel_id, etag))
        if self.feed_error:
            raise NetError(self.feed_error)
        if etag and etag == self.etag:
            return FeedResult(304)
        return FeedResult(200, self.feed_xml, self.etag, None)

    def resolve_channel(self, ref):
        self.calls.append(('resolve', ref))
        return CHANNEL

    def is_short(self, video_id):
        self.calls.append(('short', video_id))
        return video_id in self.shorts

    def video_meta(self, url):
        video_id = url.split('v=')[-1]
        self.calls.append(('meta', video_id))
        meta = self.metas.get(video_id, {})
        if meta == 'gone':
            raise Unavailable('video unavailable')
        if meta == 'error':
            raise NetError('yt-dlp failed')
        return {'title': 'T', 'channel': 'C', 'channel_id': CHANNEL, 'duration_s': 600,
                'live_status': 'not_live', 'upload_date': '20261020', **meta}

    def count(self, kind):
        return sum(1 for c in self.calls if c[0] == kind)
