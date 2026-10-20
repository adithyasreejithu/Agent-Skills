# Watch Skill: Testing Mode Plan

Status: first version built. Training is in progress (videos arrive one at a time).

## Goal
Learn which transcript cues predict a *useful* video frame, and at what time offset, so `/watch`
can pick snapshots by itself instead of relying on scene-change detection or hand-picked timestamps.

## Why
- Scene detection missed the whole chart walk-through of the first test video (3:29 to 11:20): ticker
  switches on one shared screen are small visual changes.
- Auto-captions garble tickers (AMAT heard as "AAT", Amkor as "Amcor"), and the frame is the only
  reliable source for them. Named instruments are the highest-value cue we have found so far.

## Where things live
| Thing | Location |
|---|---|
| Per-video output (frames, sheets, downloads, `testing.json`) | `watch-output/video-data/<video-id>/` |
| Written summaries (kept outside watch-output, never touched by the cleaner) | `summaries/` |
| Word bank (cue terms) | `training/word-bank.json` |
| Labels (verdicts per frame) | `training/labels/<video-id>.json` |
| Testing-mode code | `.agents/skills/watch/scripts/testing.py` + `--testing` in `watch.py` |
| Scoring and cleanup CLI | `src/agent_skills/` (`train.py`, `gc.py`) |

`training/` is tracked in git and is never touched by the cleaner. Every report starts with
"Stored in watch-output: ..." so it is always clear where a video lives.

## How a training run works
1. `uv run python .agents/skills/watch/scripts/watch.py "<url>" --testing --resolution 1024`
2. Captions are fetched and the video downloaded to `watch-output/video-data/<video-id>/`.
3. Every transcript segment is matched against the word bank. Each term is capped at 3 cues per video
   and repeats within 10 s are collapsed. If there are more cues than the frame cap allows, they are
   sampled evenly across the video.
4. For each cue, frames are grabbed at several offsets around it (default **-2, 0, +2, +4, +6 s**).
   Each cue's offsets are stitched into **one contact sheet**, left to right, to keep image cost down.
5. A control set of 12 scene/keyframe frames is kept as a baseline.
6. The run writes `testing.json` (cues, frame paths, proposed new terms) and a label skeleton.
7. Claude Reads each sheet and records a verdict per offset in `training/labels/<video-id>.json`,
   plus the best offset for each cue.
8. `uv run agent-skills train report` rolls all labels up into term and offset scores.
9. Frames and downloads are cleared on request with `uv run agent-skills clean`.

Cue selection is round-robin by term (every term gets its first cue before any term gets a second;
tickers take 3 slots per round and are one cue per distinct ticker). The first run showed why: with a
100-frame cap (17 cues) tickers got a single cue.

Settings: `--testing-cap` (total frames, default 150, about 27 cues at 5 offsets),
`--testing-offsets` (e.g. `-2,0,3,6,10`).

## Labeling
Claude labels by default; the user overrides any verdict that looks wrong.

| Verdict | Meaning |
|---|---|
| `new-info` | Shows something the captions could not give: real ticker, price, level, chart state |
| `useful` | Relevant to what was said, but the transcript already covers it |
| `redundant` | Same as a frame already seen |
| `blank` | Transition slide or empty screen |
| `wrong` | A different chart or unrelated screen |

A term **hits** when at least one of its offsets is `new-info` or `useful`. Offsets are scored by how often
they are good and how often they are picked as best.

## Offset experiment
The offset is not guessed; it is measured. Five offsets on every cue, then compare. Expect it to differ by
category (a chart page may need longer to load than a spoken ticker). Once a clear winner emerges, drop to
3 offsets to save tokens, and later consider a per-category offset.

## Decision rules (to confirm as data arrives)
- Prune a term after at least 5 labeled cues if its hit rate is under 30%.
- Promote a proposed term (ticker or repeated phrase) after the user approves it.
- Merge cue frames closer than about 5 s so two cues do not produce near-identical frames.
- Treat the control hit rate as the bar: a cue category is only worth keeping if it beats scene detection.

## Open questions
- Is a fixed offset enough, or does each category need its own?
- Does the cue approach still work on videos with no captions (Whisper transcripts have different timing)?
- Can tickers be extracted reliably from a frame (OCR) so captions matter less?
- Should the final mode replace scene detection or sit beside it?

## Log
- Video 1 labeled (`JKXovvYSh9U`, 27 cues, sheet-level verdicts, control frames not yet viewed):
  - Best offset is +0 or +2 for screen switches (6 cues each). The screen lags the spoken cue by about 2s.
    +4/+6 only won twice, and look good in the totals only because screens persist after a switch.
  - Strong terms: pointing phrases (all 5 cues hit), "next one" (new-info), "options chain" (new-info).
  - Ticker cues hit 4 of 6 but only 1 showed new info. Value depends on whether the ticker is the subject
    ("next one is CRDO") or a passing mention (JP, QQQ, VIX, ASML). Passing mentions were not visual cues.
  - Weak: "all-time high" (0 of 2), VIX (0 of 1), "strike" (1 of 2).
  - Cues within ~5s produced duplicate sheets (c02/c03, c05/c06), so the merge rule is confirmed.
  - Contact sheets are too small to read text, so new-info could not be confirmed on most cues.
  - Next changes to try: merge cues within 5s, offsets -1/0/+2/+4 (drop -2), ticker cues only after
    "next one"/"let's talk about", and 3 larger tiles per sheet.
- Videos 2-7 labeled (6 more videos, 7 total, 154 cues, 770 cue frames, 84 control frames). Four are the same creator
  and format as video 1; one is a different creator doing a static screen share; one is a produced video with b-roll.
  Control frames were labeled for all seven from a 4x3 grid.
  - Cue frames vs control, per frame: 69% good vs 54% good. Cue frames beat control in 6 of 7 videos.
    New-info share is lower for cue frames (10% vs 17%): scene changes often land on data cards, cues land on
    whatever is on screen. So cues win on relevance, not on information density. Caveat: control is 12 frames
    per video, clustered in the promo intro, and every verdict is a single labeler.
  - Offsets: of 46 cues where the screen changed after -2, the first good offset was +0 (16), +2 (21), +4 (9).
    Best offset picked: +2 (24), +0 (19), +4 (12), +6 (1), -2 (1). Suggested set: 0, +2, +4 (drop -2 and +6).
    Two slide cues ("VIX Levels" slide) were already on screen at -2, so a few cues may want an earlier look.
  - Strongest terms (per frame): inflation-data and moving-average (100%), chart (88%), as-you-can-see (80%, 16% new-info),
    strike (73%, 22% new-info), next-one (4 cues, 75% new-info). Weakest: lets-dive (35%), VIX (46%), look-here (56%).
  - Tickers: 41 cues, 72% good per frame, but only 10 cues showed new info. Many "tickers" are acronyms
    (PMI, PCE, BLS, AAA, COVID, AGI, MIT, CEO). Add them to the stoplist.
  - Noise: 14% of cue frames were wrong-screen, 9% blank, 7% redundant. Several cue pairs share a timestamp
    (same sentence matching two terms) and give duplicate sheets.
  - Format matters: static screen shares give identical frames at every offset (offset is irrelevant there);
    the produced b-roll video had 40% new-info on cue frames and 0% on control (on-screen stat overlays).
  - Process: downloads can 403 intermittently right after the captions request (retry added to download.py);
    sheet tiles are too small to read, so `new-info` was only marked where text was legible.
- First test video: `JKXovvYSh9U` (Options With Ryan). Ground truth from frames: AAT = AMAT, COR = COHR,
  Amcor = AMKR. His watchlist sidebar was only visible in frames.

## Creator tracking (training only)
- Each label file records the video's creator (`creator`, from the video details). It is stored for training only;
  normal `/watch` reports and the watch-output folders do not use it.
- `uv run agent-skills train report` now adds a "terms by creator" table, and `--creator "<name>"` scores one
  creator's videos on their own. Purpose: when a creator's next video arrives, we can check how well the keyword
  list that was built from their earlier videos performs on it.
- Creators so far: Options With Ryan (5 videos), Jeremy Lefebvre Makes Money (1), Ticker Symbol: YOU (1).

## Fewer approval prompts
- Cause: `.claude/settings.json` only pre-approved Bash commands, so the PowerShell `uv run ...` commands, the
  inline Python used to write labels, and edits to label/plan files each asked for approval.
- Labels are now applied with `uv run agent-skills train label training/specs/<video-id>.json`, so no inline
  Python is needed. Verdict specs are kept in `training/specs/` as a record.
- Proposed narrow allow rules plus a deny list for destructive commands are in `permissions-proposal.json`
  (not applied: editing the permission file was blocked, so it needs to be applied by the user).

## Training run steps (current)
1. `uv run python .agents/skills/watch/scripts/watch.py "<url>" --testing --resolution 1024 --no-whisper`
   (videos land in `watch-output/video-data/<video-id>/`; `transcript.txt` is saved beside the frames).
2. Read each contact sheet and the control grid, then write the verdicts to `training/specs/<video-id>.json`.
3. `uv run agent-skills train label training/specs/<video-id>.json` applies the labels and rebuilds
   `training/training-log.md` (one entry per video: creator, settings, scores, link to the summary).
4. Write the video's summary to `summaries/<video-id>-<short-title>.md` (outside watch-output, never touched by
   the cleaner), then run `uv run agent-skills train log` again so the entry links it.
5. `uv run agent-skills train report [--creator "<name>"]` for scores. `uv run agent-skills clean --all` when
   frames and downloads are no longer needed (labels, specs, the log and summaries are kept).

## Decisions
- Training-process changes (offsets, cue merging, stoplist, term weights, scene frames, tile size) are on hold
  until there is a larger set of videos. Current suggestions are in the findings above.
