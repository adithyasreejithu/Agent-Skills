# Plan: Instagram reels pipeline (discover → queue → transcribe → batched summaries → reels brief)

## Status (2026-10-22)
Built: sections 2-5, 7, 8 (`igweb.py`, `ig_poll.py`, `reelstore.py`, `reel_fetch.py`, `reels.py`, `reel_brief.py`,
`reels_cli.py`, `reel-prompt.md`, `reel-brief-prompt.md`), tests in `tests/ingest/test_reels.py`. Vetted creators
(from `Instagram-Channels.txt`) are in `queue/reel-sources.toml`: wealthbychristy, andre.invests, stockswithjonah,
mo.invests, jointhe535. Not started: the trial itself (section 6) and `reel-types.toml`, which come from its data.

What live testing changed:
- **Logged out, a profile shows only its latest 12 reels, and scrolling loads no more.** The page embeds each
  reel's code, play count and pinned flag but no date, so dates and captions come from one yt-dlp lookup per
  new reel (that works logged out). The network-JSON route in section 2 only applies with a login.
- **That breaks the 30-day backfill for busy creators.** stockswithjonah posted 12 reels in about 3 days
  (2026-10-19 to 21). Logged out, the trial therefore has to be collected *forward*: one poll a day for 30 days,
  each catching what is new. The alternative is a logged-in session (`INGEST_IG_STORAGE_STATE`, a spare
  account), which the code supports but which is not set up.
- First real batch (3 reels, open types): one call, $0.072 ($0.024 a reel); Gemini used about 500-1,000 tokens
  a reel; the transcripts take about 1 KB each and no audio is kept. Types it chose: stock-pick, trade-alert,
  no-speech (a reel of song lyrics). Batches of 15 should cost less per reel; the trial measures it.
- `reel_fetch.py` runs as its own process: watch and ingest both have a `config` module.

**Logged-in mode (added 2026-10-22, for the 30-day trial).**
- **Login:** `reels login` opens a visible browser and the user logs in to a burner account by hand; the
  password is never seen or stored. The persistent browser profile lives in `~/.config/ingest/ig-profile/`,
  together with `ig-session.json`, which records the login window's user agent.
- **Polling:** polls reuse that profile and user agent and scroll the reels tab. API answers carry each reel's
  date, caption and length, so yt-dlp lookups are skipped.
- **Pacing:** read-only visits to the vetted profiles only; 4-9 s between profiles and 2.5-6 s between scrolls.
  A normal day scrolls at most 4 times per creator; the trial scrolls at most 25 and stops as soon as it is
  30 days back.
- **Pushback:** a challenge or checkpoint page, `feedback_required`, "Try again later", HTTP 429 or a login
  redirect stops the run at once with no retry and starts a 48-hour cooldown. Warnings are read from the
  page's visible text, not the raw HTML, because script bundles may quote them.
- Downloads and yt-dlp lookups never use the login.
- **Not yet tested live:** no login has been saved yet. The first logged-in run should be a
  `--dry-run --user <one creator>`.

## 1. Context
Videos from YouTube already flow through `run.py tick`: an RSS poll, the folder queue (`store.py`), one `claude -p`
agent per video, and a morning brief. Instagram was shelved (`plan/video-ingest/SHELVED-instagram.md`) because the
Graph API can't read personal accounts. The user has confirmed public profiles open without a login (tested in
incognito), so discovery can be a headless browser walking a **vetted list of creators**.

Reels are short and numerous, so the YouTube design (one agent run and one ~5 KB note per item) would be costly
and leave thousands of tiny files. Instead:
- Python does everything deterministic: discovery, download, and Gemini audio transcription.
- Claude only writes. One `claude -p` call **with no tools** summarizes a batch of reels.
- Summaries live in **one file per creator per month**, rebuilt from a single JSONL index.
- A separate **reels brief** is written for now. A later step merges it into the YouTube brief as a second section.
- A **1-month trial backfill** finds out which reel types exist. Each type then gets its own note structure.

Decisions already made: types come from the trial; the browser runs logged out; storage is per creator per month;
summaries are written by Python plus batched `claude -p`.

---

## 2. Discovery: headless browser on vetted creators
**New file `.agents/skills/ingest/scripts/igweb.py`** (Playwright, Chromium, headless, logged out).
- `discover(username, since, max_scrolls=15) -> list[Candidate]`
  1. Open `https://www.instagram.com/<username>/reels/`.
  2. Read both layers:
     - **Network JSON**: listen to `page.on('response')` and parse any JSON body (`web_profile_info`,
       `graphql/query`, `clips/user`) for objects carrying `code`/`shortcode` and `taken_at`/`taken_at_timestamp`.
       This gives the shortcode, publish time, caption, `video_duration`, view count and pinned flag.
     - **DOM fallback**: `a[href*="/reel/"]` anchors give the shortcode only. The date is filled later from
       yt-dlp metadata.
  3. Scroll until **3 consecutive non-pinned items** are older than `since`, there are no new items after 2
     scrolls, or `max_scrolls` is reached. Pinned reels show first with old dates, so a single old item must not
     stop the scroll.
  4. Spot a login wall or "page isn't available" from the URL (`/accounts/login`) or page text, and return
     a typed error (`LoginWall` / `NotFound`) instead of an empty list.
- Politeness: one browser for the whole poll; a random 4-9 s gap between profiles; a normal desktop UA and
  viewport; no parallel tabs; one poll a day. The terms-of-service grey area from the shelved doc still applies and
  is restated in SKILL.md.
- Later fallback, not built now: `INGEST_IG_STORAGE_STATE`, a Playwright `storage_state` JSON in
  `~/.config/ingest/`, used only if login walls start appearing.
- `Candidate` = `{shortcode, url, username, taken_at, caption, duration_s, views, pinned, via: json|dom}`.

**`urls.py`** gains `extract_reel_code(text)` (accepts `instagram.com/reel|reels|p/<code>/`, with or without
query or `www`) and `reel_url(code)`. The YouTube functions are untouched.

**Vetted list: new `<home>/reel-sources.toml`**, kept separate from `sources.toml` so YouTube polling can never
break on it:
```toml
[defaults]
priority = 50
max_age_days = 3        # normal daily poll; the trial overrides this with --days 30
min_duration_s = 8      # skip near-empty clips
max_duration_s = 180

[[creator]]
username = "somecreator"
name     = "Some Creator"
tags     = ["options"]
# enabled = false
```
`config.py` gets `ReelSource` plus `load_reel_sources(path)`, built like `load_sources` and reusing
`_int`, `_bool` and `ConfigError`.

**New file `ig_poll.py`**: `poll_reels(store, sources, browser, now, days=None, only=None, dry_run=False)`.
It mirrors `poll.py`:
- New shortcodes go to `pending/` with `origin='ig'`, `video_id=<shortcode>`, `channel_name=<name>`, `username`,
  `published_at`, `caption`, `duration_s`.
- Out-of-range items go to `skipped.jsonl` with a reason: `too_old`, `too_short`, `too_long` or `pinned_old`.
- Per-creator `fail_count` and last poll are kept in `state.json` (reusing `Store.load_state`/`save_state`).

## 3. Queue and storage
**Queue: reuse `Store` unchanged** on its own state root, `<home>/reels/`, via `Paths` with `state=home/reels`.
That gives reels their own `pending/`, `processing/`, `failed/`, `run.lock` and `QUEUE.md`, and keeps the reels
lock separate from YouTube's.
- **No `done/` manifests for reels.** Done means "has a line in `reels.jsonl`", so finished reels leave no
  per-item file. `known_ids()` for reels = queue stems + skipped + the JSONL shortcodes. A small `ReelStore`
  subclass in `reels.py` overrides `noted_ids()`, since the base class reads 11-character YouTube ids from
  filenames.

**Raw data (transcripts)**: `<raw>/reels/<username>/<YYYY-MM>.transcripts.jsonl`, with one line per reel:
`{shortcode, taken_at, caption, duration_s, segments:[{start,end,text}], speech: bool, gemini_usage}`.
The audio file is deleted as soon as the transcript is written, so there is no media on disk.

**Summaries, the source of truth**: `summaries/reels/reels.jsonl`, one line per reel:
```json
{"shortcode":"DXyz123","username":"somecreator","creator":"Some Creator","taken_at":"2026-10-21T14:02:00Z",
 "ingested_at":"…","url":"https://www.instagram.com/reel/DXyz123/","duration_s":48,"type":"stock-pick",
 "one_line":"…","tickers":["CRDO"],"stance":"bullish","points":["…"],"levels":["CRDO buy under 120"],
 "fields":{…type-specific…},"evidence":"transcript+caption","batch":"2026-10-22T07:05Z#3"}
```
**Readable view (generated, never hand-edited)**: `summaries/reels/<username>/<YYYY-MM>.md`. It's rebuilt from
the JSONL for every month the run touched, newest first. One entry is about 5-8 lines:
```
### 2026-10-21 · stock-pick · [DXyz123](https://www.instagram.com/reel/DXyz123/) · 0:48
**CRDO** · bullish — One-line summary of the reel.
- point one
- Levels (as stated): CRDO buy under 120; target 150
```
Promo, lifestyle and no-speech reels get a single line with no bullets. Rendering is deterministic Python
(`render_month()`), so re-runs never duplicate entries. The JSONL is updated in place by shortcode.

## 4. Fetch and transcribe (deterministic, no agent)
**New file `reels.py`**, with `fetch_one(item, paths, transcriber=gemini_transcriber)`:
1. **Download audio**: watch's `download.download(url, out_dir, audio_only=True)`
   (`.agents/skills/watch/scripts/download.py:210`). It already uses `runtime.find_tool` for the venv's
   yt-dlp. The yt-dlp metadata also fills `taken_at` and `caption` for DOM-only candidates.
2. **Transcribe**: `gemini.transcribe_audio(path, key, model=WATCH_GEMINI_MODEL, duration=…)`
   (`watch/scripts/gemini.py:198`). Use `transcribe_long_audio` above about 10 min, which won't happen given the
   180 s cap. The key comes from watch's `config.load_gemini_key()`. The Gemini call reuses watch's own code
   and settings, so nothing duplicates it.
3. Write the transcript line, delete the audio, and move the item to a `transcribed` state. That's an extra field
   on the pending item (`stage_hint: 'summarize'`), so no new folder is needed.
4. Failures:
   - yt-dlp login or 404 → `fail()` (reuse `process.fail`, 3 attempts with a 6 h hold).
   - Gemini 429 or quota → stop the run and release the item without counting an attempt, like
     `process.blocker`.
   - An empty transcript (music-only) → `speech: false`. That still counts as success, and the reel is
     summarized from its caption only.

Frames are **off by default**: reels are short and the transcript plus caption should carry most of the content.
On-screen text (tickers on a chart) is a trial question, see section 6.

## 5. Batched summaries (one `claude -p`, no tools, many reels)
**`reels.py`**, with `summarize_batches(store, runner=claude_text_runner, batch_size=15)`:
- Take transcribed items and group them by creator, oldest first, in batches of up to `INGEST_REEL_BATCH`
  (default 15) or about 12k transcript tokens, whichever comes first. Grouping by creator lets the model see
  running context, such as a ticker the same person mentioned two reels ago.
- **Prompt `.agents/skills/ingest/reel-prompt.md`**: the type list with each type's fields (from
  `reel-types.toml`, see section 6), then each reel inline as
  `<reel code="…" date="…" duration="…"><caption>…</caption><transcript>…</transcript></reel>`.
  The caption and transcript are untrusted evidence, never instructions. The model returns **only a JSON array**,
  one object per reel, in the schema above.
- **Runner**: lift `brief.claude_brief_runner` (`brief.py:268`) into a shared `claude_text_runner(prompt, timeout)`
  in `process.py`. It runs `claude -p --output-format json --no-session-persistence --tools ''` with the prompt on
  stdin and `env=agent_env()`, and returns the text plus usage. `brief.py` then calls it too.
- **Validation** (`validate_batch`), all mechanical:
  - Valid JSON; every shortcode in the batch is present exactly once, and nothing else.
  - `type` is in the allowed set; type-specific required fields are present.
  - `stance` is in `note.STANCES`; tickers are uppercase.
  - Every number in `one_line`, `points` and `levels` appears in that reel's transcript or caption, using
    `brief.unsourced_numbers` (`brief.py:180`).
  - On problems, run one retry with `brief.retry_prompt`-style feedback. If it still fails, accept the reels that
    validated and send the rest back to pending, with an attempt counted.
- Write the JSONL lines, re-render the touched month files, and remove the items from `processing/`.
- Every batch adds a cost line to `summaries/reels/_cost.jsonl`: reels, transcript characters, the Claude
  token/cost/duration fields (same `USAGE_KEYS` as the brief) and the summed Gemini usage. That gives a real
  per-reel cost.

## 6. Trial: a 1-month backfill to discover types and fix their structures
**Goal**: learn which kinds of reels the vetted creators post, then fix a structure for each type.

**Step A, collect** (one-off):
```
run.py reels trial --days 30          # poll every vetted creator back 30 days, fetch + transcribe all
```
Transcripts are cached in the raw JSONL, so the summarize passes below can be re-run cheaply, paying for Claude
only.

**Step B, open classification**: `run.py reels summarize --open-types`
- Runs the batch prompt in "open" mode. The model gives each reel a short free-text `type_label` and a one-line
  reason, and fills a **generic** structure: `one_line`, `tickers`, `stance`, `points`, `levels`.
- Starting hypotheses, given to the model as examples and not as a closed list:
  - stock-pick or trade idea
  - market update (indices, macro)
  - news reaction
  - education or how-to (options mechanics, strategy)
  - portfolio or P&L update
  - promo or lifestyle
  - no speech

**Step C, report**: `run.py reels trial-report` writes `plan/reels/TRIAL.md` with:
- Per type label: count, share, creators, median duration, share with tickers, share with numbers or levels,
  and 3 example one-liners.
- Per creator: reels per week and their type mix.
- Cost: Gemini and Claude per reel, per batch size. Re-run step B once with batch sizes 5 and 25 on the same
  reels to pick the default.
- Speech: the share of no-speech reels and of caption-only reels.

**Step D, freeze the taxonomy** (user decision, recorded in `.agents/skills/ingest/reel-types.toml`):
- Proposed rules:
  - A type needs at least 5% of reels or at least 5 reels, otherwise it merges into its nearest neighbour or
    `other`.
  - Promo, lifestyle and no-speech reels get a one-liner only and are left out of the brief.
- Per type:
  - `fields`: for example stock-pick → `ticker, action (buy/sell/hold/watch), levels, timeframe, thesis`;
    market-update → `indices, levels, macro_drivers, outlook`; education → `topic, takeaway`.
  - `brief: include | count-only | skip`
  - `max_points`
- These are filled in from the trial data, not guessed now.

**Step E, re-summarize with the fixed structures**: `run.py reels summarize --redo --since 30d` rewrites the
JSONL from the cached transcripts. Spot-check about 20 reels against the transcripts.

**Trial questions to answer in TRIAL.md**:
- Does on-screen text matter? On 20 reels flagged by the model as "refers to something on screen", grab 3 frames
  and compare. If it matters, add a `frames` option per type.
- The batch size with the best cost and validation-pass trade-off.
- Whether `max_age_days` should be 2 or 3 for daily polling, given how often each creator posts.

## 7. Reels brief (separate for now)
**New file `reel_brief.py`**. It reuses `brief.py` building blocks (`local_day`, `unsourced_numbers`,
`retry_prompt`, `log_cost`'s pattern, the shared `claude_text_runner`) but takes JSONL entries, not note files.
- Batch: reels whose `ingested_at` falls on the local day, with types marked `brief: include`. Types marked
  `count-only` show only a count per creator.
- The input is the compact JSON entries, not transcripts, so the prompt stays small.
- **Prompt `reel-brief-prompt.md`**, output to `summaries/_briefs/<date>.reels.md`:
  ```
  ---
  date / reels: N / creators: [...] / generated: claude|fallback
  ---
  # Reels brief 2026-10-22
  ## Short read          3-5 bullets, <=120 words
  ## By creator          ### <Creator>: one line per included reel, grouped by type
  ## Tickers mentioned   Ticker | creators | action | levels as stated
  ## Reels               mechanical list: date · type · link (like the brief's "Videos" list)
  ```
- Validation: the section checks, bullet count, word cap and the number check (same rules as
  `validate_brief`, smaller limits). If those fail, the fallback is a mechanical brief, as in
  `brief.fallback_body`.
- **Future merge** (not in this work): `brief.py` gets an optional reels batch, and `## Long read` gains a
  `### Reels` section. `<date>.reels.md` then goes away. The JSONL entries are built so they can be inlined
  directly when that happens.

## 8. CLI: `run.py reels …` (a new sub-command group in `run.py`)
```
run.py reels init                                 create <home>/reels/ and a starter reel-sources.toml
run.py reels source list | add USER [--name N] [--priority P]
run.py reels poll   [--user U] [--days D] [--dry-run]        headless browser -> pending
run.py reels add URL... [--now]                   manual reel links (also <home>/reels/inbox/*.txt)
run.py reels fetch  [--limit N]                   download audio + Gemini transcript
run.py reels summarize [--limit N] [--batch-size B] [--open-types] [--redo --since 30d] [--dry-run]
run.py reels process [--limit N] [--budget-min M] [--log]     fetch + summarize
run.py reels tick   [--log]                       poll + process + reels brief (for the scheduler)
run.py reels brief  [--date YYYY-MM-DD] [--dry-run]
run.py reels trial  --days 30                     backfill poll + fetch for every vetted creator
run.py reels trial-report                         write plan/reels/TRIAL.md
run.py reels render                               rebuild every month file from reels.jsonl
run.py reels status | list [--skipped] [--json]
```
`--dry-run` on `summarize` and `brief` prints the prompt and calls nothing, as for YouTube. Scheduling comes after
the trial: either `schedule.py install --name ingest-reels` with `reels tick`, or a step at the end of the
YouTube `tick`. The user decides once the costs are known.

## 9. Config and dependencies
- `ingest.env` / `config.py` new keys:
  - `INGEST_REELS_STATE_DIR` (default `<home>/reels`)
  - `INGEST_REEL_NOTES_DIR` (default `<notes>/reels`)
  - `INGEST_REEL_SOURCES_FILE` (default `<home>/reel-sources.toml`)
  - `INGEST_REEL_BATCH` (default 15)
  - `INGEST_IG_HEADFUL` (debug: show the browser)
  - `INGEST_IG_STORAGE_STATE` (optional, unused unless login walls appear)
- Gemini key and model stay in watch's `~/.config/watch/.env` (`GEMINI_API_KEY`, `WATCH_GEMINI_MODEL`).
- `pyproject.toml`: add `playwright`, then `python -m playwright install chromium` once (documented in SKILL.md).
  `igweb.py` imports Playwright lazily, so the YouTube pipeline and its tests don't need it.

## 10. Files
- **New**:
  - `scripts/igweb.py`, `scripts/ig_poll.py`, `scripts/reels.py` (ReelStore, fetch, summarize, render, trial
    report), `scripts/reel_brief.py`
  - `reel-prompt.md`, `reel-brief-prompt.md`, `reel-types.toml` (after the trial)
  - `plan/reels/PLAN.md` (a copy of this plan, per repo convention)
  - `tests/ingest/test_reels_*.py`
- **Changed**:
  - `scripts/run.py` (the `reels` subparser)
  - `scripts/config.py` (ReelSource, new paths)
  - `scripts/urls.py` (shortcodes)
  - `scripts/process.py` (shared `claude_text_runner`)
  - `scripts/brief.py` (uses the shared runner)
  - `SKILL.md` (commands, settings, ToS note)
  - `plan/video-ingest/SHELVED-instagram.md` (status: superseded by `plan/reels/`)
  - `pyproject.toml`

## 11. Tests (no network, no model; fakes like `tests/ingest/_fakes.py`)
- `urls`: reel, reels and p links, with or without query and www → shortcode; YouTube links are rejected.
- `igweb`: run the JSON parser over saved response fixtures (profile info, graphql page) → candidates. Pinned old
  items don't stop the scroll; 3 consecutive old ones do. Login-wall HTML raises `LoginWall`.
- `ig_poll`: new, known and skipped are handled; the age, duration and pinned filters work; `fail_count` goes up
  on errors.
- `reels.fetch_one` with a fake downloader and transcriber: the transcript line is written, the audio deleted,
  no-speech is marked, a 429 releases the item without counting an attempt.
- `summarize_batches` with a fake runner:
  - valid JSON → JSONL lines plus a rendered month file;
  - a missing shortcode, a bad type or an invented number → one retry, then partial accept;
  - re-running doesn't duplicate entries.
- `render_month`: deterministic output, newest first, promo reels on one line.
- `reel_brief`: the day batch uses local time, `count-only` and `skip` types are respected, the fallback works.
- The shared `claude_text_runner` keeps `test_brief` passing.

## 12. Verification
1. `python -m unittest discover -s tests/ingest` and `-s tests/watch` pass.
2. `run.py reels source add <user>` for 2 vetted creators, then `run.py reels poll --days 7 --dry-run`. Check the
   shortcodes and dates by eye against the profile in a normal browser.
3. `run.py reels fetch --limit 3`: transcripts appear in the raw JSONL and no audio is left behind.
4. `run.py reels summarize --dry-run` prints a sensible batch prompt. A real `summarize` then writes JSONL lines,
   a month file and a `_cost.jsonl` line.
5. `run.py reels brief --date <today>` writes `summaries/_briefs/<date>.reels.md`. Spot-check its numbers against
   the transcripts.
6. Run the trial (section 6, steps A-E) on the full vetted list. Review `plan/reels/TRIAL.md` with the user, then
   freeze `reel-types.toml`.

## 13. Risks
- Instagram changes its markup or JSON. Parsing is isolated in `igweb.py` with fixtures. A creator returning 0
  reels for 3 polls in a row raises a `failing creator` warning in `status`.
- Login walls on logged-out sessions. The fallback is the saved `storage_state` (section 2), off by default.
- Terms of service: scraping and downloading is a grey area (see the shelved doc). Keep it to a small vetted list,
  one poll a day, and audio only, deleted after transcription.
- Gemini timing and quality on music-heavy reels. The trial measures the no-speech share.
