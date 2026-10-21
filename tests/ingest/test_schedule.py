import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import run
import schedule
from test_cli import cli


class ScheduleTests(unittest.TestCase):
    def script(self, **kw):
        args = dict(name='IngestVideos', at='07:00', project=Path('C:/proj'), python='C:/py/python.exe',
                    run_py=Path('C:/skill/run.py'))
        args.update(kw)
        return schedule.build_script(**args)

    def test_weekdays_only_no_overlap_catchup_and_time_limit(self):
        text = self.script()
        self.assertIn('-DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday', text)
        self.assertNotIn('Saturday', text)
        self.assertIn('-At 07:00', text)
        self.assertIn('-MultipleInstances IgnoreNew', text)
        self.assertIn('-StartWhenAvailable', text)
        self.assertIn('-ExecutionTimeLimit (New-TimeSpan -Hours 4)', text)
        self.assertIn('-LogonType Interactive', text)
        self.assertIn("-WorkingDirectory 'C:\\proj'", text.replace('C:/proj', 'C:\\proj') if '/' in text else text)
        self.assertIn('tick --log', text)

    def test_quotes_in_paths_are_escaped(self):
        text = self.script(project=Path("C:/it's here"))
        self.assertIn("it''s here", text)

    def test_bad_time_or_name_is_rejected(self):
        for bad in ('7:00', '25:00', '07:60', 'seven'):
            with self.assertRaises(ValueError):
                self.script(at=bad)
        with self.assertRaises(ValueError):
            self.script(name="x'; Remove-Item *")

    def test_install_without_yes_registers_nothing(self):
        called = []
        original = schedule.powershell
        schedule.powershell = lambda script: called.append(script)
        try:
            self.assertEqual(schedule.main(['install']), 1)
            self.assertEqual(called, [])
        finally:
            schedule.powershell = original


class LogFlagTests(unittest.TestCase):
    def test_tick_log_writes_run_log_and_keeps_console_quiet(self):
        home = Path(tempfile.mkdtemp()) / 'q'
        cli('--home', str(home), 'init')
        code, out, _ = cli('--home', str(home), 'tick', '--log')
        self.assertEqual(code, 0)
        self.assertEqual(out, '')
        logs = list((home / 'logs').glob('*/run.log'))
        self.assertEqual(len(logs), 1)
        text = logs[0].read_text(encoding='utf-8')
        self.assertIn('tick ===', text)
        self.assertIn('processed: 0 done', text)
        self.assertTrue(text.rstrip().endswith('exit 0'))


if __name__ == '__main__':
    unittest.main()
