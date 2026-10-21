import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import run


def cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = run.main(list(args))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()) / 'my-queue'

    def test_init_creates_folders_and_starter_sources_without_clobbering(self):
        code, out, _ = cli('--home', str(self.home), 'init')
        self.assertEqual(code, 0)
        for name in ('pending', 'processing', 'failed', 'done', 'inbox', 'logs'):
            self.assertTrue((self.home / name).is_dir(), name)
        sources = self.home / 'sources.toml'
        self.assertIn('[defaults]', sources.read_text(encoding='utf-8'))
        sources.write_text('# mine\n', encoding='utf-8')
        cli('--home', str(self.home), 'init')
        self.assertEqual(sources.read_text(encoding='utf-8'), '# mine\n')

    def test_source_add_list_and_duplicate(self):
        cli('--home', str(self.home), 'init')
        self.assertEqual(cli('--home', str(self.home), 'source', 'add', 'OptionsWithRyan', '--name', 'Ryan',
                             '--priority', '70')[0], 0)
        code, out, _ = cli('--home', str(self.home), 'source', 'list')
        self.assertIn('p70', out)
        self.assertIn('@OptionsWithRyan', out)
        self.assertEqual(cli('--home', str(self.home), 'source', 'add', '@optionswithryan')[0], 1)

    def test_status_next_and_recover_on_empty_queue(self):
        cli('--home', str(self.home), 'init')
        code, out, _ = cli('--home', str(self.home), 'status', '--json')
        self.assertEqual(json.loads(out)['counts']['pending'], 0)
        self.assertIn('nothing pending', cli('--home', str(self.home), 'next')[1])
        self.assertIn('nothing stale', cli('--home', str(self.home), 'recover')[1])

    def test_bad_sources_file_gives_config_error_not_traceback(self):
        cli('--home', str(self.home), 'init')
        (self.home / 'sources.toml').write_text('[[source]]\nname = "x"\n', encoding='utf-8')
        code, _, err = cli('--home', str(self.home), 'source', 'list')
        self.assertEqual(code, 2)
        self.assertIn('config error', err)

    def test_poll_with_no_channels_is_harmless(self):
        cli('--home', str(self.home), 'init')
        code, out, _ = cli('--home', str(self.home), 'poll', '--dry-run')
        self.assertEqual(code, 0)
        self.assertIn('no channels configured', out)

    def test_list_and_queue_md_after_next(self):
        cli('--home', str(self.home), 'init')
        code, out, _ = cli('--home', str(self.home), 'list')
        self.assertIn('nothing pending', out)
        cli('--home', str(self.home), 'next')
        self.assertTrue((self.home / 'QUEUE.md').exists())
        self.assertEqual(cli('--home', str(self.home), 'list', '--skipped')[0], 0)

    def test_requeue_sends_done_and_failed_back_to_pending(self):
        cli('--home', str(self.home), 'init')
        from store import Store
        from config import resolve_paths
        store = Store(resolve_paths(str(self.home)))
        store.add_pending({'video_id': 'failed00000', 'url': 'u', 'title': 't', 'origin': 'rss', 'priority': 50,
                           'attempts': 3, 'last_error': 'x'})
        store.move('failed00000', 'pending', 'failed')
        (store.dirs['done'] / 'done0000000.json').write_text(json.dumps(
            {'video_id': 'done0000000', 'url': 'u', 'title': 'T', 'channel': 'C'}), encoding='utf-8')
        code, out, _ = cli('--home', str(self.home), 'requeue', 'failed00000', 'done0000000', 'nothere0000')
        self.assertEqual(code, 1)
        self.assertEqual(store.find('failed00000')[0], 'pending')
        self.assertEqual(store.find('failed00000')[1]['attempts'], 0)
        stage, item = store.find('done0000000')
        self.assertEqual((stage, item['channel_name']), ('pending', 'C'))

    def test_testing_flag_comes_from_settings(self):
        from config import resolve_paths
        self.assertFalse(resolve_paths(None, env={}, cwd=self.home, user_config=self.home / 'none').testing)
        on = resolve_paths(None, env={'INGEST_TESTING': 'yes'}, cwd=self.home, user_config=self.home / 'none')
        self.assertTrue(on.testing)
        self.assertEqual(on.labels, self.home / 'training' / 'labels')


if __name__ == '__main__':
    unittest.main()
