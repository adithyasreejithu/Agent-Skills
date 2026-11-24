import json
import tempfile
import unittest
from datetime import date, timedelta, timezone
from pathlib import Path

import _path  # noqa: F401
from _fakes import make_paths
from brief import (BriefRun, build_brief_prompt, clean_body, day_batch, history_notes, unsourced_numbers,
                   validate_brief, write_brief)
from store import Store, write_json

EDT = timezone(timedelta(hours=-4))
DAY = date(2026, 10, 20)
RYAN, JEREMY = 'Options With Ryan', 'Jeremy Lefebvre Makes Money'
TEMPLATE = 'Brief for {date}: {video_count} from {channels}\n{notes}\n{history_block}\n{changed_bullet}{changed_section}'

NOTE = """---
video_id: {vid}
channel: {channel}
title: Video {vid}
published: {published}
stance: bullish
tickers: [AMAT, QQQ]
---

# Video {vid}

- Stored data: `C:/somewhere/{vid}/`

## Market view
QQQ about 719.75, buy zone 694 to 700. 10-year 5.144, oil 99.22, VIX 18.37. Cash 11%.

## Positions and plans
| AMAT | holds | puts at 500, 475, 455; covered call 470 |
"""


def short_read(extra=''):
    return ('## Short read\n'
            '- **Mood:** bullish, buying dips.\n'
            '- **Buying:** AMAT puts at 500/475/455.\n'
            '- **Holding / income:** plans a 470 covered call.\n'
            '- **Levels:** QQQ ~720, buy zone 694-700; 10Y ~5.1%, oil ~$99.\n'
            '- **This week:** Tesla and Meta on Wed.\n' + extra)


def long_read(channels, changed=True):
    stocks = [f'**{c}**: Thesis.\n| Ticker | Action | Levels as stated |\n| AMAT | holding | none |' for c in channels]
    options = [f'**{c}**: Puts.\n| Ticker | Action | Levels as stated |\n| AMAT | holding | puts at 500 |' for c in channels]
    parts = ['## Long read', '### Market dashboard', '| gauge | x |',
             '### Stocks', *stocks, '### Options', *options,
             '### Where they agree or differ', 'No overlap today.']
    if changed:
        parts += ['### What changed since their last video', 'Buy zone moved.']
    parts += ['### Calendar', '- Wed: Tesla', '### Caveats', 'None.']
    return '\n'.join(parts)


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.paths = make_paths(self.root)
        self.store = Store(self.paths)
        self.store.ensure()
        self.paths.notes.mkdir(parents=True, exist_ok=True)

    def done(self, vid, channel=RYAN, published='2026-10-19', ingested='2026-10-20T11:00:00Z'):
        note = self.paths.notes / f'{vid}-video.md'
        note.write_text(NOTE.format(vid=vid, channel=channel, published=published), encoding='utf-8')
        write_json(self.store.item_path('done', vid), {
            'video_id': vid, 'title': f'Video {vid}', 'channel': channel, 'note': note.as_posix(),
            'published_at': f'{published}T00:00:00Z', 'ingested_at': ingested, 'stance': 'bullish',
            'tickers': ['AMAT', 'QQQ']})

    def runner(self, *bodies):
        """A fake `claude -p` that returns the given bodies in turn and records the prompts it saw."""
        self.prompts = []
        queue = list(bodies)

        def run(prompt):
            self.prompts.append(prompt)
            return BriefRun(0, queue.pop(0), {'input_tokens': 1000, 'output_tokens': 200, 'cost_usd': 0.01})
        return run

    # ---- choosing the notes ------------------------------------------------
    def test_batch_uses_local_date_not_utc(self):
        self.done('aaaaaaaaaa1', ingested='2026-10-21T00:34:00Z')      # 8:34 PM EDT on Oct 20
        self.done('aaaaaaaaaa2', ingested='2026-10-21T11:00:00Z')      # 7:00 AM EDT on Oct 21
        self.assertEqual([e.manifest['video_id'] for e in day_batch(self.store, DAY, EDT)], ['aaaaaaaaaa1'])

    def test_history_is_the_same_creators_previous_video_outside_the_batch(self):
        self.done('old00000001', published='2026-10-10', ingested='2026-10-12T11:00:00Z')
        self.done('old00000002', published='2026-10-15', ingested='2026-10-16T11:00:00Z')
        self.done('other000001', channel=JEREMY, published='2026-10-18', ingested='2026-10-19T11:00:00Z')
        self.done('today000001', published='2026-10-19')
        self.done('today000002', published='2026-10-20')
        batch = day_batch(self.store, DAY, EDT)
        self.assertEqual([e.manifest['video_id'] for e in history_notes(self.store, batch)], ['old00000002'])

    def test_prompt_inlines_notes_without_local_paths_and_always_compares_history(self):
        self.done('aaaaaaaaaa1')
        batch = day_batch(self.store, DAY, EDT)
        prompt = build_brief_prompt(TEMPLATE, DAY, batch, [])
        self.assertIn('<note video_id="aaaaaaaaaa1">', prompt)
        self.assertNotIn('Stored data', prompt)
        self.assertIn('No earlier notes', prompt)
        self.assertIn('What changed', prompt)
        earlier = [e for e in batch]                                     # any non-empty list stands for earlier notes
        self.assertIn('<earlier_note video_id="aaaaaaaaaa1">', build_brief_prompt(TEMPLATE, DAY, batch, earlier))

    # ---- checking ----------------------------------------------------------
    def test_numbers_must_come_from_the_notes_allowing_rounding(self):
        source = [NOTE.format(vid='x', channel=RYAN, published='2026-10-19')]
        self.assertEqual(unsourced_numbers('QQQ ~720, 10Y ~5.1%, oil ~$99, 3 puts', source), [])
        self.assertEqual(unsourced_numbers('target 812, yield 5.3%', source), ['812', '5.3'])

    def test_validator_rules(self):
        self.done('aaaaaaaaaa1')
        batch = day_batch(self.store, DAY, EDT)
        sources = [e.text for e in batch]
        good = short_read() + long_read([RYAN])
        self.assertEqual(validate_brief(good, batch, sources), [])
        four = '\n'.join(short_read().splitlines()[:5]) + '\n' + long_read([RYAN])
        self.assertIn('4 bullets', ' '.join(validate_brief(four, batch, sources)))
        eight = short_read('- **a:** x\n- **b:** y\n- **c:** z\n') + long_read([RYAN])
        self.assertIn('8 bullets', ' '.join(validate_brief(eight, batch, sources)))
        wordy = short_read().replace('bullish, buying dips.', 'word ' * 180) + long_read([RYAN])
        self.assertIn('limit is 180', ' '.join(validate_brief(wordy, batch, sources)))
        invented = short_read().replace('~720', '~812') + long_read([RYAN])
        self.assertIn('812', ' '.join(validate_brief(invented, batch, sources)))
        no_creator = short_read() + long_read(['Someone Else'])
        self.assertIn(f'"{RYAN}"', ' '.join(validate_brief(no_creator, batch, sources)))
        no_options = short_read() + long_read([RYAN]).replace('### Options', '### Something')
        self.assertIn('"### Options"', ' '.join(validate_brief(no_options, batch, sources)))
        no_changed = short_read() + long_read([RYAN], changed=False)
        self.assertIn('What changed', ' '.join(validate_brief(no_changed, batch, sources)))

    def test_clean_body_drops_chatter_and_any_videos_list(self):
        text = 'Here is your brief:\n\n' + short_read() + long_read([RYAN]) + '\n## Videos\n- a link'
        cleaned = clean_body(text)
        self.assertTrue(cleaned.startswith('## Short read'))
        self.assertNotIn('## Videos', cleaned)

    # ---- writing -----------------------------------------------------------
    def test_writes_brief_with_header_and_video_links_and_logs_cost(self):
        self.done('aaaaaaaaaa1')
        result = write_brief(self.store, DAY, runner=self.runner(short_read() + long_read([RYAN])),
                             template=TEMPLATE, tz=EDT)
        self.assertEqual((result.generated, result.attempts), ('claude', 1))
        self.assertEqual(result.path.name, '2026-10-20.md')
        text = result.path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\ndate: 2026-10-20\nvideos: 1\n'))
        self.assertNotIn('history:', text)
        self.assertIn('generated: claude', text)
        self.assertIn('(../summaries/aaaaaaaaaa1-video.md)', text)
        cost = [json.loads(line) for line in (self.paths.briefs / '_cost.jsonl').read_text().splitlines()]
        self.assertEqual(cost[0]['input_tokens'], 1000)

    def test_invalid_draft_is_retried_once_with_the_problems(self):
        self.done('aaaaaaaaaa1')
        bad = short_read().replace('~720', '~812') + long_read([RYAN])
        result = write_brief(self.store, DAY, runner=self.runner(bad, short_read() + long_read([RYAN])),
                             template=TEMPLATE, tz=EDT)
        self.assertEqual((result.generated, result.attempts), ('claude', 2))
        self.assertIn('812', self.prompts[1])
        self.assertEqual(result.usage['input_tokens'], 2000)            # both attempts counted
        self.assertIn('812', result.retry_reasons[0])
        cost = json.loads((self.paths.briefs / '_cost.jsonl').read_text().splitlines()[-1])
        self.assertIn('812', cost['retry_reasons'][0])

    def test_falls_back_when_claude_fails_twice(self):
        self.done('aaaaaaaaaa1')
        failing = lambda prompt: BriefRun(1, 'API error')
        result = write_brief(self.store, DAY, runner=failing, template=TEMPLATE, tz=EDT)
        text = result.path.read_text(encoding='utf-8')
        self.assertEqual(result.generated, 'fallback')
        self.assertIn('generated: fallback', text)
        self.assertIn(f'**{RYAN}**: 1 video(s); stance bullish; tickers: AMAT, QQQ', text)
        self.assertIn('## Videos', text)

    def test_second_run_same_day_rewrites_with_all_videos(self):
        self.done('aaaaaaaaaa1')
        body = short_read() + long_read([RYAN])
        write_brief(self.store, DAY, runner=self.runner(body), template=TEMPLATE, tz=EDT)
        self.done('aaaaaaaaaa2', ingested='2026-10-20T15:00:00Z')
        result = write_brief(self.store, DAY, runner=self.runner(body), template=TEMPLATE, tz=EDT)
        text = result.path.read_text(encoding='utf-8')
        self.assertIn('videos: 2', text)
        self.assertEqual((text.count('aaaaaaaaaa1-video.md'), text.count('aaaaaaaaaa2-video.md')), (1, 1))

    def test_nothing_finished_writes_nothing(self):
        self.assertIsNone(write_brief(self.store, DAY, runner=self.runner(), template=TEMPLATE, tz=EDT))
        self.assertFalse(self.paths.briefs.exists())


if __name__ == '__main__':
    unittest.main()
