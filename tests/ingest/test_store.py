import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _path  # noqa: F401
from _fakes import make_paths
from store import LockHeld, Store, iso

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def item(vid, priority=50, origin='rss', published='2026-10-19T00:00:00Z', discovered=None, **extra):
    return {'video_id': vid, 'url': f'https://www.youtube.com/watch?v={vid}', 'title': vid, 'origin': origin,
            'priority': priority, 'published_at': published, 'discovered_at': discovered or iso(NOW),
            'attempts': 0, **extra}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.store = Store(make_paths(self.root))
        self.store.ensure()

    def test_manual_now_then_manual_then_rss_by_priority(self):
        for i in (item('rss_low_aaa', 50), item('rss_hi_aaaa', 80), item('manual_aaaa', 100, 'manual'),
                  item('now_aaaaaaa', 1000, 'manual')):
            self.store.add_pending(i)
        order = [i['video_id'] for i in self.store.pending_items(NOW)]
        self.assertEqual(order, ['now_aaaaaaa', 'manual_aaaa', 'rss_hi_aaaa', 'rss_low_aaa'])

    def test_same_priority_newest_published_first(self):
        self.store.add_pending(item('older_aaaaa', published='2026-10-01T00:00:00Z'))
        self.store.add_pending(item('newer_aaaaa', published='2026-10-18T00:00:00Z'))
        self.assertEqual([i['video_id'] for i in self.store.pending_items(NOW)], ['newer_aaaaa', 'older_aaaaa'])

    def test_aging_lets_old_low_priority_overtake_but_is_capped(self):
        old = iso(NOW - timedelta(days=30))
        self.store.add_pending(item('waiting_aaa', 40, discovered=old))     # 40 + capped 20 = 60
        self.store.add_pending(item('fresh_aaaaa', 55))
        self.assertEqual([i['video_id'] for i in self.store.pending_items(NOW)], ['waiting_aaa', 'fresh_aaaaa'])
        self.assertEqual(self.store.effective_priority(item('x', 40, discovered=old), NOW), 60)

    def test_claim_moves_files_and_respects_limit_but_not_for_manual(self):
        for n in range(4):
            self.store.add_pending(item(f'rss_{n}_aaaaa', 50))
        self.store.add_pending(item('manual_aaaa', 100, 'manual'))
        claimed = self.store.claim_next(2, NOW)
        ids = [c['video_id'] for c in claimed]
        self.assertEqual(len(ids), 3)                      # manual + 2 rss
        self.assertEqual(ids[0], 'manual_aaaa')
        self.assertEqual(self.store.counts()['pending'], 2)
        self.assertEqual(self.store.counts()['processing'], 3)
        self.assertIn('claimed_at', claimed[0])

    def test_unlimited_claim(self):
        for n in range(6):
            self.store.add_pending(item(f'rss_{n}_aaaaa'))
        self.assertEqual(len(self.store.claim_next(None, NOW)), 6)

    def test_deferred_items_are_not_claimed_until_due(self):
        self.store.add_pending(item('upcoming_aa', not_before=iso(NOW + timedelta(hours=3))))
        self.assertEqual(self.store.claim_next(None, NOW), [])
        self.assertEqual(len(self.store.claim_next(None, NOW + timedelta(hours=4))), 1)

    def test_stale_claims_are_released_fresh_ones_kept(self):
        self.store.add_pending(item('stale_aaaaa'))
        self.store.add_pending(item('fresh_aaaaa'))
        self.store.claim_next(None, NOW - timedelta(hours=3))
        fresh = self.store.item_path('processing', 'fresh_aaaaa')
        data = json.loads(fresh.read_text(encoding='utf-8'))
        data['claimed_at'] = iso(NOW - timedelta(minutes=10))
        fresh.write_text(json.dumps(data), encoding='utf-8')
        released = self.store.recover_stale(NOW)
        self.assertEqual(released, ['stale_aaaaa'])
        self.assertEqual(self.store.counts()['pending'], 1)
        self.assertEqual(self.store.counts()['processing'], 1)
        self.assertNotIn('claimed_at', self.store.find('stale_aaaaa')[1])

    def test_known_ids_cover_every_stage_skips_and_notes(self):
        self.store.add_pending(item('pending_aaaa'))
        self.store.move('pending_aaaa', 'pending', 'failed')
        self.store.record_skip('skipped_aaa', 'short', NOW, 't')
        self.store.paths.notes.mkdir(parents=True, exist_ok=True)
        (self.store.paths.notes / 'JKXovvYSh9U-will-the-qqq-rally-hold.md').write_text('x', encoding='utf-8')
        (self.store.paths.notes / '_2kSZRoEVgg-sold-30-year.md').write_text('x', encoding='utf-8')
        (self.store.paths.notes / 'options-trading-beginners-guide.md').write_text('x', encoding='utf-8')
        known = self.store.known_ids()
        self.assertEqual(known, {'pending_aaaa', 'skipped_aaa', 'JKXovvYSh9U', '_2kSZRoEVgg'})

    def test_lock_blocks_second_run_and_recovers_when_stale(self):
        self.store.acquire_lock(NOW)
        with self.assertRaises(LockHeld):
            Store(self.store.paths).acquire_lock(NOW + timedelta(minutes=5))
        # a dead run left the lock behind more than 2 h ago
        Store(self.store.paths).acquire_lock(NOW + timedelta(hours=3))
        self.store.release_lock()          # same pid as the taker, so this removes it
        self.assertFalse(self.store.lock_file.exists())

    def test_release_only_removes_own_lock(self):
        self.store.lock_file.write_text(json.dumps({'pid': -1, 'started': iso(NOW)}), encoding='utf-8')
        self.store.release_lock()
        self.assertTrue(self.store.lock_file.exists())
        self.store.lock_file.write_text(json.dumps({'pid': os.getpid(), 'started': iso(NOW)}), encoding='utf-8')
        self.store.release_lock()
        self.assertFalse(self.store.lock_file.exists())

    def test_queue_md_lists_pending_in_order_with_links_and_skips(self):
        self.store.add_pending(item('rss_low_aaa', 50, title='Low | pipe'))
        self.store.add_pending(item('manual_aaaa', 100, 'manual', duration_s=1200))
        self.store.record_skip('skipped_aaa', 'too old', NOW, 'Old one')
        text = self.store.render_queue_md(NOW)
        self.assertLess(text.index('manual_aaaa'), text.index('rss_low_aaa'))
        self.assertIn('| 20 min |', text)
        self.assertIn('Low / pipe', text)                       # pipes cannot break the table
        self.assertIn('| too old |', text)
        self.store.write_queue_md(NOW)
        self.assertTrue(self.store.queue_md.exists())


if __name__ == '__main__':
    unittest.main()
