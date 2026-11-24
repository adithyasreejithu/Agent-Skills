import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import _path  # noqa: F401
from _fakes import make_paths
from config import ConfigError, ReelSource, clean_username, load_reel_sources
from ig_poll import add_reel, poll_reels
from ig_poll import cooldown
from igweb import (Blocked, Candidate, IgError, LoginWall, NotFound, Profile, Unavailable, block_signal,
                   candidates_from_page, edge_older, fill_meta, keep_order, last_unchecked, meta_from_ytdlp, page_problem, parse_media, past_horizon, read_session)
from process import TextRun
from reel_brief import tickers_table, validate as validate_brief, write_reel_brief
import reel_filter
from reels import (ReelType, check_entry, fetch_queue, load_types, make_batches, parse_array, redo, render_month,
                   render_reel, summarize_batch, summarize_queue, trial_report)
from reelstore import ReelStore
from urls import extract_reel_code, reel_url

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
TEMPLATE = 'Summarize {count} reels from {creators}.\n{types_block}\n{reels}'


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')


def media(code, pinned=False, views=100):
    pin = '"999"' if pinned else ''
    return (f'{{"user":{{"pk":"1"}},"product_type":"clips","play_count":{views},'
            f'"clips_tab_pinned_user_ids":[{pin}],"code":"{code}","display_uri":"x"}}')


class FakeWeb:
    def __init__(self, profiles=None, metas=None):
        self.profiles = profiles or {}
        self.metas = metas or {}
        self.meta_calls = []

    def profile(self, username, since=None, max_scrolls=None):
        self.since = since
        found = self.profiles.get(username)
        if isinstance(found, Exception):
            raise found
        return Profile(username, [c if isinstance(c, Candidate) else Candidate(c, username) for c in found or []])

    def reel_meta(self, code):
        self.meta_calls.append(code)
        meta = self.metas.get(code, {})
        if isinstance(meta, Exception):
            raise meta
        return {'taken_at': ts(1), 'caption': f'caption {code}', 'duration_s': 30.0, 'username': 'jonah',
                'creator_name': 'Jonah', **meta}


def source(**kw):
    return ReelSource(**{'username': 'jonah', 'name': 'Stocks with Jonah', 'max_age_days': 3, **kw})


class UrlAndConfigTests(unittest.TestCase):
    def test_reel_codes(self):
        for url in ('https://www.instagram.com/reel/Dew_paEIJvi/', 'instagram.com/reels/Dew_paEIJvi',
                    'https://www.instagram.com/p/Dew_paEIJvi/?hl=en', 'https://www.instagram.com/jonah/reel/Dew_paEIJvi/'):
            self.assertEqual(extract_reel_code(url), 'Dew_paEIJvi', url)
        for url in ('https://www.youtube.com/watch?v=Dew_paEIJvi', 'https://www.instagram.com/jonah/', ''):
            self.assertIsNone(extract_reel_code(url), url)
        self.assertEqual(reel_url('abc12345678'), 'https://www.instagram.com/reel/abc12345678/')

    def test_usernames(self):
        self.assertEqual(clean_username('https://www.instagram.com/andre.invests/?hl=en'), 'andre.invests')
        self.assertEqual(clean_username('https://www.instagram.com/jointhe535/reels/?hl=en'), 'jointhe535')
        self.assertEqual(clean_username('@Mo.Invests'), 'mo.invests')
        self.assertIsNone(clean_username('not a user!'))

    def test_load_reel_sources(self):
        root = Path(tempfile.mkdtemp())
        path = root / 'reel-sources.toml'
        self.assertEqual(load_reel_sources(path), [])
        path.write_text('[defaults]\nmax_age_days = 5\n[[creator]]\nusername = "@Jonah"\n'
                        '[[creator]]\nusername = "mo"\nmax_age_days = 2\nenabled = false\n', encoding='utf-8')
        jonah, mo = load_reel_sources(path)
        self.assertEqual((jonah.username, jonah.max_age_days, jonah.name), ('jonah', 5, 'jonah'))
        self.assertEqual((mo.max_age_days, mo.enabled), (2, False))
        path.write_text('[[creator]]\nusername = "a"\n[[creator]]\nusername = "A"\n', encoding='utf-8')
        with self.assertRaises(ConfigError):
            load_reel_sources(path)


class PageParsingTests(unittest.TestCase):
    def test_scroll_stops_once_the_oldest_loaded_reel_is_past_the_cutoff(self):
        since = datetime(2026, 10, 1, tzinfo=timezone.utc)
        found = [Candidate('PINNEDAAAAA', 'x', pinned=True, taken_at='2025-01-01T00:00:00Z'),
                 Candidate('NEWAAAAAAAA', 'x'), Candidate('EDGEAAAAAAA', 'x')]
        self.assertEqual(last_unchecked(found, {}).code, 'EDGEAAAAAAA')
        self.assertFalse(edge_older(found, since))
        looked = {'EDGEAAAAAAA': {'taken_at': '2026-09-20T00:00:00Z', 'caption': 'old one', 'duration_s': 30.0}}
        fill_meta(found, looked)
        self.assertIsNone(last_unchecked(found, looked))
        self.assertTrue(edge_older(found, since))
        self.assertEqual(found[2].caption, 'old one')
        found[2].taken_at = '2026-10-10T00:00:00Z'
        self.assertFalse(edge_older(found, since))

    def test_links_dropped_by_the_scrolling_grid_are_kept(self):
        first = ['/x/reel/AAAAAAAAAAA/', '/x/reel/BBBBBBBBBBB/']
        later = ['/x/reel/BBBBBBBBBBB/', '/x/reel/CCCCCCCCCCC/', '/x/reel/CCCCCCCCCCC/']
        self.assertEqual(keep_order(first, later),
                         ['/x/reel/AAAAAAAAAAA/', '/x/reel/BBBBBBBBBBB/', '/x/reel/CCCCCCCCCCC/'])

    def test_parse_media_reads_pinned_and_views_per_code(self):
        html = '<script>' + ','.join([media('AAAAAAAAAA1', pinned=True, views=5), media('BBBBBBBBBB2', views=7)]) + \
               ',{"locale":{"code":"en_US"}}</script>'
        found = parse_media(html)
        self.assertEqual(set(found), {'AAAAAAAAAA1', 'BBBBBBBBBB2'})
        self.assertEqual(found['AAAAAAAAAA1'], {'pinned': True, 'views': 5})
        self.assertEqual(found['BBBBBBBBBB2'], {'pinned': False, 'views': 7})

    def test_taken_at_from_api_json(self):
        body = '{"items":[{"media_type":2,"product_type":"clips","taken_at":1792598422,"code":"CCCCCCCCCC3","video_duration":31.5}]}'
        found = parse_media(body)
        self.assertEqual(found['CCCCCCCCCC3']['taken_at'][:10], '2026-10-21')
        self.assertEqual(found['CCCCCCCCCC3']['duration_s'], 31.5)

    def test_candidates_follow_the_link_order(self):
        html = media('AAAAAAAAAA1', pinned=True) + media('BBBBBBBBBB2')
        anchors = ['/jonah/reel/BBBBBBBBBB2/', '/jonah/reel/AAAAAAAAAA1/', '/jonah/reel/BBBBBBBBBB2/', '/explore/']
        found = candidates_from_page('jonah', 'https://www.instagram.com/jonah/reels/', html, anchors)
        self.assertEqual([c.code for c in found], ['BBBBBBBBBB2', 'AAAAAAAAAA1'])
        self.assertTrue(found[1].pinned)

    def test_login_wall_and_missing_profile(self):
        with self.assertRaises(LoginWall):
            candidates_from_page('jonah', 'https://www.instagram.com/accounts/login/?next=x', '', [])
        with self.assertRaises(NotFound):
            candidates_from_page('jonah', 'https://www.instagram.com/jonah/', "Sorry, this page isn't available.", [])

    def test_caption_from_api_json(self):
        body = ('{"items":[{"product_type":"clips","taken_at":1792598422,"caption":{"pk":"1","text":"Buy \\"INTC\\"\\nnow"},'
                '"code":"CCCCCCCCCC3"}]}')
        self.assertEqual(parse_media(body)['CCCCCCCCCC3']['caption'], 'Buy "INTC"\nnow')

    def test_pushback_is_blocked_when_logged_in(self):
        self.assertIsInstance(page_problem('https://www.instagram.com/challenge/?x', ''), Blocked)
        self.assertIsInstance(page_problem('https://www.instagram.com/accounts/login/', '', logged_in=True), Blocked)
        self.assertIsInstance(page_problem('https://www.instagram.com/accounts/login/', ''), LoginWall)
        self.assertIsInstance(page_problem('https://www.instagram.com/jonah/reels/', 'Try Again Later. We limit how often'), Blocked)
        self.assertEqual(block_signal('{"message":"feedback_required","spam":true}'), 'feedback_required')
        self.assertIsNone(page_problem('https://www.instagram.com/jonah/reels/', 'Stocks with Jonah reels'))

    def test_visible_text_decides_not_the_scripts(self):
        html = media('AAAAAAAAAA1') + '<script>"Try Again Later"</script>'
        found = candidates_from_page('jonah', 'https://www.instagram.com/jonah/reels/', html,
                                     ['/reel/AAAAAAAAAA1/'], visible='Jonah · Reels')
        self.assertEqual([c.code for c in found], ['AAAAAAAAAA1'])

    def test_past_horizon_ignores_pinned_and_needs_three_old(self):
        since = NOW - timedelta(days=30)
        old = [Candidate(f'O{i:010d}', 'j', taken_at=ts(40)) for i in range(3)]
        self.assertFalse(past_horizon([Candidate('P0000000001', 'j', pinned=True, taken_at=ts(400)), *old[:2]], since))
        self.assertTrue(past_horizon([Candidate('N0000000001', 'j', taken_at=ts(1)), *old], since))
        self.assertFalse(past_horizon(old, None))

    def test_read_session(self):
        folder = Path(tempfile.mkdtemp())
        self.assertIsNone(read_session(folder))
        self.assertIsNone(read_session(None))
        (folder / 'ig-session.json').write_text('{"user_agent": "UA", "saved_at": "x"}', encoding='utf-8')
        self.assertEqual(read_session(folder)['user_agent'], 'UA')

    def test_ytdlp_meta(self):
        meta = meta_from_ytdlp({'timestamp': 1792598422, 'description': 'Buy INTC', 'channel': 'StocksWithJonah',
                                'formats': [{'duration': 30.3}, {}]})
        self.assertEqual(meta['taken_at'][:10], '2026-10-21')
        self.assertEqual((meta['duration_s'], meta['username'], meta['caption']), (30.3, 'stockswithjonah', 'Buy INTC'))


class PollTests(unittest.TestCase):
    def setUp(self):
        self.store = ReelStore(make_paths(Path(tempfile.mkdtemp())))
        self.store.ensure()

    def poll(self, web, **kw):
        return poll_reels(self.store, kw.pop('sources', [source()]), web, NOW, sleep=lambda s: None, **kw)

    def test_queues_new_reels_once(self):
        web = FakeWeb({'jonah': ['AAAAAAAAAA1', 'BBBBBBBBBB2']})
        report = self.poll(web)
        self.assertEqual(report.count('queued'), 2)
        item = self.store.find('AAAAAAAAAA1')[1]
        self.assertEqual((item['origin'], item['username'], item['url']),
                         ('ig', 'jonah', 'https://www.instagram.com/reel/AAAAAAAAAA1/'))
        self.assertEqual(self.poll(web).count('queued'), 0)
        self.assertEqual(len(web.meta_calls), 2)

    def test_filters_and_stops_looking_up_after_old_reels(self):
        codes = [f'{c}' * 10 + '1' for c in 'ABCDEFG']
        metas = {codes[0]: {'duration_s': 4.0}, codes[1]: {'duration_s': 400.0}}
        metas.update({c: {'taken_at': ts(10)} for c in codes[2:]})
        web = FakeWeb({'jonah': codes}, metas)
        report = self.poll(web)
        reasons = [o.detail for o in report.outcomes]
        self.assertEqual(reasons[:2], ['too_short', 'too_long'])
        self.assertEqual(reasons[2:], ['too_old'] * 5)
        self.assertEqual(len(web.meta_calls), 5)          # the last two were skipped without a lookup

    def test_days_override_reconsiders_too_old(self):
        web = FakeWeb({'jonah': ['AAAAAAAAAA1']}, {'AAAAAAAAAA1': {'taken_at': ts(10)}})
        self.assertEqual(self.poll(web).count('skipped'), 1)
        self.assertEqual(self.poll(web, days=30).count('queued'), 1)

    def test_pinned_old_reel_does_not_count_towards_the_stop(self):
        cands = [Candidate('PPPPPPPPPP1', 'jonah', pinned=True), Candidate('AAAAAAAAAA1', 'jonah')]
        web = FakeWeb({'jonah': cands}, {'PPPPPPPPPP1': {'taken_at': ts(200)}})
        report = self.poll(web)
        self.assertEqual([o.detail.split()[0] for o in report.outcomes], ['pinned_old', ts(1)[:10]])

    def test_login_wall_stops_the_poll_and_counts_a_failure(self):
        web = FakeWeb({'jonah': LoginWall('login'), 'mo': ['AAAAAAAAAA1']})
        report = self.poll(web, sources=[source(), source(username='mo', name='Mo')])
        self.assertEqual(report.polled, 0)
        self.assertEqual(self.store.load_state()['channels']['ig:jonah']['fail_count'], 1)
        self.assertTrue(any('login' in w for w in report.warnings))

    def test_unavailable_is_skipped_and_errors_are_retried(self):
        web = FakeWeb({'jonah': ['AAAAAAAAAA1', 'BBBBBBBBBB2']},
                      {'AAAAAAAAAA1': Unavailable('gone'), 'BBBBBBBBBB2': IgError('timeout')})
        report = self.poll(web)
        self.assertEqual([o.result for o in report.outcomes], ['skipped', 'error'])
        self.assertIn('AAAAAAAAAA1', self.store.known_ids())
        self.assertNotIn('BBBBBBBBBB2', self.store.known_ids())

    def test_blocked_stops_everything_and_cools_down(self):
        web = FakeWeb({'jonah': Blocked('Instagram says: Try Again Later'), 'mo': ['AAAAAAAAAA1']})
        report = self.poll(web, sources=[source(), source(username='mo', name='Mo')])
        self.assertEqual(report.polled, 0)
        state = self.store.load_state()
        self.assertEqual(cooldown(state, NOW)['until'], '2026-10-24T12:00:00Z')
        self.assertNotIn('fail_count', state['channels']['ig:jonah'])     # not the creator's fault
        again = self.poll(FakeWeb({'jonah': ['AAAAAAAAAA1']}))
        self.assertEqual((again.polled, again.count('queued')), (0, 0))
        self.assertIn('cooldown', again.warnings[0])
        later = poll_reels(self.store, [source()], FakeWeb({'jonah': ['AAAAAAAAAA1']}), NOW + timedelta(hours=49),
                           days=30, sleep=lambda s: None)
        self.assertEqual(later.count('queued'), 1)

    def test_logged_in_details_skip_the_lookup(self):
        cand = Candidate('AAAAAAAAAA1', 'jonah', taken_at=ts(2), caption='Buy INTC', duration_s=20.0, via='json')
        web = FakeWeb({'jonah': [cand]})
        report = self.poll(web, days=30)
        self.assertEqual(report.count('queued'), 1)
        self.assertEqual(web.meta_calls, [])
        self.assertEqual(self.store.find('AAAAAAAAAA1')[1]['caption'], 'Buy INTC')
        self.assertEqual(web.since, NOW - timedelta(days=30))

    def test_manual_add(self):
        web = FakeWeb()
        status, _, code = add_reel(self.store, web, 'https://www.instagram.com/reel/AAAAAAAAAA1/', NOW, [source()])
        self.assertEqual((status, code), ('queued', 'AAAAAAAAAA1'))
        self.assertEqual(self.store.find(code)[1]['channel_name'], 'Stocks with Jonah')
        self.assertEqual(add_reel(self.store, web, 'https://youtu.be/x', NOW, [])[0], 'rejected')


def queue_reel(store, code, transcribed=False, published=None, username='jonah'):
    store.add_pending({'video_id': code, 'url': reel_url(code), 'username': username, 'channel_name': username.title(),
                       'published_at': published or ts(1), 'caption': f'Caption for {code}: INTC 19', 'duration_s': 30,
                       'origin': 'ig', 'priority': 50, 'attempts': 0, 'transcribed': transcribed})


def save_transcript(store, code, text='I bought INTC at 19 and target 120.', username='jonah', taken=None):
    store.save_transcript({'code': code, 'username': username, 'creator': username.title(), 'taken_at': taken or ts(1),
                           'caption': f'Caption for {code}: INTC 19', 'duration_s': 30, 'speech': bool(text),
                           'segments': [{'start': 0, 'end': 5, 'text': text}] if text else [], 'gemini_tokens': 500})


def answer(*codes, **overrides):
    rows = []
    for code in codes:
        row = {'code': code, 'type': 'stock-pick', 'one_line': 'Bought INTC at 19, target 120.', 'tickers': ['$intc'],
               'stance': 'bullish', 'points': ['p1', 'p2', 'p3', 'p4', 'p5'], 'levels': ['bought at 19', 'target 120'],
               'fields': {}, 'on_screen': False, 'type_reason': 'names a ticker'}
        row.update(overrides.get(code, {}))
        rows.append(row)
    return TextRun(0, 'Here you go:\n```json\n' + json.dumps(rows) + '\n```', {'cost_usd': 0.01, 'output_tokens': 50})


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.store = ReelStore(make_paths(Path(tempfile.mkdtemp())))
        self.store.ensure()

    def test_transcribes_and_marks_items(self):
        queue_reel(self.store, 'AAAAAAAAAA1')
        queue_reel(self.store, 'BBBBBBBBBB2')
        results = {'AAAAAAAAAA1': {'ok': True, 'segments': [{'start': 0, 'end': 2, 'text': 'hi'}], 'gemini_tokens': 9},
                   'BBBBBBBBBB2': {'ok': True, 'segments': []}}
        report = fetch_queue(self.store, fetcher=lambda item, work: results[item['video_id']], now_fn=lambda: NOW)
        self.assertEqual(sorted(report.done), ['AAAAAAAAAA1', 'BBBBBBBBBB2'])
        a = self.store.find('AAAAAAAAAA1')
        self.assertEqual((a[0], a[1]['transcribed'], a[1]['speech']), ('pending', True, True))
        self.assertFalse(self.store.find('BBBBBBBBBB2')[1]['speech'])
        self.assertEqual(self.store.load_transcript('jonah', 'AAAAAAAAAA1')['segments'][0]['text'], 'hi')

    def test_quota_releases_without_an_attempt_and_stops(self):
        queue_reel(self.store, 'AAAAAAAAAA1')
        queue_reel(self.store, 'BBBBBBBBBB2')
        calls = []

        def fetcher(item, work):
            calls.append(item['video_id'])
            return {'ok': False, 'kind': 'quota', 'error': 'Gemini quota'}
        report = fetch_queue(self.store, fetcher=fetcher, now_fn=lambda: NOW)
        self.assertEqual(len(calls), 1)
        self.assertIn('quota', report.stopped)
        self.assertEqual(self.store.find(calls[0])[1]['attempts'], 0)

    def test_unavailable_is_skipped_and_failures_retry(self):
        queue_reel(self.store, 'AAAAAAAAAA1')
        queue_reel(self.store, 'BBBBBBBBBB2')
        results = {'AAAAAAAAAA1': {'ok': False, 'kind': 'unavailable', 'error': 'removed'},
                   'BBBBBBBBBB2': {'ok': False, 'kind': 'failed', 'error': 'ffmpeg broke'}}
        report = fetch_queue(self.store, fetcher=lambda item, work: results[item['video_id']], now_fn=lambda: NOW)
        self.assertEqual([c for c, _ in report.skipped], ['AAAAAAAAAA1'])
        self.assertIsNone(self.store.find('AAAAAAAAAA1'))
        item = self.store.find('BBBBBBBBBB2')[1]
        self.assertEqual((item['attempts'], bool(item['not_before'])), (1, True))


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.store = ReelStore(make_paths(Path(tempfile.mkdtemp())))
        self.store.ensure()

    def ready(self, *codes, username='jonah'):
        for code in codes:
            queue_reel(self.store, code, transcribed=True, username=username)
            save_transcript(self.store, code, username=username)

    def test_one_call_for_a_batch_writes_index_and_month_file(self):
        self.ready('AAAAAAAAAA1', 'BBBBBBBBBB2')
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            return answer('AAAAAAAAAA1', 'BBBBBBBBBB2')
        report = summarize_queue(self.store, runner=runner, template=TEMPLATE, open_types=True, now_fn=lambda: NOW)
        self.assertEqual((sorted(report.done), report.calls), (['AAAAAAAAAA1', 'BBBBBBBBBB2'], 1))
        self.assertIn('I bought INTC at 19', prompts[0])
        entry = self.store.load_index()['AAAAAAAAAA1']
        self.assertEqual((entry['tickers'], len(entry['points']), entry['mode']), (['INTC'], 4, 'open'))
        self.assertIsNone(self.store.find('AAAAAAAAAA1'))
        month = (self.store.notes_dir / 'jonah' / f'{ts(1)[:7]}.md').read_text(encoding='utf-8')
        self.assertIn('[AAAAAAAAAA1](https://www.instagram.com/reel/AAAAAAAAAA1/)', month)
        self.assertEqual(len(list((self.store.notes_dir).glob('*.jsonl'))), 2)   # reels.jsonl + _cost.jsonl

    def test_retry_only_sends_the_broken_reels(self):
        self.ready('AAAAAAAAAA1', 'BBBBBBBBBB2')
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return answer('AAAAAAAAAA1', 'BBBBBBBBBB2', BBBBBBBBBB2={'stance': 'very bullish'})
            return answer('BBBBBBBBBB2')
        report = summarize_queue(self.store, runner=runner, template=TEMPLATE, open_types=True, now_fn=lambda: NOW)
        self.assertEqual(len(report.done), 2)
        self.assertIn('BBBBBBBBBB2: `stance`', prompts[1])
        self.assertNotIn('code="AAAAAAAAAA1"', prompts[1])

    def test_invented_number_is_retried_then_kept_flagged(self):
        self.ready('AAAAAAAAAA1')
        bad = {'AAAAAAAAAA1': {'levels': ['target 777']}}
        report = summarize_queue(self.store, runner=lambda p: answer('AAAAAAAAAA1', **bad), template=TEMPLATE,
                                 open_types=True, now_fn=lambda: NOW)
        self.assertEqual(report.done, ['AAAAAAAAAA1'])
        self.assertEqual(self.store.load_index()['AAAAAAAAAA1']['unverified_numbers'], ['777'])

    def test_structural_failure_goes_back_to_pending_with_an_attempt(self):
        self.ready('AAAAAAAAAA1')
        report = summarize_queue(self.store, runner=lambda p: TextRun(0, 'sorry, no JSON'), template=TEMPLATE,
                                 open_types=True, now_fn=lambda: NOW)
        self.assertEqual(len(report.retried), 1)
        stage, item = self.store.find('AAAAAAAAAA1')
        self.assertEqual((stage, item['attempts']), ('pending', 1))

    def test_typed_mode_checks_types_and_fields(self):
        types = [ReelType('stock-pick', 'one ticker', ('ticker', 'action'))]
        entry, problems, _ = check_entry({'type': 'stock-pick', 'one_line': 'x', 'fields': {'ticker': 'INTC'}}, '', types)
        self.assertEqual(problems, ['`fields` is missing action for type stock-pick'])
        _, problems, _ = check_entry({'type': 'meme', 'one_line': 'x'}, '', types)
        self.assertIn('not one of', problems[0])

    def test_batches_split_per_creator_and_size(self):
        pairs = [({'video_id': f'J{i:010d}', 'username': 'jonah', 'published_at': ts(i)}, None) for i in range(5)]
        pairs += [({'video_id': 'M0000000001', 'username': 'mo', 'published_at': ts(1)}, None)]
        batches = make_batches(pairs, 2)
        self.assertEqual([len(b) for b in batches], [2, 2, 1, 1])
        self.assertEqual(batches[0][0][0]['video_id'], 'J0000000004')     # oldest first

    def test_redo_rewrites_from_cached_transcripts(self):
        self.ready('AAAAAAAAAA1')
        summarize_queue(self.store, runner=lambda p: answer('AAAAAAAAAA1'), template=TEMPLATE, open_types=True,
                        now_fn=lambda: NOW)
        report = redo(self.store, NOW - timedelta(days=30), template=TEMPLATE, now_fn=lambda: NOW,
                      types=[ReelType('stock-pick')],
                      runner=lambda p: answer('AAAAAAAAAA1', AAAAAAAAAA1={'one_line': 'Redone.'}))
        self.assertEqual(report.done, ['AAAAAAAAAA1'])
        entry = self.store.load_index()['AAAAAAAAAA1']
        self.assertEqual((entry['one_line'], entry['mode']), ('Redone.', 'typed'))
        self.assertEqual(len(self.store.load_index()), 1)

    def test_parse_array(self):
        self.assertEqual(parse_array('x ```json\n[{"a": 1}]\n``` y'), [{'a': 1}])
        self.assertIsNone(parse_array('{"a": 1}'))

    def test_render_month_is_newest_first_and_promo_is_one_line(self):
        entries = [{'code': 'OLD00000001', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': '2026-10-01T00:00:00Z',
                    'type': 'stock-pick', 'one_line': 'old', 'points': ['p'], 'tickers': ['A'], 'stance': 'bullish'},
                   {'code': 'NEW00000001', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': '2026-10-20T00:00:00Z',
                    'type': 'promo', 'one_line': 'buy my course', 'points': ['skip me']},
                   {'code': 'SEP00000001', 'username': 'jonah', 'taken_at': '2026-09-20T00:00:00Z', 'type': 'promo',
                    'one_line': 'other month'}]
        text = render_month(entries, 'jonah', '2026-10', {'promo'})
        self.assertLess(text.index('NEW00000001'), text.index('OLD00000001'))
        self.assertNotIn('skip me', text)
        self.assertNotIn('other month', text)
        self.assertEqual(text, render_month(entries, 'jonah', '2026-10', {'promo'}))

    def test_trial_report_tables(self):
        self.ready('AAAAAAAAAA1', 'BBBBBBBBBB2')
        summarize_queue(self.store, runner=lambda p: answer('AAAAAAAAAA1', 'BBBBBBBBBB2', BBBBBBBBBB2={'type': 'promo'}),
                        template=TEMPLATE, open_types=True, now_fn=lambda: NOW)
        text = trial_report(self.store)
        self.assertIn('| stock-pick | 1 | 50% |', text)
        self.assertIn('| promo | 1 | 50% |', text)
        self.assertIn('## Cost by batch size', text)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.store = ReelStore(make_paths(Path(tempfile.mkdtemp())))
        self.store.ensure()

    def test_caption_information(self):
        self.assertFalse(reel_filter.caption_has_info('Another great day 💪💪💪 #stocks #nvidia'))
        self.assertFalse(reel_filter.caption_has_info('Follow for real setups not hyped up BS'))
        self.assertTrue(reel_filter.caption_has_info('Up 12k today'))
        self.assertTrue(reel_filter.caption_has_info('Watching $VST here'))
        self.assertTrue(reel_filter.caption_has_info('IREN, ASTS and RKLB on watch'))
        self.assertTrue(reel_filter.caption_has_info('word ' * 40))

    def test_stage_rules(self):
        self.assertIsNotNone(reel_filter.before_download('Another great day', 9))
        self.assertIsNone(reel_filter.before_download('Another great day', 30))
        self.assertIsNone(reel_filter.before_download('Bought at 19', 9))
        self.assertIsNotNone(reel_filter.before_model('LETS go', [{'text': 'Wow.'}]))
        self.assertIsNone(reel_filter.before_model('', [{'text': 'word ' * 25}]))
        self.assertEqual(reel_filter.sponsor_hint('#kalshipartner'), '#kalshipartner')
        self.assertEqual(reel_filter.sponsor_hint('', 'This video is a paid advertisement.'), 'paid advertisement')
        self.assertIsNone(reel_filter.sponsor_hint('Link in my bio', 'the World Cup is partnered with Ondas'))

    def test_short_empty_reel_is_filler_without_download(self):
        self.store.add_pending({'video_id': 'CCCCCCCCCC3', 'url': reel_url('CCCCCCCCCC3'), 'username': 'jonah',
                                'channel_name': 'Jonah', 'published_at': ts(1), 'caption': 'Another great day 💪',
                                'duration_s': 7, 'origin': 'ig', 'priority': 50, 'attempts': 0})
        queue_reel(self.store, 'AAAAAAAAAA1')
        calls = []

        def fetcher(item, work):
            calls.append(item['video_id'])
            return {'ok': True, 'segments': [{'start': 0, 'end': 2, 'text': 'hi'}]}
        report = fetch_queue(self.store, fetcher=fetcher, now_fn=lambda: NOW)
        self.assertEqual(calls, ['AAAAAAAAAA1'])
        self.assertEqual([c for c, _ in report.filtered], ['CCCCCCCCCC3'])
        self.assertIsNone(self.store.find('CCCCCCCCCC3'))
        entry = self.store.load_index()['CCCCCCCCCC3']
        self.assertEqual((entry['type'], entry['mode'], entry['evidence']), ('filler', 'rule', 'caption'))
        self.assertIn('Another great day', entry['one_line'])

    def test_near_silent_reel_skips_the_model(self):
        queue_reel(self.store, 'AAAAAAAAAA1', transcribed=True)
        save_transcript(self.store, 'AAAAAAAAAA1')
        self.store.add_pending({'video_id': 'BBBBBBBBBB2', 'url': reel_url('BBBBBBBBBB2'), 'username': 'jonah',
                                'channel_name': 'Jonah', 'published_at': ts(1), 'caption': 'So bad 😭',
                                'duration_s': 20, 'origin': 'ig', 'priority': 50, 'attempts': 0, 'transcribed': True})
        self.store.save_transcript({'code': 'BBBBBBBBBB2', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': ts(1),
                                    'caption': 'So bad 😭', 'duration_s': 20, 'speech': True,
                                    'segments': [{'start': 0, 'end': 2, 'text': 'Turn around.'}]})
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            return answer('AAAAAAAAAA1')
        report = summarize_queue(self.store, runner=runner, open_types=True, now_fn=lambda: NOW)
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('BBBBBBBBBB2', prompts[0])
        self.assertEqual([c for c, _ in report.filtered], ['BBBBBBBBBB2'])
        self.assertEqual(sorted(report.done), ['AAAAAAAAAA1'])
        index = self.store.load_index()
        self.assertEqual((index['BBBBBBBBBB2']['type'], index['BBBBBBBBBB2']['evidence']), ('filler', 'transcript+caption'))
        self.assertIsNone(self.store.find('BBBBBBBBBB2'))

    def test_rules_can_be_turned_off(self):
        self.store.add_pending({'video_id': 'BBBBBBBBBB2', 'url': reel_url('BBBBBBBBBB2'), 'username': 'jonah',
                                'channel_name': 'Jonah', 'published_at': ts(1), 'caption': 'So bad',
                                'duration_s': 20, 'origin': 'ig', 'priority': 50, 'attempts': 0, 'transcribed': True})
        self.store.save_transcript({'code': 'BBBBBBBBBB2', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': ts(1),
                                    'caption': 'So bad', 'duration_s': 20, 'speech': True,
                                    'segments': [{'start': 0, 'end': 2, 'text': 'Turn around.'}]})
        report = summarize_queue(self.store, runner=lambda prompt: answer('BBBBBBBBBB2'), open_types=True,
                                 now_fn=lambda: NOW, rules=False)
        self.assertEqual((report.filtered, report.done), ([], ['BBBBBBBBBB2']))

    def test_sponsor_hint_reaches_the_prompt(self):
        item = {'video_id': 'AAAAAAAAAA1', 'channel_name': 'Christy', 'published_at': ts(1), 'duration_s': 40}
        row = {'caption': 'Big win #kalshipartner', 'segments': [{'text': 'Someone just bet big.'}]}
        self.assertIn('sponsor_hint="#kalshipartner"', render_reel(item, row))

    def test_shipped_type_list_loads(self):
        types = load_types()
        self.assertEqual({t.name for t in types}, {'stock-pick', 'watchlist', 'trade', 'portfolio-update', 'market-news',
                                                  'insider-trade', 'education', 'promo', 'filler'})
        self.assertEqual({t.name for t in types if t.brief == 'skip'}, {'promo', 'filler'})


class ReelBriefTests(unittest.TestCase):
    def setUp(self):
        self.store = ReelStore(make_paths(Path(tempfile.mkdtemp())))
        self.store.ensure()
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.day = datetime.now().astimezone().date()
        self.store.save_index({
            'AAAAAAAAAA1': {'code': 'AAAAAAAAAA1', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': stamp,
                            'ingested_at': stamp, 'type': 'stock-pick', 'one_line': 'Bought INTC at 19.',
                            'tickers': ['INTC'], 'stance': 'bullish', 'levels': ['bought at 19'], 'url': 'u'},
            'BBBBBBBBBB2': {'code': 'BBBBBBBBBB2', 'username': 'jonah', 'creator': 'Jonah', 'taken_at': stamp,
                            'ingested_at': stamp, 'type': 'promo', 'one_line': 'Join my discord.', 'url': 'u'}})

    def body(self, extra=''):
        return ('## Short read\n- **Buying:** Jonah bought INTC at 19.\n- **Mood:** bullish.\n- **Watching:** INTC.' + extra
                + '\n\n## By creator\n\n### Jonah\n- INTC bought at 19.')

    def test_writes_brief_without_promo_and_with_tables(self):
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            return TextRun(0, self.body(), {'cost_usd': 0.01})
        result = write_reel_brief(self.store, self.day, runner=runner, template='{reels}\n{counted}', types=None)
        text = result.path.read_text(encoding='utf-8')
        self.assertEqual((result.generated, result.included, result.reels), ('claude', 1, 2))
        self.assertNotIn('discord', prompts[0])
        self.assertIn('promo: 1', prompts[0])
        self.assertIn('| INTC | Jonah | bullish | bought at 19 |', text)
        self.assertIn('[BBBBBBBBBB2](u)', text)          # every reel is still listed

    def test_invented_number_falls_back_after_retry(self):
        runner = lambda prompt: TextRun(0, self.body('\n- **Levels:** target 555.'))
        result = write_reel_brief(self.store, self.day, runner=runner, template='{reels}', types=None)
        self.assertEqual((result.generated, result.attempts), ('fallback', 2))
        self.assertIn('555', result.problems[0])
        self.assertIn('### Jonah', result.path.read_text(encoding='utf-8'))

    def test_validate_needs_each_creator(self):
        entries = [{'creator': 'Jonah'}, {'creator': 'Mo'}]
        problems = validate_brief('## Short read\n- a\n- b\n- c\n\n## By creator\n### Jonah\n- x', entries)
        self.assertEqual(problems, ['"## By creator" has no "### Mo" section'])

    def test_ticker_table_without_tickers(self):
        self.assertEqual(tickers_table([{'creator': 'x'}]), ['_No tickers today._'])


if __name__ == '__main__':
    unittest.main()
