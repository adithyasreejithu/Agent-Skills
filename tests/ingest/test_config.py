import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
from config import ConfigError, load_sources, resolve_paths


class PathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.user_file = self.tmp / 'no-user-config.env'

    def paths(self, env=None, project=None, user=None, cli=None):
        if project is not None:
            (self.tmp / 'ingest.env').write_text(project, encoding='utf-8')
        if user is not None:
            self.user_file.write_text(user, encoding='utf-8')
        return resolve_paths(cli, env or {}, self.tmp, self.user_file)

    def test_zero_config_defaults(self):
        p = self.paths()
        self.assertEqual(p.home, self.tmp / 'queue')
        self.assertEqual(p.notes, self.tmp / 'queue' / 'notes')
        self.assertEqual(p.digests, self.tmp / 'queue' / 'notes' / '_digests')
        self.assertEqual(p.raw, self.tmp / 'queue' / 'raw')
        self.assertEqual(p.state, p.home)
        self.assertEqual(p.sources_file, p.home / 'sources.toml')

    def test_precedence_env_project_user(self):
        user = 'INGEST_NOTES_DIR=from-user\nINGEST_RAW_DIR=raw-user\nINGEST_LOGS_DIR=logs-user\n'
        project = 'INGEST_NOTES_DIR=from-project\nINGEST_RAW_DIR=raw-project\n'
        env = {'INGEST_NOTES_DIR': 'from-env'}
        p = self.paths(env=env, project=project, user=user)
        self.assertEqual(p.notes, self.tmp / 'from-env')       # env beats project and user
        self.assertEqual(p.raw, self.tmp / 'raw-project')      # project beats user
        self.assertEqual(p.logs, self.tmp / 'logs-user')       # user used when nothing else is set

    def test_cli_home_beats_everything(self):
        p = self.paths(env={'INGEST_HOME': 'env-home'}, project='INGEST_HOME=proj-home', cli='cli-home')
        self.assertEqual(p.home, self.tmp / 'cli-home')

    def test_absolute_paths_kept_and_digests_follow_notes(self):
        target = (self.tmp / 'elsewhere').resolve()
        p = self.paths(env={'INGEST_NOTES_DIR': str(target)})
        self.assertEqual(p.notes, target)
        self.assertEqual(p.digests, target / '_digests')

    def test_windows_style_value_not_mangled(self):
        p = self.paths(project='INGEST_RAW_DIR=D:\\data\\raw\n')
        self.assertTrue(str(p.raw).lower().startswith('d:'))


class SourceTests(unittest.TestCase):
    def load(self, text):
        path = Path(tempfile.mkdtemp()) / 'sources.toml'
        path.write_text(text, encoding='utf-8')
        return load_sources(path)

    def test_missing_file_is_zero_config(self):
        d, sources = load_sources(Path(tempfile.mkdtemp()) / 'nope.toml')
        self.assertEqual(sources, [])
        self.assertTrue(d.skip_shorts)

    def test_defaults_and_overrides(self):
        d, sources = self.load(
            '[defaults]\nmin_duration_s = 300\n'
            '[[source]]\nhandle = "@A"\nname = "A"\n'
            '[[source]]\nchannel_id = "UCQnIfbieTyf53CZBiyLAkjg"\npriority = 80\nmax_duration_s = 7200\n'
            'exclude_title = "giveaway"\nenabled = false\n')
        a, b = sources
        self.assertEqual((a.min_duration_s, a.priority, a.max_duration_s), (300, 50, 5400))
        self.assertEqual((b.priority, b.max_duration_s, b.enabled), (80, 7200, False))
        self.assertEqual(b.channel_id, 'UCQnIfbieTyf53CZBiyLAkjg')
        self.assertIsNone(a.channel_id)

    def test_errors_are_clear(self):
        for text in ('[[source]]\nname = "x"', '[[source]]\nhandle = "@A"\npriority = "high"',
                     '[[source]]\nhandle = "@A"\ninclude_title = "("',
                     '[[source]]\nhandle = "@A"\n[[source]]\nhandle = "@a"', 'not toml ['):
            with self.assertRaises(ConfigError, msg=text):
                self.load(text)


if __name__ == '__main__':
    unittest.main()
