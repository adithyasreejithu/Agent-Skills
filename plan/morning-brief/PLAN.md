# Plan: daily morning brief (short read + long read)

## Context
Each morning's `tick` writes one note per video plus `summaries/_digests/<date>.md`, which is only a list of
links with stance and tickers. To learn what was said you still have to open every note (~5,000 characters
each; 13 videos came in on 2026-10-21). The goal is one Markdown file per day with:
- a **short read** to skim on the fly (Option A, chosen by the user: ~1 min, 5-7 bullets);
- a **long read**: longer, but still a compact summary.

Claude writes it, as it writes the notes. It **replaces** the digest. The "compare with the creator's earlier
videos" feature gets built both ways, both versions run on the same days, and the user picks after seeing the
token cost and the output.

## What the analysis of the 14 queue notes showed (drives the content)
- Two creators, 7 notes each. Stance is `bullish` in 11 of 14 and never `bearish`, so stance alone tells you
  little. The useful signal is **trades, levels, and what changed**.
- The creators rarely overlap (only AXP and AMZN appear in both), so an "agree/disagree" section is usually
  short. It is kept, and it says "none" when empty.
- The same gauges come up again and again: oil 13/14, 10-year 12, S&P 12, QQQ/Nasdaq 12, VIX/VXN 11, cash level
  10, earnings dates 10, Fed odds 9, SMH 8, breadth 7, CPI 7. This becomes the fixed **market dashboard** in the
  long read.
- Noise to leave out: promotions (13/14), account-value flexes, most caption fixes (8/14). Guest/CNBC views
  (7/14) are kept but always attributed, never presented as the creator's view.
- Every note has a positions table, and the verbs are consistent: holds, wants, cash-secured puts, buying,
  LEAPS, selling, sold. So positions can be normalised to *new / added / holding / trimmed / sold / eyeing*.
- Older notes without frontmatter (the earlier wiki pipeline) are ignored. Only `queue/done/` manifests count.

## Brief format: `summaries/_briefs/YYYY-MM-DD.md` (local date of the run)
```
---
date: 2026-10-22
videos: 2
channels: [Options With Ryan, Jeremy Lefebvre Makes Money]
history: true|false          # which variant wrote it
generated: claude|fallback
---
# Morning brief 2026-10-22

## Short read
<5-7 bullets, <=180 words: Mood · Buying · Holding/income · Levels · This week · Changed (history only)>

## Long read
### Market dashboard     table: gauge x creator (S&P, QQQ, 10Y, oil, VIX/VXN, Fed odds, breadth, cash %)
### <Creator>            one block per creator: stance + thesis (2-4 sentences), then a table:
                         Ticker | Action (new/added/holding/trimmed/sold/eyeing) | Levels as stated
### Where they agree or differ
### What changed since their last video      (history variant only)
### Calendar             dated events and earnings they named
### Caveats              guest views, on-screen-only data, low-evidence items

## Videos
- **Channel**: [title](../<note>.md) (stance; tickers)   <- the old digest line, unchanged
```
Long read target: 600-1,000 words (~4-5 min). The prompt includes the Option A example shown to the user.

## Implementation
1. **`.agents/skills/ingest/scripts/brief.py`** (new). It mirrors `process.py`'s style, with an injectable runner
   so tests need no model:
   - `day_batch(store, day)`: `done` manifests whose `ingested_at`, converted to local time, falls on `day`.
     This fixes the digest's UTC naming, where an 8:34 PM run went into the next day's file. Reuses
     `store.find`/manifest reading and `note.split_frontmatter`.
   - `history_notes(store, channel, before)`: that creator's most recent earlier note outside the batch.
   - `build_brief_prompt(template, notes, history)`: puts the note bodies inline, dropping the "Stored data"
     lines, so the call needs **no tools**.
   - `claude_brief_runner(prompt)`: `claude -p --output-format json --no-session-persistence` with no tools
     allowed, prompt on stdin (same reason as `process.claude_runner`), `env=process.agent_env()`. Parses
     `result`, `usage` (input/output/cache tokens), `total_cost_usd` and `duration_ms`.
   - `validate_brief(text, batch)`: frontmatter keys; `## Short read` with 5-7 bullets and <=180 words;
     `## Long read` with the dashboard, a section per creator, and the calendar; `## Videos` linking every
     note in the batch. **Number check:** every number in the short read must appear in some source note, which
     catches invented levels. Counts up to 10 are exempt.
   - `fallback_brief(batch)`: mechanical version with frontmatter `generated: fallback`. The short read is
     one line per creator (stance and tickers), the long read is skipped, and `## Videos` is still written.
     Used when the call fails or fails validation twice.
   - `write_brief(store, day, history, runner)`: re-writes the whole day's file, so a second run that day
     includes all of that day's videos. Appends one line of cost data to `summaries/_briefs/_cost.jsonl`.
2. **`.agents/skills/ingest/brief-prompt.md`** (new): the instructions above, the Option A example, and the
   rules: no advice, numbers only from the notes, guest views attributed, promotions left out.
3. **`run.py`**: `tick` calls `write_brief` instead of `write_digest` when anything finished. New subcommand
   `brief [--date YYYY-MM-DD] [--history|--no-history|--both] [--dry-run]`. `--both` writes
   `<date>.md` and `<date>.history.md` and prints a token/cost comparison table.
4. **`config.py`**: `briefs` path (`INGEST_BRIEFS_DIR`, default `<notes>/_briefs`) and
   `INGEST_BRIEF_HISTORY` (the default is set after the experiment).
5. **Remove the digest**: delete `process.write_digest` and its test, and drop the import in `run.py:32`.
   Keep the existing `summaries/_digests/` files.
6. **Docs**: `ingest/SKILL.md` (commands, settings, description), `plan/video-ingest/PLAN.md` (Digest
   section becomes Brief), and a copy of this plan at `plan/morning-brief/PLAN.md` (repo convention).

## Token experiment: history vs no history (user asked to run both and compare)
Run `run.py brief --both` on two real days:
- **2026-10-21** (13 videos, ~65k characters of notes);
- **2026-10-22** (1 video, so history matters most here).

The output is a table per day: input tokens, output tokens, cost, duration, and whether validation passed,
for each variant. Expected extra cost of history: one earlier note per creator (~1.3k tokens each), so
**roughly +3-5% on a big day** and **about double on a one-video day**. The user reads both briefs side by side,
then picks the default for `INGEST_BRIEF_HISTORY`. The unused variant stays available as a flag.

## Tests: `tests/ingest/test_brief.py`
- The local-date batch puts an 8:34 PM EDT run on its own day.
- History picks the same creator's previous note and never one from the batch.
- The validator rejects: 4 or 8 bullets, more than 180 words, a short-read number not in any note, a missing
  video link, a missing creator section.
- When the runner fails or produces an invalid brief, the fallback file has `generated: fallback`.
- A second run on the same day re-writes the file to include both runs' videos, with no duplicates.
- `tick` writes a brief and no digest. Existing `test_process` digest tests are removed or rewritten.

## Verification
1. `python -m unittest discover -s tests/ingest` and `-s tests/watch` pass.
2. `run.py brief --date 2026-10-21 --dry-run` prints the prompt (no model call).
3. Run the token experiment above, then check both files by eye against the source notes, including a
   spot-check that the short read's numbers appear in the notes.
4. Run `run.py tick --log` through the scheduler-environment script from the yt-dlp fix
   (`scratchpad/sched_env.ps1`). Confirm `run.log` names the brief path and that `_cost.jsonl` gets a line.
