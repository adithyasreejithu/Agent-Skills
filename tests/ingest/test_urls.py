import unittest

import _path  # noqa: F401
from urls import extract_video_id


class UrlTests(unittest.TestCase):
    def test_all_forms(self):
        vid = 'JKXovvYSh9U'
        for url in (
            f'https://www.youtube.com/watch?v={vid}',
            f'https://youtube.com/watch?v={vid}&t=93s&list=PLabc',
            f'https://m.youtube.com/watch?v={vid}',
            f'https://youtu.be/{vid}',
            f'https://youtu.be/{vid}?t=10',
            f'https://www.youtube.com/shorts/{vid}',
            f'https://www.youtube.com/live/{vid}?feature=share',
            f'https://www.youtube.com/embed/{vid}',
            f'youtube.com/watch?v={vid}',
            f'  https://youtu.be/{vid}  ',
        ):
            self.assertEqual(extract_video_id(url), vid, url)

    def test_ids_starting_with_underscore_or_dash(self):
        self.assertEqual(extract_video_id('https://youtu.be/_2kSZRoEVgg'), '_2kSZRoEVgg')
        self.assertEqual(extract_video_id('https://youtu.be/-abcdefghij'), '-abcdefghij')

    def test_rejects(self):
        for url in ('', 'hello world', 'https://example.com/watch?v=JKXovvYSh9U', 'https://youtu.be/short',
                    'https://www.youtube.com/@OptionsWithRyan', 'https://www.youtube.com/watch',
                    'https://www.instagram.com/reel/Cabc123defg/', 'JKXovvYSh9U'):
            self.assertIsNone(extract_video_id(url), url)


if __name__ == '__main__':
    unittest.main()
