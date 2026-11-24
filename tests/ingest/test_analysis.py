import json
import tempfile
import unittest
from pathlib import Path

import _path  # noqa: F401
import analysis
from _fakes import make_paths
from process import RunResult
from store import Store, write_json

VID = 'aaaaaaaaaa1'


def obs(video_id=VID, method=None, steps=None, **extra):
    method = method or {'method_id': None, 'new_method': {'name': 'Technical read on a chart', 'domain': 'stocks',
                                                          'description': 'Read a price chart with indicators.'}}
    steps = steps if steps is not None else [
        {'step_id': None, 'new_step': {'title': 'Open the chart', 'does': 'Open a chart.', 'why': 'See price.', 'after': None},
         'at': '02:15', 'does': 'Opens AMD on TradingView', 'why': 'check trend', 'data': ['AMD daily'],
         'tools': ['tradingview'], 'indicators': ['RSI'], 'conclusion': 'uptrend', 'tag': 'visual'}]
    return {'video_id': video_id, 'methods': [{**method, 'steps': steps, 'rules': [{'text': 'Avoid RSI > 80', 'tag': 'explicit'}]}],
            'tools': [{'name': 'tradingview', 'kind': 'website', 'url': 'tradingview.com', 'used_for': 'charting'}],
            'indicators': [{'name': 'RSI', 'measures': 'momentum', 'how_used': 'overbought check', 'platform': 'TradingView'}],
            **extra}


def second_video(video_id='bbbbbbbbbb2'):
    """Same method, an existing step plus one new step placed after it, TradingView spelled differently."""
    return obs(video_id, method={'method_id': 'technical-read-on-a-chart', 'new_method': None}, steps=[
        {'step_id': 'open-the-chart', 'new_step': None, 'at': '1:00', 'does': 'Opens MU', 'why': 'trend',
         'tools': ['TradingView'], 'indicators': [], 'tag': 'explicit'},
        {'step_id': None, 'new_step': {'title': 'Check volume', 'does': 'Look at volume.', 'why': 'Confirm moves.',
                                       'after': 'open-the-chart'},
         'at': '1:30', 'does': 'Reads volume bars', 'why': 'confirm', 'tools': ['Trading View'],
         'indicators': ['Volume'], 'tag': 'inference'}])


class AnalysisBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.paths = make_paths(self.tmp)
        self.store = Store(self.paths)
        self.store.ensure()
        self.lay = analysis.layout(self.paths)

    def manifest(self, vid=VID, **extra):
        m = {'video_id': vid, 'title': f'Title {vid}', 'channel': 'Chan', 'url': f'https://www.youtube.com/watch?v={vid}',
             'published_at': '2026-11-01T00:00:00+00:00', **extra}
        write_json(self.store.item_path('done', vid), m)
        raw = self.paths.raw / vid
        raw.mkdir(parents=True, exist_ok=True)
        (raw / 'transcript.txt').write_text('[00:01] hello', encoding='utf-8')
        return m

    def run_one(self, payload, vid=VID):
        m = self.manifest(vid)

        def runner(item, prompt, log):
            self.lay.inbox.mkdir(parents=True, exist_ok=True)
            (self.lay.inbox / f'{vid}.json').write_text(json.dumps(payload), encoding='utf-8')
            return RunResult(0, 'RESULT: ok')
        return analysis.run_analysis(self.store, m, runner=runner)


class ValidationTests(AnalysisBase):
    def check(self, o, registry=None):
        return analysis.validate_observation(o, registry or {'methods': {}}, VID)

    def test_good_observation_has_no_problems(self):
        self.assertEqual(self.check(obs()), [])

    def test_rejects_bad_tag_missing_time_and_wrong_id(self):
        bad = obs(video_id='zzzzzzzzzzz')
        step = bad['methods'][0]['steps'][0]
        step['tag'] = 'guess'
        step['at'] = 'soon'
        text = ' | '.join(self.check(bad))
        self.assertIn('video_id must be', text)
        self.assertIn('"tag" must be one of', text)
        self.assertIn('timestamp', text)

    def test_unknown_method_and_step_ids_are_rejected(self):
        self.assertIn('not in the registry', ' '.join(self.check(second_video(VID))))
        analysis.merge(self.lay, obs(), {})
        o = second_video(VID)
        o['methods'][0]['steps'][0]['step_id'] = 'nope'
        self.assertIn('not a step of this method', ' '.join(self.check(o, analysis.load_registry(self.lay))))

    def test_method_needs_exactly_one_of_id_or_new(self):
        both = obs(method={'method_id': 'x', 'new_method': {'name': 'a', 'domain': 'stocks', 'description': 'b'}})
        self.assertIn('exactly one', ' '.join(self.check(both)))

    def test_new_method_needs_a_domain_and_a_short_name(self):
        no_domain = obs(method={'method_id': None, 'new_method': {'name': 'A', 'description': 'b'}})
        self.assertIn('needs "domain"', ' '.join(self.check(no_domain)))
        long = obs(method={'method_id': None, 'new_method': {'name': 'one two three four five six seven eight nine',
                                                             'domain': 'options', 'description': 'b'}})
        self.assertIn('at most 8', ' '.join(self.check(long)))

    def test_a_spoken_number_or_slide_is_not_a_tool(self):
        bad = obs()
        bad['methods'][0]['steps'][0]['tools'] = ['spoken estimate', 'Prepared graphic / screenshots in an image viewer']
        text = ' '.join(self.check(bad))
        self.assertIn('"spoken estimate" is not a site or software', text)
        self.assertIn('image viewer', text)

    def test_slug_never_ends_mid_word(self):
        out = analysis.slug('Selecting a cash-secured put strike and expiry from an options chain')
        self.assertLessEqual(len(out), 48)
        self.assertTrue('selecting-a-cash-secured-put-strike-and-expiry-from-an-options-chain'.startswith(out + '-'))
        self.assertEqual(analysis.slug('Short name'), 'short-name')

    def test_no_analysis_needs_a_reason(self):
        self.assertTrue(self.check({'video_id': VID, 'methods': []}))
        self.assertEqual(self.check({'video_id': VID, 'methods': [], 'no_analysis': True, 'reason': 'talking head'}), [])


class MergeAndRenderTests(AnalysisBase):
    def snapshot(self):
        return (self.lay.registry.read_text(), self.lay.tools.read_text(),
                (self.lay.observations / f'{VID}.json').read_text())

    def test_same_video_twice_changes_nothing(self):
        analysis.merge(self.lay, obs(), {'title': 'T'})
        first = self.snapshot()
        analysis.merge(self.lay, obs(), {'title': 'T'})
        self.assertEqual(first, self.snapshot())

    def test_second_video_builds_on_the_method(self):
        analysis.merge(self.lay, obs(), {})
        analysis.merge(self.lay, second_video(), {})
        reg = analysis.load_registry(self.lay)
        steps = reg['methods']['technical-read-on-a-chart']['steps']
        self.assertEqual([s['id'] for s in steps], ['open-the-chart', 'check-volume'])
        self.assertEqual(len(reg['methods']), 1)

    def test_tool_names_are_normalised(self):
        analysis.merge(self.lay, obs(), {})
        analysis.merge(self.lay, second_video(), {})
        tools = analysis.load_tools(self.lay)['tools']
        self.assertEqual([t['name'] for t in tools.values()], ['tradingview'])      # first spelling wins; one entry
        stored = json.loads((self.lay.observations / 'bbbbbbbbbb2.json').read_text())
        self.assertEqual({t for s in stored['methods'][0]['steps'] for t in s['tools']}, {'tradingview'})

    def test_rerun_that_drops_a_method_prunes_it(self):
        analysis.merge(self.lay, obs(), {})
        analysis.merge(self.lay, obs(method={'method_id': None, 'new_method': {'name': 'Other', 'domain': 'options', 'description': 'd'}}), {})
        self.assertEqual(list(analysis.load_registry(self.lay)['methods']), ['other'])

    def test_master_list_separates_stock_and_options_methods(self):
        analysis.merge(self.lay, obs(), {'title': 'First'})
        analysis.merge(self.lay, obs('bbbbbbbbbb2', method={'method_id': None, 'new_method': {
            'name': 'Put strike selection', 'domain': 'options', 'description': 'Pick a strike.'}}), {'title': 'Second'})
        analysis.render(self.lay, self.paths.notes)
        master = self.lay.master.read_text(encoding='utf-8')
        stocks, options = master.index('## Stock methods (1)'), master.index('## Options methods (1)')
        self.assertLess(stocks, options)
        self.assertIn('technical-read-on-a-chart.md', master[stocks:options])
        self.assertIn('put-strike-selection.md', master[options:])
        self.assertIn('**Type:** options analysis', (self.lay.methods_dir / 'put-strike-selection.md').read_text(encoding='utf-8'))
        self.assertIn('| stocks + options |', self.lay.tracker.read_text(encoding='utf-8'))

    def test_render_writes_master_method_and_tracker(self):
        analysis.merge(self.lay, obs(), {'title': 'First', 'published_at': '2026-11-01T00:00:00Z', 'channel': 'Chan'})
        analysis.merge(self.lay, second_video(), {'title': 'Second', 'published_at': '2026-11-05T00:00:00Z', 'channel': 'Chan'})
        written = analysis.render(self.lay, self.paths.notes)
        self.assertEqual({p.name for p in written}, {'methods.md', 'technical-read-on-a-chart.md', 'tools.md'})
        master = self.lay.master.read_text(encoding='utf-8')
        self.assertIn('(methods/technical-read-on-a-chart.md)', master)
        self.assertIn('| 2 | 2026-11-05 |', master)
        method = (self.lay.methods_dir / 'technical-read-on-a-chart.md').read_text(encoding='utf-8')
        self.assertIn('### 2. Check volume', method)
        self.assertIn('&t=135s', method)                       # 02:15 deep link
        self.assertIn('**[inference]**', method)
        tracker = self.lay.tracker.read_text(encoding='utf-8')
        self.assertIn('| tradingview | website | tradingview.com | charting |', tracker)
        self.assertIn('| RSI | momentum | overbought check | TradingView |', tracker)
        before = {p: p.read_text(encoding='utf-8') for p in written}
        analysis.render(self.lay, self.paths.notes)
        self.assertEqual(before, {p: p.read_text(encoding='utf-8') for p in written})     # re-render is stable


class RunTests(AnalysisBase):
    def test_good_run_merges_and_clears_the_inbox(self):
        res = self.run_one(obs())
        self.assertTrue(res.ok, res.problems)
        self.assertEqual(res.methods, 1)
        self.assertIn(VID, analysis.analysed_ids(self.lay))
        self.assertFalse((self.lay.inbox / f'{VID}.json').exists())

    def test_invalid_output_is_retried_once_with_the_problems(self):
        m = self.manifest()
        prompts = []

        def runner(item, prompt, log):
            prompts.append(prompt)
            self.lay.inbox.mkdir(parents=True, exist_ok=True)
            payload = obs() if len(prompts) > 1 else obs(steps=[{'at': 'x'}])
            (self.lay.inbox / f'{VID}.json').write_text(json.dumps(payload), encoding='utf-8')
            return RunResult(0, '')
        res = analysis.run_analysis(self.store, m, runner=runner)
        self.assertTrue(res.ok)
        self.assertEqual(len(prompts), 2)
        self.assertIn('previous attempt was rejected', prompts[1])

    def test_model_failure_is_reported_not_raised_and_stays_pending(self):
        m = self.manifest()
        res = analysis.run_analysis(self.store, m, runner=lambda item, prompt, log: RunResult(1, 'boom'))
        self.assertFalse(res.ok)
        self.assertTrue(res.problems)
        self.assertEqual(analysis.pending_ids(self.store), [VID])

    def test_no_transcript_is_skipped_without_calling_the_model(self):
        m = self.manifest()
        (self.paths.raw / VID / 'transcript.txt').unlink()
        res = analysis.run_analysis(self.store, m, runner=lambda *a: self.fail('model called'))
        self.assertEqual(res.skipped, 'no transcript.txt on disk')

    def test_prompt_has_no_unfilled_placeholders_and_shows_the_registry(self):
        analysis.merge(self.lay, obs(), {})
        text = analysis.build_prompt(analysis.prompt_template(self.paths), self.manifest(), self.paths, self.lay)
        self.assertIn('technical-read-on-a-chart', text)
        self.assertIn(f'_data/inbox/{VID}.json', text)
        for name in ('video_id', 'title', 'channel', 'url', 'raw_dir', 'out_path', 'registry'):
            self.assertNotIn('{' + name + '}', text)

    def test_sample_spreads_across_channels(self):
        for vid, chan in (('aaaaaaaaaa1', 'A'), ('aaaaaaaaaa2', 'A'), ('bbbbbbbbbb1', 'B')):
            self.manifest(vid, channel=chan)
            (self.paths.raw / vid / 'sheets').mkdir()
        picks = analysis.pick_sample(self.store, 2)
        self.assertEqual({v[0] for v in picks}, {'a', 'b'})


if __name__ == '__main__':
    unittest.main()
