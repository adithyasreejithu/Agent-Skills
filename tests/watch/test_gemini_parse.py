import unittest

import _path  # noqa: F401
from gemini import parse_timestamped_lines


class ParseTests(unittest.TestCase):
    def test_requested_format_ends_where_next_starts(self):
        segs = parse_timestamped_lines('[00:00.0] Hello there.\n[00:02.5] And again.', 10.0)
        self.assertEqual([(s['start'], s['end'], s['text']) for s in segs],
                         [(0.0, 2.5, 'Hello there.'), (2.5, 10.0, 'And again.')])

    def test_range_format_uses_the_stated_end(self):
        segs = parse_timestamped_lines('[00:00.040 --> 00:02.820] one\n[00:03.000 --> 00:04.500] two')
        self.assertEqual([(s['start'], s['end']) for s in segs], [(0.04, 2.82), (3.0, 4.5)])

    def test_bold_and_bullet_decorations(self):
        segs = parse_timestamped_lines('- **[01:00.1]** bold line')
        self.assertEqual(segs[0]['start'], 60.1)
        self.assertEqual(segs[0]['text'], 'bold line')

    def test_trailing_s_on_the_timestamp(self):
        segs = parse_timestamped_lines("[00:00.0s] Here's how.\n[00:02.4s] Next.")
        self.assertEqual([(s['start'], s['text']) for s in segs], [(0.0, "Here's how."), (2.4, 'Next.')])

    def test_hours(self):
        self.assertEqual(parse_timestamped_lines('[1:02:03.5] late')[0]['start'], 3723.5)

    def test_out_of_order_lines_are_sorted_not_fatal(self):
        segs = parse_timestamped_lines('[01:00.0] later\n[00:05.0] earlier', 70.0)
        self.assertEqual([s['text'] for s in segs], ['earlier', 'later'])

    def test_unparseable_text_gives_no_segments(self):
        segs = parse_timestamped_lines('Sure! Here is the transcript you asked for.')
        self.assertEqual(len(segs), 0)

    def test_empty_text_is_no_speech(self):
        self.assertTrue(parse_timestamped_lines('').no_speech)


if __name__ == '__main__':
    unittest.main()
