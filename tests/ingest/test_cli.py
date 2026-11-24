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

    def test_a_run_that_finished_videos_writes_the_brief_not_a_digest(self):
        from types import SimpleNamespace
        from unittest import mock
        from process import ProcessReport
        cli('--home', str(self.home), 'init')
        calls = []

        def fake_brief(store, day, **kwargs):
            calls.append(day)
            return SimpleNamespace(path=Path(f'{day}.md'), generated='claude', videos=1,
                                   history_notes=1, attempts=1, usage={})

        with mock.patch.object(run, 'process_queue', lambda *a, **k: ProcessReport(done=['aaaaaaaaaa1'])), \
                mock.patch.object(run, 'write_brief', fake_brief):
            code, out, _ = cli('--home', str(self.home), 'process')
        self.assertEqual(code, 0)
        self.assertEqual(calls, [run.today()])
        self.assertIn(f'brief     {run.today()}.md  (claude)', out)
        self.assertNotIn('digest', out)

    def test_brief_on_a_day_with_no_videos_is_harmless(self):
        cli('--home', str(self.home), 'init')
        code, out, _ = cli('--home', str(self.home), 'brief', '--date', '2001-01-01')
        self.assertEqual((code, out.strip()), (0, 'no videos finished on 2001-01-01'))
        code, out, _ = cli('--home', str(self.home), 'brief', '--date', 'yesterday')
        self.assertEqual(code, 2)

    def test_analyze_with_nothing_to_do_and_render_only_are_harmless(self):
        import os
        from unittest import mock
        cli('--home', str(self.home), 'init')
        with mock.patch.dict(os.environ, {'INGEST_RESEARCH_DIR': str(self.home.parent / 'research')}):   # not the repo's
            code, out, _ = cli('--home', str(self.home), 'analyze')
            self.assertEqual((code, 'nothing to analyse' in out), (0, True))
            code, out, _ = cli('--home', str(self.home), 'analyze', '--render-only')
        self.assertEqual(code, 0)
        self.assertIn('rendered 2 file(s)', out)
        self.assertTrue((self.home.parent / 'research' / 'analysis' / 'methods.md').is_file())

    def test_a_run_that_finished_videos_analyses_them_without_failing_the_run(self):
        from unittest import mock
        from process import ProcessReport
        cli('--home', str(self.home), 'init')
        seen = []

        def boom(store, ids, **kwargs):
            seen.append(list(ids))
            raise RuntimeError('model down')

        with mock.patch.object(run, 'process_queue', lambda *a, **k: ProcessReport(done=['aaaaaaaaaa1'])),                 mock.patch.object(run, 'write_brief', lambda *a, **k: None),                 mock.patch.object(run.analysis, 'analyse_many', boom):
            code, out, _ = cli('--home', str(self.home), 'process')
        self.assertEqual((code, seen), (0, [['aaaaaaaaaa1']]))
        self.assertIn('analysis failed: RuntimeError: model down', out)

    def test_testing_flag_comes_from_settings(self):
        from config import resolve_paths
        self.assertFalse(resolve_paths(None, env={}, cwd=self.home, user_config=self.home / 'none').testing)
        on = resolve_paths(None, env={'INGEST_TESTING': 'yes'}, cwd=self.home, user_config=self.home / 'none')
        self.assertTrue(on.testing)
        self.assertEqual(on.labels, self.home / 'training' / 'labels')


if __name__ == '__main__':
    unittest.main()
