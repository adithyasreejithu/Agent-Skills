import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _path
from _fakes import CHANNEL, FakeNet, make_paths, make_source
from poll import poll
from store import Store

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
FEED = _path.FIXTURE.read_text(encoding='utf-8')
ALL_IDS = ['4zPSPmVxhr0', 'SLBmkUzyGtA', 'ik7Mong73Hg', 'hpUnLAXgOYQ', '667m_tyzrDo', '33Yqdsr_vcA', 'aT5AaRmohrs',
           'JKXovvYSh9U', 'ioSr_jyNKoo', 'EYfrlglrFyc', 'itg44KXGa2I', 'DVzBpptnr1M', '491Xm6_gO0Y', 't8tVP-_oMdA',
           'NQFjRtceW4w']


def no_sleep(_):
    return None


class PollTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.store = Store(make_paths(self.root))
        self.store.ensure()
        self.net = FakeNet(FEED)
        self.source = make_source()

    def run_poll(self, sources=None, now=NOW, **kw):
        return poll(self.store, sources or [self.source], self.net, now, sleep=no_sleep, **kw)

    def test_first_poll_skips_backlog_and_queues_nothing(self):
        report = self.run_poll()
        self.assertEqual(report.count('skipped'), 15)
        self.assertEqual(report.count('queued'), 0)
        self.assertEqual(self.store.counts()['pending'], 0)
        self.assertEqual(self.net.count('meta'), 0)          # no yt-dlp spend on backlog
        self.assertEqual(self.store.counts()['skipped'], 15)

    def test_backfill_queues_latest_n(self):
        report = self.run_poll(backfill=3)
        self.assertEqual(report.count('queued'), 3)
        self.assertEqual(report.count('skipped'), 12)
        pending = {i['video_id'] for i in self.store.pending_items(NOW)}
        self.assertEqual(pending, {'4zPSPmVxhr0', 'SLBmkUzyGtA', 'ik7Mong73Hg'})
        item = self.store.find('4zPSPmVxhr0')[1]
        self.assertEqual((item['origin'], item['priority'], item['channel_name']), ('rss', 50, 'Options With Ryan'))
        self.assertEqual(item['duration_s'], 600)

    def test_second_poll_queues_nothing_new(self):
        self.run_poll(backfill=3)
        before = self.store.counts()
        report = self.run_poll()
        self.assertEqual(report.count('queued') + report.count('skipped') + report.count('error'), 0)
        self.assertEqual(self.store.counts(), before)

    def test_new_video_after_first_poll_is_queued(self):
        self.run_poll()                                         # backlog skipped
        newer = FEED.replace('4zPSPmVxhr0', 'NEWVIDEO123', 2)   # pretend the top entry is a brand new id
        self.net.feed_xml, self.net.etag = newer, 'etag-2'
        report = self.run_poll()
        self.assertEqual([o.video_id for o in report.outcomes if o.result == 'queued'], ['NEWVIDEO123'])
        self.assertEqual(self.store.counts()['pending'], 1)

    def test_already_summarized_videos_are_never_queued(self):
        self.run_poll()
        notes = self.store.paths.notes
        notes.mkdir(parents=True, exist_ok=True)
        (notes / 'JKXovvYSh9U-will-the-qqq-rally-hold.md').write_text('x', encoding='utf-8')
        # fresh store state so every entry looks unseen except via the notes folder
        self.root2 = Path(tempfile.mkdtemp())
        store2 = Store(make_paths(self.root2))
        store2.paths.notes.mkdir(parents=True, exist_ok=True)
        (store2.paths.notes / 'JKXovvYSh9U-will-the-qqq-rally-hold.md').write_text('x', encoding='utf-8')
        (store2.paths.notes / 'aT5AaRmohrs-earnings-season-outlook.md').write_text('x', encoding='utf-8')
        store2.ensure()
        state = store2.load_state()
        state['channels'][CHANNEL] = {'first_polled': True}
        store2.save_state(state)
        report = poll(store2, [self.source], self.net, NOW, sleep=no_sleep)
        queued = {o.video_id for o in report.outcomes if o.result == 'queued'}
        self.assertEqual(len(queued), 13)
        self.assertNotIn('JKXovvYSh9U', queued)
        self.assertNotIn('aT5AaRmohrs', queued)

    def mark_polled(self):
        state = self.store.load_state()
        state['channels'][CHANNEL] = {'first_polled': True}
        self.store.save_state(state)

    def test_filters_shorts_duration_title_age_unavailable(self):
        self.mark_polled()
        self.net.shorts = {'4zPSPmVxhr0'}
        self.net.metas = {'SLBmkUzyGtA': {'duration_s': 90}, 'ik7Mong73Hg': {'duration_s': 9000},
                          'hpUnLAXgOYQ': 'gone', '667m_tyzrDo': {'duration_s': 600}}
        source = make_source(exclude_title='Credo', max_age_days=30)
        # entries older than 30 days from NOW would be 'too old'; fixture is all within ~4 weeks
        late = NOW + timedelta(days=10)
        report = poll(self.store, [source], self.net, late, sleep=no_sleep)
        reasons = {o.video_id: o.detail for o in report.outcomes if o.result == 'skipped'}
        self.assertEqual(reasons['4zPSPmVxhr0'], 'short')
        self.assertEqual(reasons['SLBmkUzyGtA'], 'too short')
        self.assertEqual(reasons['ik7Mong73Hg'], 'too long')
        self.assertEqual(reasons['hpUnLAXgOYQ'], 'unavailable')
        self.assertEqual(reasons['ioSr_jyNKoo'], 'title excluded')
        self.assertIn('too old', set(reasons.values()))
        self.assertNotIn('667m_tyzrDo', reasons)
        self.assertEqual(self.store.find('667m_tyzrDo')[0], 'pending')

    def test_include_title_regex_requires_match(self):
        self.mark_polled()
        source = make_source(include_title='wheel')
        report = self.run_poll([source])
        queued = [o.video_id for o in report.outcomes if o.result == 'queued']
        self.assertEqual(sorted(queued), ['SLBmkUzyGtA', 'ioSr_jyNKoo'])

    def test_metadata_error_is_retried_next_poll_not_recorded(self):
        self.mark_polled()
        self.net.metas = {v: 'error' for v in ALL_IDS}
        report = self.run_poll()
        self.assertEqual(report.count('error'), 15)
        self.assertEqual(self.store.counts()['skipped'], 0)
        self.net.metas = {}
        report = self.run_poll()
        self.assertEqual(report.count('queued'), 15)

    def test_live_then_released_after_airing_or_dropped_if_out_of_range(self):
        self.mark_polled()
        self.net.metas = {'4zPSPmVxhr0': {'live_status': 'is_upcoming', 'duration_s': None},
                          'SLBmkUzyGtA': {'live_status': 'is_upcoming', 'duration_s': None}}
        report = self.run_poll()
        self.assertEqual(report.count('deferred'), 2)
        claimed = {i['video_id'] for i in self.store.claim_next(None, NOW)}
        self.assertEqual(len(claimed), 13)
        self.assertTrue({'4zPSPmVxhr0', 'SLBmkUzyGtA'}.isdisjoint(claimed))   # deferred stay in pending
        later = NOW + timedelta(hours=7)
        self.net.metas = {'4zPSPmVxhr0': {'duration_s': 600}, 'SLBmkUzyGtA': {'duration_s': 30}}
        self.run_poll(now=later)
        self.assertEqual(self.store.find('4zPSPmVxhr0')[1]['not_before'], None)
        self.assertIsNone(self.store.find('SLBmkUzyGtA'))
        self.assertIn('SLBmkUzyGtA', self.store.skipped_ids())

    def test_304_not_modified_and_resolve_cached(self):
        source = make_source(channel_id=None)
        self.run_poll([source])
        self.assertEqual(self.net.count('resolve'), 1)
        report = self.run_poll([source])
        self.assertEqual(report.not_modified, 1)
        self.assertEqual(self.net.count('resolve'), 1)         # cached in state.json refs

    def test_feed_failure_counts_and_flags_after_three(self):
        self.net.feed_error = 'feed HTTP 500'
        for _ in range(3):
            report = self.run_poll()
        self.assertEqual(self.store.load_state()['channels'][CHANNEL]['fail_count'], 3)
        self.assertTrue(any('failing polls in a row' in w for w in report.warnings))
        self.net.feed_error = None
        self.run_poll()
        self.assertEqual(self.store.load_state()['channels'][CHANNEL]['fail_count'], 0)

    def test_dry_run_writes_nothing(self):
        self.mark_polled()
        before = sorted(p.name for p in self.root.rglob('*'))
        report = self.run_poll(dry_run=True)
        self.assertEqual(report.count('queued'), 15)
        self.assertEqual(sorted(p.name for p in self.root.rglob('*')), before)

    def test_only_and_disabled(self):
        other = make_source(ref='@Other', name='Other', channel_id=None)
        off = make_source(ref='@Off', name='Off', enabled=False)
        report = self.run_poll([self.source, other, off], only='options with ryan')
        self.assertEqual(report.polled, 1)

    def test_all_new_entries_warns_about_gap(self):
        self.mark_polled()
        self.net.metas = {v: {'duration_s': 600} for v in ALL_IDS}
        report = self.run_poll()
        self.assertTrue(any('all 15 feed entries are new' in w for w in report.warnings))


if __name__ == '__main__':
    unittest.main()
