import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import _path  # noqa: F401
from _fakes import FakeNet, make_paths
from inbox import add_manual, consume_inbox
from store import Store

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
URL = 'https://youtu.be/JKXovvYSh9U'


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.store = Store(make_paths(self.root))
        self.store.ensure()
        self.net = FakeNet()

    def test_add_queues_manual_priority(self):
        status, _, vid = add_manual(self.store, self.net, URL, NOW)
        self.assertEqual((status, vid), ('queued', 'JKXovvYSh9U'))
        item = self.store.find(vid)[1]
        self.assertEqual((item['origin'], item['priority']), ('manual', 100))

    def test_now_flag_and_explicit_priority(self):
        add_manual(self.store, self.net, URL, NOW, now_flag=True)
        self.assertEqual(self.store.find('JKXovvYSh9U')[1]['priority'], 1000)
        add_manual(self.store, self.net, 'https://youtu.be/aaaaaaaaaaa', NOW, priority=70)
        self.assertEqual(self.store.find('aaaaaaaaaaa')[1]['priority'], 70)

    def test_manual_bypasses_filters_even_for_long_or_short_videos(self):
        self.net.metas = {'JKXovvYSh9U': {'duration_s': 20}}
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'queued')
        self.assertEqual(self.net.count('short'), 0)

    def test_upgrades_a_queued_rss_item_and_requeues_failed(self):
        self.store.add_pending({'video_id': 'JKXovvYSh9U', 'origin': 'rss', 'priority': 50, 'url': URL,
                                'discovered_at': '2026-10-19T00:00:00Z', 'attempts': 0})
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'updated')
        self.assertEqual(self.store.find('JKXovvYSh9U')[1]['origin'], 'manual')
        self.store.move('JKXovvYSh9U', 'pending', 'failed')
        item = self.store.find('JKXovvYSh9U')[1]
        item.update(attempts=3, error='boom')
        self.store.remove('failed', 'JKXovvYSh9U')
        self.store.dirs['failed'].joinpath('JKXovvYSh9U.json').write_text(
            '{"video_id": "JKXovvYSh9U", "attempts": 3, "error": "boom", "origin": "rss", "priority": 50}', encoding='utf-8')
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'requeued')
        found = self.store.find('JKXovvYSh9U')
        self.assertEqual((found[0], found[1]['attempts']), ('pending', 0))
        self.assertNotIn('error', found[1])

    def test_done_or_noted_requires_force_and_processing_is_left_alone(self):
        self.store.paths.notes.mkdir(parents=True, exist_ok=True)
        (self.store.paths.notes / 'JKXovvYSh9U-x.md').write_text('x', encoding='utf-8')
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'exists')
        self.assertEqual(add_manual(self.store, self.net, URL, NOW, force=True)[0], 'queued')
        self.store.move('JKXovvYSh9U', 'pending', 'processing')
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'in-progress')

    def test_rejects_non_youtube_and_unavailable(self):
        self.assertEqual(add_manual(self.store, self.net, 'https://www.instagram.com/reel/abc/', NOW)[0], 'rejected')
        self.net.metas = {'JKXovvYSh9U': 'gone'}
        self.assertEqual(add_manual(self.store, self.net, URL, NOW)[0], 'rejected')

    def test_metadata_failure_still_queues(self):
        self.net.metas = {'JKXovvYSh9U': 'error'}
        status, message, _ = add_manual(self.store, self.net, URL, NOW)
        self.assertEqual(status, 'queued')
        self.assertIn('metadata lookup failed', message)

    def test_inbox_file_is_consumed_archived_and_bad_lines_kept(self):
        (self.store.inbox / 'links.txt').write_text(
            '# my picks\n\nhttps://youtu.be/JKXovvYSh9U\nnot a url\nhttps://youtu.be/aaaaaaaaaaa\n', encoding='utf-8')
        results = consume_inbox(self.store, self.net, NOW)
        self.assertEqual([r[0] for r in results], ['queued', 'rejected', 'queued'])
        self.assertEqual(self.store.counts()['pending'], 2)
        self.assertFalse((self.store.inbox / 'links.txt').exists())
        self.assertEqual(len(list((self.store.inbox / 'done').glob('links-*.txt'))), 1)
        self.assertIn('not a url', (self.store.inbox / 'rejected.txt').read_text(encoding='utf-8'))
        self.assertEqual(consume_inbox(self.store, self.net, NOW), [])

    def test_inbox_dry_run_changes_nothing(self):
        (self.store.inbox / 'links.txt').write_text(URL + '\n', encoding='utf-8')
        results = consume_inbox(self.store, self.net, NOW, dry_run=True)
        self.assertEqual(results[0][0], 'would-add')
        self.assertTrue((self.store.inbox / 'links.txt').exists())
        self.assertEqual(self.store.counts()['pending'], 0)


if __name__ == '__main__':
    unittest.main()
