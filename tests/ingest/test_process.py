import dataclasses
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import _path  # noqa: F401
from _fakes import make_paths
from note import find_note, label_problems, summarize, validate
from process import RunResult, build_prompt, complete, fail, process_queue, write_digest
from store import Store, iso

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
VID = 'abcdefghijk'

GOOD = f"""---
video_id: {VID}
channel: Options With Ryan
title: Test video
published: 2026-10-19
ingested: 2026-10-20
source: https://www.youtube.com/watch?v={VID}
evidence: captions+frames
tickers: [AMAT, CRDO]
stance: bullish
---

# Test video

- Video: https://www.youtube.com/watch?v={VID}

## Market view
{'The market is at highs and breadth is narrow. ' * 8}

## Positions and plans
| Ticker | Plan |
|---|---|
| AMAT | cash-secured puts at 500 |
"""


def item(vid=VID, **extra):
    base = {'video_id': vid, 'url': f'https://www.youtube.com/watch?v={vid}', 'title': 'Test video',
            'channel_name': 'Options With Ryan', 'origin': 'rss', 'priority': 50, 'published_at': '2026-10-19T00:00:00Z',
            'discovered_at': iso(NOW), 'attempts': 0}
    return {**base, **extra}


class NoteTests(unittest.TestCase):
    def test_good_note_passes_and_summarizes(self):
        self.assertEqual(validate(GOOD, VID, f'{VID}-test-video.md'), [])
        self.assertEqual(summarize(GOOD), {'tickers': ['AMAT', 'CRDO'], 'stance': 'bullish', 'evidence': 'captions+frames'})

    def test_each_contract_break_is_reported(self):
        self.assertIn('missing frontmatter', validate('# Title\n' + 'x' * 500, VID)[0])
        no_stance_ok = GOOD.replace('stance: bullish', 'stance: moon')
        self.assertTrue(any('stance' in p for p in validate(no_stance_ok, VID)))
        self.assertTrue(any('does not match' in p for p in validate(GOOD, 'zzzzzzzzzzz')))
        self.assertTrue(any('Positions and plans' in p for p in validate(GOOD.replace('## Positions and plans', '## Stuff'), VID)))
        self.assertTrue(any('filename' in p for p in validate(GOOD, VID, 'wrong-name.md')))
        self.assertTrue(any('evidence' in p for p in validate(GOOD.replace('captions+frames', 'vibes'), VID)))
        self.assertTrue(any('channel' in p for p in validate(GOOD.replace('channel: Options With Ryan\n', ''), VID)))

    def test_empty_body_is_rejected(self):
        short = GOOD.split('## Market view')[0] + '## Market view\nx\n## Positions and plans\ny\n'
        self.assertTrue(any('under 400' in p for p in validate(short, VID)))


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.paths = make_paths(self.root)
        self.store = Store(self.paths)
        self.store.ensure()
        self.paths.notes.mkdir(parents=True, exist_ok=True)
        self.template = 'Do {video_id} at {url} into {notes_dir} {unknown_brace}'

    def writer(self, text=GOOD, code=0):
        """A fake `claude -p` that writes the note for whichever video it is given."""
        def run(it, prompt, log):
            self.last_prompt = prompt
            vid = it['video_id']
            (self.paths.notes / f'{vid}-test.md').write_text(text.replace(VID, vid), encoding='utf-8')
            return RunResult(code, 'RESULT: ok')
        return run

    def test_prompt_fills_known_placeholders_and_leaves_other_braces(self):
        text = build_prompt(self.template, item(), self.paths)
        self.assertIn(f'Do {VID} at https://www.youtube.com/watch?v={VID}', text)
        self.assertIn('{unknown_brace}', text)

    def test_success_writes_manifest_and_clears_processing(self):
        self.store.add_pending(item())
        report = process_queue(self.store, lambda: NOW, runner=self.writer(), template=self.template)
        self.assertEqual(report.done, [VID])
        counts = self.store.counts()
        self.assertEqual((counts['pending'], counts['processing'], counts['done']), (0, 0, 1))
        manifest = json.loads(self.store.item_path('done', VID).read_text(encoding='utf-8'))
        self.assertEqual(manifest['training_status'], 'new')
        self.assertEqual(manifest['tickers'], ['AMAT', 'CRDO'])
        self.assertTrue(manifest['note'].endswith(f'{VID}-test.md'))
        self.assertTrue((self.paths.logs / '2026-10-20' / f'{VID}.log').exists())

    def test_no_note_is_a_retry_held_for_next_run_then_fails_on_third(self):
        self.store.add_pending(item())
        silent = lambda it, prompt, log: RunResult(3, 'ACTION NEEDED: no captions')
        report = process_queue(self.store, lambda: NOW, runner=silent, template=self.template)
        self.assertEqual([v for v, _ in report.retried], [VID])
        self.assertIn('ACTION NEEDED', report.retried[0][1])
        held = self.store.find(VID)
        self.assertEqual(held[0], 'pending')
        self.assertEqual(held[1]['attempts'], 1)
        # not due again within the same run
        self.assertEqual(process_queue(self.store, lambda: NOW, runner=silent, template=self.template).retried, [])
        for _ in range(2):
            stage, it = self.store.find(VID)
            it.pop('not_before', None)
            self.store.add_pending(it)
            report = process_queue(self.store, lambda: NOW, runner=silent, template=self.template)
        self.assertEqual([v for v, _ in report.failed], [VID])
        self.assertEqual(self.store.find(VID)[0], 'failed')
        self.assertEqual(self.store.find(VID)[1]['attempts'], 3)

    def test_note_that_breaks_the_contract_is_not_done(self):
        self.store.add_pending(item())
        report = process_queue(self.store, lambda: NOW, runner=self.writer(GOOD.replace('stance: bullish', 'stance: moon')),
                               template=self.template)
        self.assertEqual(report.done, [])
        self.assertIn('stance', report.retried[0][1])

    def test_stale_old_note_does_not_count_as_new_work(self):
        old = self.paths.notes / f'{VID}-old.md'
        old.write_text(GOOD, encoding='utf-8')
        import os
        os.utime(old, (1, 1))
        self.store.add_pending(item())
        report = process_queue(self.store, lambda: NOW, runner=lambda i, p, l: RunResult(0, 'RESULT: failed x'),
                               template=self.template)
        self.assertEqual(report.done, [])

    def test_limit_and_budget_and_order(self):
        for n, vid in enumerate(('aaaaaaaaaa1', 'aaaaaaaaaa2', 'aaaaaaaaaa3')):
            self.store.add_pending(item(vid, published_at=f'2026-10-1{n}T00:00:00Z'))
        seen = []

        def run(it, prompt, log):
            seen.append(it['video_id'])
            return self.writer()(it, prompt, log)

        report = process_queue(self.store, lambda: NOW, runner=run, limit=2, template=self.template)
        self.assertEqual(seen, ['aaaaaaaaaa3', 'aaaaaaaaaa2'])        # newest first at equal priority
        self.assertIn('limit', report.stopped)
        ticks = iter(range(0, 10_000, 4000))                           # each clock() call advances ~67 min
        report = process_queue(self.store, lambda: NOW, runner=self.writer(), budget_min=60,
                               template=self.template, clock=lambda: next(ticks))
        self.assertIn('budget', report.stopped)

    def test_manual_now_item_runs_first(self):
        self.store.add_pending(item('aaaaaaaaaa1'))
        self.store.add_pending(item('mmmmmmmmmm1', priority=1000, origin='manual'))
        seen = []
        process_queue(self.store, lambda: NOW, runner=lambda i, p, l: (seen.append(i['video_id']), RunResult(1))[1],
                      limit=1, template=self.template)
        self.assertEqual(seen, ['mmmmmmmmmm1'])

    def test_only_targets_one_queued_video(self):
        self.store.add_pending(item('aaaaaaaaaa1'))
        self.store.add_pending(item('aaaaaaaaaa2'))
        report = process_queue(self.store, lambda: NOW, runner=self.writer(), only='aaaaaaaaaa1', template=self.template)
        self.assertEqual(report.done, ['aaaaaaaaaa1'])
        self.assertEqual(self.store.find('aaaaaaaaaa2')[0], 'pending')

    def test_rate_limit_stops_run_and_costs_no_attempt(self):
        self.store.add_pending(item('aaaaaaaaaa1'))
        self.store.add_pending(item('aaaaaaaaaa2'))
        calls = []

        def limited(it, prompt, log):
            calls.append(it['video_id'])
            return RunResult(0, 'RESULT: failed captions: HTTP Error 429: Too Many Requests')

        report = process_queue(self.store, lambda: NOW, runner=limited, template=self.template)
        self.assertEqual(len(calls), 1)
        self.assertTrue(report.rate_limited)
        stage, kept = self.store.find(calls[0])
        self.assertEqual((stage, kept['attempts']), ('pending', 0))
        self.assertEqual(self.store.counts()['processing'], 0)

    def test_watch_result_json_flags_rate_limit_and_fills_manifest(self):
        self.store.add_pending(item('aaaaaaaaaa1'))
        raw = self.paths.raw / 'aaaaaaaaaa1'
        raw.mkdir(parents=True)

        def limited(it, prompt, log):
            (raw / 'result.json').write_text(json.dumps({'caption_status': 'fetch_failed'}), encoding='utf-8')
            return RunResult(0, 'RESULT: failed captions unavailable')

        report = process_queue(self.store, lambda: NOW, runner=limited, template=self.template)
        self.assertTrue(report.rate_limited)
        self.assertEqual(self.store.find('aaaaaaaaaa1')[1]['attempts'], 0)

        def fine(it, prompt, log):
            (raw / 'result.json').write_text(json.dumps({'caption_status': 'available', 'engine': 'local',
                                                         'transcript_kind': 'captions', 'event_kinds': []}), encoding='utf-8')
            return self.writer()(it, prompt, log)

        report = process_queue(self.store, lambda: NOW, runner=fine, template=self.template)
        self.assertEqual(report.done, ['aaaaaaaaaa1'])
        manifest = json.loads(self.store.item_path('done', 'aaaaaaaaaa1').read_text(encoding='utf-8'))
        self.assertEqual((manifest['watch_engine'], manifest['transcript_kind']), ('local', 'captions'))
        self.assertEqual(manifest['raw_dir'], raw.as_posix())

    def test_stale_result_json_from_an_earlier_run_is_ignored(self):
        import os
        self.store.add_pending(item('aaaaaaaaaa1'))
        raw = self.paths.raw / 'aaaaaaaaaa1'
        raw.mkdir(parents=True)
        old = raw / 'result.json'
        old.write_text(json.dumps({'caption_status': 'fetch_failed'}), encoding='utf-8')
        os.utime(old, (1, 1))
        report = process_queue(self.store, lambda: NOW, runner=lambda i, p, l: RunResult(0, 'RESULT: failed x'),
                               template=self.template)
        self.assertFalse(report.rate_limited)
        self.assertEqual(len(report.retried), 1)

    def test_digest_groups_by_channel_and_appends_same_day(self):
        self.store.add_pending(item())
        process_queue(self.store, lambda: NOW, runner=self.writer(), template=self.template)
        path = write_digest(self.store, [VID], NOW)
        text = path.read_text(encoding='utf-8')
        self.assertIn('Options With Ryan', text)
        self.assertIn('AMAT, CRDO', text)
        rel = Path(os.path.relpath(self.paths.notes / f'{VID}-test.md', self.paths.digests)).as_posix()
        self.assertIn(f'({rel})', text)
        write_digest(self.store, [VID], NOW)                          # redone video: one line, not two
        self.assertEqual(path.read_text(encoding='utf-8').count(VID), 1)
        self.assertIsNone(write_digest(self.store, ['nothere0000'], NOW))
        self.assertEqual(find_note(self.paths.notes, VID).name, f'{VID}-test.md')


class TestingModeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.labels = self.root / 'training' / 'labels'
        self.labels.mkdir(parents=True)
        self.paths = dataclasses.replace(make_paths(self.root), testing=True, labels=self.labels)
        self.store = Store(self.paths)
        self.store.ensure()
        self.paths.notes.mkdir(parents=True, exist_ok=True)

    def write_labels(self, verdict='useful', control='blank'):
        (self.labels / f'{VID}.json').write_text(json.dumps({
            'cues': [{'cue_id': 'c01', 'offsets': {'+0': verdict, '+2': verdict}}],
            'control': [{'t': 0.0, 'verdict': control}]}), encoding='utf-8')

    def run_one(self, label_writer=None):
        self.store.add_pending(item())

        def runner(it, prompt, log):
            (self.paths.notes / f'{VID}-test.md').write_text(GOOD, encoding='utf-8')
            if label_writer:
                label_writer()
            return RunResult(0, 'RESULT: ok')

        return process_queue(self.store, lambda: NOW, runner=runner, template='x')

    def test_note_without_labels_is_not_done(self):
        report = self.run_one()
        self.assertEqual(report.done, [])
        self.assertIn('testing run incomplete', report.retried[0][1])
        self.assertIn('no label file', report.retried[0][1])

    def test_unlabeled_skeleton_is_not_done(self):
        report = self.run_one(lambda: self.write_labels(verdict=None, control=None))
        self.assertEqual(report.done, [])
        self.assertIn('unlabeled', report.retried[0][1])

    def test_labeled_run_is_done_and_marked_labeled(self):
        report = self.run_one(self.write_labels)
        self.assertEqual(report.done, [VID])
        manifest = json.loads(self.store.item_path('done', VID).read_text(encoding='utf-8'))
        self.assertEqual(manifest['training_status'], 'labeled')

    def test_label_problems_directly(self):
        self.assertTrue(label_problems(self.labels, 'nothere0000'))
        self.write_labels()
        self.assertEqual(label_problems(self.labels, VID), [])

    def test_testing_prompt_is_used_and_carries_label_paths(self):
        from process import prompt_template
        text = build_prompt(prompt_template(self.paths, env={}), item(), self.paths)
        self.assertIn('--testing', text)
        self.assertIn(f'{self.labels.parent.as_posix()}/specs/{VID}.json', text)
        self.assertNotIn('{labels_dir}', text)
        self.assertNotIn('{specs_dir}', text)


if __name__ == '__main__':
    unittest.main()
