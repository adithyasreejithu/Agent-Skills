import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import watch

YT = 'https://www.youtube.com/watch?v=JKXovvYSh9U'
REEL = 'https://www.instagram.com/reel/DcclCGZhlo2/'


class RoutingTests(unittest.TestCase):
    def test_youtube_never_uploads_automatically(self):
        self.assertEqual(watch.choose_backend(YT, 'auto', True), 'none')
        self.assertEqual(watch.choose_backend('https://youtu.be/JKXovvYSh9U', 'auto', True), 'none')

    def test_reel_and_local_file_use_gemini_audio_when_a_key_exists(self):
        self.assertEqual(watch.choose_backend(REEL, 'auto', True), 'gemini')
        self.assertEqual(watch.choose_backend('C:/videos/clip.mp4', 'auto', True), 'gemini')

    def test_without_a_key_other_sources_keep_the_old_auto_behaviour(self):
        self.assertEqual(watch.choose_backend(REEL, 'auto', False), 'auto')

    def test_an_explicit_backend_always_wins(self):
        self.assertEqual(watch.choose_backend(YT, 'gemini', True), 'gemini')
        self.assertEqual(watch.choose_backend(REEL, 'groq', True), 'groq')
        self.assertEqual(watch.choose_backend(REEL, 'none', True), 'none')


class RunLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_file, self.old_run = watch.LOG_FILE, watch.RUN
        watch.LOG_FILE = Path(self.tmp.name) / 'logs' / 'watch-log.jsonl'
        watch.RUN = {'events': []}
        self.addCleanup(lambda: (setattr(watch, 'LOG_FILE', self.old_file), setattr(watch, 'RUN', self.old_run)))

    def test_one_json_line_per_run_with_events(self):
        watch.RUN.update(source=REEL, engine='local')
        watch.log_event('transcription_failed', 'gemini: HTTP 503', 'error')
        watch.write_run_log(0)
        watch.RUN = {'events': []}
        watch.write_run_log(1)
        lines = watch.LOG_FILE.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first['exit_code'], 0)
        self.assertEqual(first['events'][0]['kind'], 'transcription_failed')
        self.assertIn('ts', first)

    def test_a_logging_failure_never_breaks_the_run(self):
        watch.LOG_FILE = Path(self.tmp.name) / 'a-file'
        watch.LOG_FILE.write_text('x')
        watch.LOG_FILE = watch.LOG_FILE / 'child' / 'log.jsonl'  # parent is a file, so the write must fail
        watch.write_run_log(0)  # must not raise


if __name__ == '__main__':
    unittest.main()
