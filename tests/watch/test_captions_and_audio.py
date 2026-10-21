import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import gemini
from download import select_caption
from transcribe import Segments


def track(*langs):
    return {lang: [{'ext': 'vtt', 'url': f'https://x/{lang}'}] for lang in langs}


class CaptionSelectionTests(unittest.TestCase):
    def test_requested_language_prefers_the_original_track_over_the_translated_one(self):
        info = {'extractor_key': 'Youtube', 'automatic_captions': track('ar-orig', 'ar', 'en-orig', 'en')}
        self.assertEqual(select_caption(info, 'en')['key'], 'en-orig')

    def test_plain_track_is_used_when_there_is_no_orig(self):
        info = {'extractor_key': 'Youtube', 'automatic_captions': track('en')}
        self.assertEqual(select_caption(info, 'en')['key'], 'en')

    def test_manual_captions_beat_automatic_ones(self):
        info = {'extractor_key': 'Youtube', 'subtitles': track('en'), 'automatic_captions': track('en-orig', 'en')}
        chosen = select_caption(info, 'en')
        self.assertEqual((chosen['kind'], chosen['key']), ('manual', 'en'))


@unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg is required to split audio')
class LongAudioTests(unittest.TestCase):
    def test_audio_is_chunked_and_stitched_into_source_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'long.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                            'anullsrc=r=16000:cl=mono', '-t', '700', '-b:a', '64k', str(audio)], check=True)
            calls = []

            def fake(path, key, *, model, duration=None, timeout=600.0):
                calls.append(path.name)
                out = Segments([{'start': 1.0, 'end': 2.0, 'text': path.name}])
                out.total_tokens = 100
                return out

            real = gemini.transcribe_audio
            gemini.transcribe_audio = fake
            try:
                result = gemini.transcribe_long_audio(audio, 'k', model='m', duration=700.0,
                                                      chunk_dir=Path(tmp) / 'chunks', chunk_seconds=300.0)
            finally:
                gemini.transcribe_audio = real
            self.assertGreater(len(calls), 1)
            starts = [s['start'] for s in result]
            self.assertEqual(starts, sorted(starts))
            self.assertGreater(starts[-1], 300)  # later chunks were shifted by their offset
            self.assertEqual(result.total_tokens, 100 * len(calls))

    def test_short_audio_is_sent_in_one_piece(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / 'short.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                            'anullsrc=r=16000:cl=mono', '-t', '60', '-b:a', '64k', str(audio)], check=True)
            calls = []
            real = gemini.transcribe_audio
            gemini.transcribe_audio = lambda path, key, **kw: calls.append(path.name) or Segments()
            try:
                gemini.transcribe_long_audio(audio, 'k', model='m', duration=60.0, chunk_dir=Path(tmp) / 'c')
            finally:
                gemini.transcribe_audio = real
            self.assertEqual(calls, ['short.mp3'])


if __name__ == '__main__':
    unittest.main()
