import unittest

import _path
from feed import FeedError, parse_feed


class FeedTests(unittest.TestCase):
    def test_real_feed_fixture(self):
        entries = parse_feed(_path.FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(len(entries), 15)
        first = entries[0]
        self.assertEqual(first['video_id'], '4zPSPmVxhr0')
        self.assertEqual(first['channel_id'], 'UCQnIfbieTyf53CZBiyLAkjg')
        self.assertEqual(first['channel_name'], 'Options With Ryan')
        self.assertEqual(first['url'], 'https://www.youtube.com/watch?v=4zPSPmVxhr0')
        self.assertTrue(first['published_at'].startswith('2026-10-20'))
        self.assertIsInstance(first['views'], int)
        dates = [e['published_at'] for e in entries]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_not_xml(self):
        with self.assertRaises(FeedError):
            parse_feed('<html>nope')

    def test_wrong_root(self):
        with self.assertRaises(FeedError):
            parse_feed('<rss></rss>')

    def test_entry_without_video_id_is_dropped(self):
        xml = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>x</title></entry></feed>'
        self.assertEqual(parse_feed(xml), [])


if __name__ == '__main__':
    unittest.main()
