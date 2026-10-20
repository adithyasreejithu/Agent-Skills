# Video Summary Wiki: Plan and Format Proposal

Status: proposal, not built. Open questions are listed at the end; defaults are stated so work can start
without waiting on them.

## Goal
Turn each `/watch` video into a structured, traceable note that gives a fast overview of what was said, the
analysis behind it, and what to check, and store it in a plain-markdown wiki that an LLM can keep up to date
(Karpathy "LLM wiki" pattern). Notes must also be machine-readable so cross-video views (ticker index,
predictions ledger, weekly digest) can be built from them.

## Scope
| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Calls table (action, levels, horizon, rationale) | 1 | core |
| 2 | Thesis vs evidence, split into Verified and Not verified sections | 1 | core, pilot first |
| 3 | Key numbers and levels | 1 | core |
| 4 | Timestamped outline; every major point carries a traceable timestamp | 1 | core |
| 5 | Overall bias and risk posture | 1 | core |
| 6 | Disclosures and conflicts | 1 | core |
| 7 | YouTube metadata (description, chapters, tags, counts, pinned comment) | 1 | core |
| 9 | Ticker normalization (alias map, canonical tickers) | 3 | planned addition; manual alias map from phase 1 |
| 11 | Running ticker index | 4 | test run |
| 12 | Predictions ledger | 4 | test run |
| 13 | Weekly digest | 4 | test run |

Not in scope for now: OCR of frames (idea 8). Phase 1 can use frames the way the current summaries do (read by
Claude, cited by cue id). OCR is a later optional input to verification.

## Design principles
1. **Every claim is traceable.** Anything in a calls table, claims list, number list or outline has a timestamp
   that links to the exact moment (`https://youtu.be/<id>?t=<seconds>`), or a frame reference when the source is
   a screen. A bullet with no anchor fails lint.
2. **Verification is explicit and honest.** A claim is Verified only if something independent of the creator's
   say-so confirms it. Everything else stays in Not verified, with a reason. We never promote opinions or
   forecasts to Verified.
3. **One source of truth per video.** A structured YAML sidecar holds the claims, calls and numbers. The readable
   note is rendered from it, so the tables cannot drift from the data and cross-video views read the YAML.
4. **Plain markdown, portable.** YAML frontmatter, `[[wikilinks]]`, no plugin-only syntax required. It must open
   cleanly in Obsidian and be navigable by an LLM using only `index.md`.
5. **Raw is immutable, wiki is owned by the LLM, the schema is written down.** (Karpathy three layers.)
6. **Not investment advice.** Notes record what a creator said and what we could check. Wording stays
   attributive ("he says", "he plans"), never "you should".

## Repository layout (default: inside this repo as `wiki/`)
```
wiki/
  WIKI.md                      schema: conventions, vocabularies, rules the LLM follows (also linked from CLAUDE.md)
  index.md                     content catalog, one line per page, grouped by type; first thing an LLM reads
  log.md                       append-only operations log (ingest, verify, lint, digest)
  raw/                         layer 1, immutable
    <video-id>/
      info.json                trimmed yt-dlp metadata (title, creator, description, chapters, tags, counts)
      transcript.txt           captions as downloaded (timestamps preserved)
      testing.json             cue data, if a testing run exists
      frames/                  only the frames cited by the note (small set)
  videos/                      layer 2: one note per video
    2026-10-07-jmpbceo_uh4-emergency-with-1-of-my-stocks.md
  data/
    claims/<video-id>.yaml     structured sidecar: claims, calls, numbers, outline (source of truth)
  creators/<slug>.md
  tickers/<TICKER>.md          index pages (phase 4), aliases from _meta
  themes/<slug>.md             rates, oil, earnings-season, ai-capex, etc.
  ledger/predictions.md        predictions ledger (phase 4)
  digests/2026-W41.md          weekly digests (phase 4)
  _meta/
    ticker-aliases.yaml        spoken name or caption error -> canonical ticker (phase 1 manual, phase 3 grown)
    vocab.yaml                 allowed values for action, stance, kind, status, format
```
`summaries/` is migrated into `wiki/videos/` in phase 2, then kept as redirects (a one-line pointer file) or
removed once links are updated. `training/` and `watch-output/` stay as they are; the wiki only reads from them.

Naming: video notes are `<published-date>-<video-id-lowercase>-<slug>.md` so they sort by date and the id stays
searchable. Tickers are upper case file names. Creators and themes are kebab-case slugs.

## Video note format

### Frontmatter
```yaml
---
type: video
id: JmPBceO_UH4                       # platform video id (case preserved)
platform: youtube
url: https://www.youtube.com/watch?v=JmPBceO_UH4
title: "Emergency with 1 of my stocks"   # cleaned, ASCII, no emoji
creator: "[[creators/financial-education]]"
published: 2026-10-07
duration_s: 2272
ingested: 2026-10-08
format: talking-head                  # talking-head | screen-share | reaction | produced | mixed
language: en
transcript_source: captions-auto      # captions-manual | captions-auto | whisper
tickers: [ELF, AMD, PLTR, META, CELH, RH, WYNN, NFLX, AXP, SOFI]
themes: ["[[themes/rates-and-treasuries]]", "[[themes/consumer-brands]]"]
bias:
  direction: bullish                  # bullish | bearish | mixed | neutral | n/a
  horizon: "3-5y"
  cash_posture: "not stated"          # free text or null; Ryan-style rules go here
  hedging: "none stated"
  confidence_language: high           # low | medium | high (how certain the creator sounds)
disclosures:
  positions_held: [ELF, AMD, PLTR, META, CELH, RH, AXP, NFLX]   # tickers he says he owns
  positions_unknown: []
  promo: [private-group, patreon]     # vocab: private-group, patreon, course, newsletter, affiliate, sponsor
  sponsor_reads: 0
youtube:
  chapters: []                        # [{t: 0, title: ...}] from the creator, empty if none
  tags: []
  views: null
  likes: null
  comments: null
  pinned_comment: null
  description_links: []
verification:
  status: partial                     # none | partial | complete
  checked_on: 2026-10-08
  method: [screen, web]
  counts: {verified: 6, contradicted: 0, partial: 1, unchecked: 9, opinion: 11, forecast: 5}
  follow_ups: 2                       # open items flagged "worth looking into"
  human_reviewed: false               # set true after you spot-check the note
sources:
  raw: wiki/raw/JmPBceO_UH4/
  claims: wiki/data/claims/JmPBceO_UH4.yaml
related: ["[[videos/2026-10-06-11ku7bixa28-this-1-stock-is-changing-investors-life]]"]
tags: [video, finance]
---
```

### Body sections (fixed order, fixed headings)
1. `## TL;DR` : 3 to 5 sentences. What he argues, what he is doing, the main risk.
   Directly under it, `### Worth looking into` lists open follow-ups (reason, next step, priority); omitted if none.
2. `## Bias and risk posture` : rendered from `bias`, plus what he says would change his mind (with timestamp).
3. `## Calls` : table, one row per ticker or instrument.
4. `## Key numbers and levels` : table of every cited figure.
5. `## Analysis: verified` : claims confirmed independently (see verification rules).
6. `## Analysis: not verified` : three sub-lists, `### Unchecked facts`, `### Opinions and forecasts`,
   `### Contradicted or disputed` (empty if none).
7. `## Outline` : timestamped, every major point linked.
8. `## Disclosures and conflicts` : rendered from `disclosures` plus promo moments with timestamps.
9. `## What the frames added` : only information the audio did not carry, cited by frame id.
10. `## Metadata` : description, chapters, links, pinned comment, counts.
11. `## Open questions` : what we could not resolve and what would settle it.

### Anchor syntax
- Timestamp: `[12:34](https://youtu.be/JmPBceO_UH4?t=754)`. Ranges: `[12:34-13:10](...?t=754)`.
- Frame: `(frame c09 +2s)` pointing to `wiki/raw/<id>/frames/c09_+2.jpg`.
- Claim id: `JmPBceO_UH4-c012`, call id `-k03`, number id `-n07`. Ids appear as a trailing `^c012`
  block anchor so other notes can link to `[[videos/...#^c012]]`.
- Non-YouTube sources: plain `[mm:ss]` with no link.

### Calls table
| Ticker | Action | Instrument | Entry / strike | Target | Worst case or stop | Horizon | Creator holds | Why | When |
|---|---|---|---|---|---|---|---|---|---|
| [[tickers/CELH]] | buy (accumulating) | stock | ~26 | n/s | 22 | 3 years | yes | brand volume expected to turn positive in 1-2 quarters | [30:55](...?t=1855) |

Rules: `n/s` means not stated, never guessed. Action vocabulary: `buy`, `add`, `trim`, `sell`, `hold`,
`watch`, `avoid`, `rotate-into`, `rotate-out`, `sell-put`, `sell-call`, `roll`. Prices are as spoken; a
normalized numeric version lives in the YAML.

### Key numbers table
| Number | What it is | As of | Source type | Check | When |
|---|---|---|---|---|---|
| 5.307% | US 10-year yield | 2026-10-06 | screen (CNBC graphic) | verified (screen) | [36:03](...) |

Source type is `spoken`, `screen` or `both`; a number only on screen and not in the audio is flagged, because
the frames are where those come from.

### Claim and verification rules
Claim kinds: `fact` (checkable statement), `number` (a figure), `forecast` (a statement about the future),
`opinion` (judgment), `call` (his stated action), `quote` (reporting what someone else said).

Verification status:
| Status | Meaning | Goes under |
|---|---|---|
| `verified` | Confirmed by an independent source, with source and date recorded | Analysis: verified |
| `verified-screen` | The creator shows a primary source on screen that matches (a brokerage page, a FedWatch table, a filing) and we read it from the frame | Analysis: verified, labelled "screen" |
| `partial` | Some parts confirmed, some not (state which) | Analysis: verified with a caveat, and also listed in unchecked |
| `unchecked` | A checkable fact we have not yet checked | Not verified: unchecked facts |
| `not-checkable` | Opinion, valuation view, personal plan | Not verified: opinions and forecasts |
| `forecast-open` | Dated or checkable in the future; goes to the ledger | Not verified: opinions and forecasts |
| `unverifiable-now` | Checkable in principle but the data is gone or live-only (an intraday level, a live probability, a paywalled report) and no archive exists | Not verified: unchecked facts, with the reason |
| `contradicted` | An independent source disagrees; both recorded (see the process for how this is decided) | Not verified: contradicted or disputed |

What counts as an independent source (default, to confirm): a primary document (filing, earnings release,
exchange or central-bank data page), a reputable data provider page, or a second reputable outlet. A
creator's own screen share counts only as `verified-screen`, since it is still the creator's choice of
evidence. Each check records `method` (`screen`, `web`, `data`), `source` (URL or frame id), `checked_on`, and a
one-line note. Checks use fixed as-of dates, since prices move; a price claim is checked against the close of
the day the video was published.

### Outline
Sections come from the creator's chapters if the video has them (frontmatter `chapters_source: creator`),
otherwise generated from topic shifts. Every major point, not just every section, gets a timestamp:

```
- [00:02](...?t=2) Opens with ELF position, calls 140 the next level ^o01
- [02:34](...?t=154) How he builds a position: never all in one day, 3-6 month span ^o02
  - [03:43](...?t=223) Sizing: 1-2% high risk, 3-7% lower risk ^o03
```
"Major point" means: a thesis, a call, a number that supports a call, a risk, or a change of topic.

## YAML sidecar (`wiki/data/claims/<video-id>.yaml`)
This is the source of truth the note is rendered from.

```yaml
video: JmPBceO_UH4
schema_version: 1
extracted_by: claude-sonnet-5-5
extracted_on: 2026-10-08
transcript_source: captions-auto
outline:
  - id: o01
    t: 2
    text: "Opens with ELF position, calls 140 the next level"
    level: 1
claims:
  - id: c012
    kind: fact                   # fact | number | forecast | opinion | call | quote
    text: "Celsius brand volume fell 20% over four weeks to Sep 19 (Nielsen via Beverage Insights)"
    t: [854, 880]                # start, end seconds
    tickers: [CELH]
    anchors: ["transcript", "frame:c09"]
    priority: P1                 # P1 verify now | P2 verify if cheap | P3 record only (see Verification process)
    checkable: true
    material: true               # feeds a call, a key number, or a thesis pillar
    verification:
      status: unchecked
      method: null               # screen | web | data | arithmetic
      source_tier: null          # T1 primary | T2 reputable data or news | T3 other (never enough alone)
      source: null               # URL or frame id; a list when two sources were needed
      as_of: null                # the date the fact should hold for (publish date by default)
      checked_on: null
      tolerance: null            # e.g. "within 2% of close", "exact"
      cause: null                # only for contradicted: creator-error | caption-error | outdated | definition
      note: "Third-party data cited by the creator"
calls:
  - id: k03
    ticker: CELH
    action: add
    instrument: stock
    entry: "26"
    target: null
    worst_case: "22"
    horizon: "3y"
    rationale: "Brand volume expected to turn positive within 1-2 quarters"
    t: 1855
    creator_holds: true
numbers:
  - id: n07
    value: 5.307
    unit: "%"
    label: "US 10-year yield"
    as_of: 2026-10-06
    source_type: screen          # spoken | screen | both
    t: 2162
    frame: "c13"
follow_ups:                       # items flagged "worth looking into"
  - id: f01
    about: [c012, k03]            # claim or call ids
    reason: unverified-pillar     # contradicted-material | unverified-pillar | novelty-claim | surprising-figure | cross-creator-disagreement | near-dated-forecast | frame-audio-gap
    detail: "Celsius call rests on a volume turn that no data supports yet"
    next_step: "Check the Nielsen release the post cites; compare the next monthly data"
    priority: M                   # H | M | L
    status: open                  # open | done | dropped
    resolved_note: null
predictions:                      # subset of claims worth tracking in the ledger
  - id: p02
    claim: c030
    statement: "AMD trades above 700 within weeks and he starts trimming"
    ticker: AMD
    type: price-level            # price-level | event | trend | time-bound
    made_on: 2026-10-06
    resolve_by: 2026-11-03       # null if open-ended
    resolution_rule: "AMD closes at or above 700 on any day before resolve_by"
disclosures:
  positions_held: [AMD]
  promo:
    - {kind: private-group, t: 3, note: "pinned-comment pitch"}
```

`_meta/vocab.yaml` holds the allowed values so lint can reject unknown actions, kinds or statuses.

## Verification process
This section defines how a claim moves from "said in the video" to "Verified" or "Not verified", and how items
get flagged as worth a closer look. Claude runs it inside the extraction session; you review the outcome.

### Step 1: Triage every extracted claim
Each claim gets two yes/no tags, which give a priority.
- **Checkable:** is it a statement that a source could confirm or refute (a figure, a dated event, a quote, a
  company fact, a market level)? Opinions, valuations, plans and "I think" statements are not checkable.
- **Material:** does it feed a call, a row in the key numbers table, a stated risk, or a thesis pillar? Or is
  it surprising, framed as news, or big enough to change the picture?

| Checkable | Material | Priority | Action |
|---|---|---|---|
| yes | yes | **P1** | Verify now. Always. |
| yes | no | **P2** | Verify if cheap (one search or one frame). Cap about 10 per video. |
| no | any | **P3** | Record only, under opinions and forecasts. Forecasts with a resolution rule go to the ledger. |

Budget per video: all P1, up to about 10 P2, and a hard cap of about 25 checks. Whatever is not checked
stays `unchecked` and is counted, so the cost is visible instead of hidden.

### Step 2: Run the check ladder (cheapest and most independent first)
1. **Screen check.** Does a frame show the source the creator is reading (a brokerage page, a FedWatch table,
   a CNBC graphic, a filing)? If the frame matches the claim, the result is `verified-screen`. The creator
   chose the screen, so this alone never counts as independent.
2. **Arithmetic and internal consistency.** Do the numbers add up within the video (9.8% volume plus 6.6% price
   is about 17% revenue; 1.6B cash against 6.6B assets)? Method `arithmetic`. Catches caption errors cheaply.
3. **Primary source (T1).** The company release or filing, an exchange or index page, a central bank, Treasury,
   FRED, EIA, BLS, or the original data owner (for example Nielsen or the report a post cites).
4. **Reputable data or news (T2).** An established wire or data provider page, with the date on it.
5. **Second independent outlet.** Two T2 sources that do not cite each other.

Rule for `verified`: one T1 source, or two independent T2 sources. A T3 source (a blog, a social post, a forum, a
video, an AI-generated page) never verifies a claim by itself; it can only suggest where to look. A claim the
creator cites from a tweet or newsletter is traced back to the original; if the original cannot be found it
stays `unchecked` with the note "secondary-cited".

### Step 3: Handle time
- Every check records `as_of`. Price and level claims are checked against the close (or the intraday range for
  an intraday remark) on the video's publish date; "today" claims use that date.
- Live-only data (CME FedWatch odds, an options premium, an intraday quote) is verified only through a dated
  archive or the creator's own screen. Otherwise `unverifiable-now`.
- Tolerance: exact for counts, dates and names; within rounding for percentages the creator rounds; within 2%
  of the day's close for prices he rounds; larger gaps are not "close enough".
- Time-sensitive claims that were only partly checkable are queued for a re-check on their resolution date (the
  predictions ledger does this for forecasts).

### Step 4: Decide the outcome and write it down
Record `status`, `method`, `source_tier`, `source`, `as_of`, `checked_on`, `tolerance` and a one-line note.
- **Confirmed:** `verified` or `verified-screen`.
- **Part right, part not:** `partial`, stating which part.
- **Does not match:** before writing `contradicted`, rule out three explanations in order: (1) a caption or
  transcription error (re-read the surrounding transcript and check a frame), (2) a different definition or
  period (a quarter versus a year, a company versus a brand, "volume" versus "revenue"), (3) an outdated or
  revised source. Only if none applies is it `contradicted`, and it then needs two sources or one T1 source.
  Record `cause`: `creator-error`, `caption-error`, `outdated` or `definition`. Only `creator-error` and
  `outdated` appear under Contradicted or disputed; a caption error is fixed in the note, not blamed on the
  creator.
- **Could not check:** `unchecked` (we did not get to it), or `unverifiable-now` (we cannot).

### Step 5: Flag what is worth looking into
After checks, scan for items that deserve a closer look and write them to the `follow_ups` list with a reason,
a next step and a priority. An item is flagged when any of these is true:

| Reason code | Trigger |
|---|---|
| `contradicted-material` | A material claim came back contradicted or partial |
| `unverified-pillar` | A call's main reason rests on a claim that is unchecked, unverifiable now, or opinion with no data behind it |
| `novelty-claim` | The creator presents it as new, insider, "nobody is talking about this", or a surprise |
| `surprising-figure` | A checkable figure that is large or far from what the other videos in the window say |
| `cross-creator-disagreement` | Another video in the last 14 days takes the opposite stance on the same ticker or claim (automatic in phase 4; flagged by hand before then) |
| `near-dated-forecast` | A forecast or catalyst resolves within 14 days (earnings, data release); also enters the ledger |
| `frame-audio-gap` | The frames show something the speaker did not say that changes the read (a position size, a table, a graphic) |

Priority: **H** when it changes a call's rationale or is material and contradicted, **M** when it is a pillar
we could not verify, **L** otherwise. A follow-up always has a concrete `next_step` (a document to read, a
data release to compare, a date to re-check). "Worth looking into" means worth research, never a
recommendation to trade; the wording stays attributive.

### Step 6: Review and quality
- The note shows the follow-ups near the top (under the TL;DR) and counts them in frontmatter, so they are
  hard to miss. The weekly digest lists open high and medium ones under "Worth a closer look".
- You spot-check: set `human_reviewed: true` after reading, and note any status you disagree with.
  Disagreements are logged in `log.md` and used to tune triage, source tiers and tolerances.
- Lint errors: `verified` with no source, tier or date; `contradicted` with fewer than the required sources or
  with no `cause`; a P1 claim left `unchecked` without a reason; a follow-up without a `next_step`.
- Cost tracking: each note records how many checks were run and how many P2 were skipped, so we can see whether
  the budget is right after the pilot.

### Automation path
Phases 1 to 2: Claude runs steps 1 to 5 by hand in a session (screen reading, web search, fetching filings).
Phase 3: add a price-history source for price claims and a small script that pre-fills tolerance checks. Later:
cached source snapshots (so a check can be re-run), OCR for screen checks, and automatic re-checks on
resolution dates. Each automation replaces a manual step only after it agrees with the manual result on the
pilot videos.

## Other page types

### Creator page
```yaml
---
type: creator
name: Financial Education
slug: financial-education
platform: youtube
handle: null
format_tendency: [talking-head]
typical_posture: "long-term buyer, scales in over 3-6 months"
videos: 1
first_seen: 2026-10-07
last_seen: 2026-10-07
tags: [creator]
---
```
Body: a short profile (auto-written from video notes), a table of videos, recurring promo, stance by ticker,
and a link to the creator's section of the ledger once phase 4 exists.

### Ticker page (phase 4, test)
```yaml
---
type: ticker
ticker: AMD
name: Advanced Micro Devices
aliases: ["Advanced Micro Devices", "A M D"]
sector: semiconductors
mentions: 7
last_mentioned: 2026-10-08
stance_now: {bullish: 2, bearish: 0, mixed: 1}
tags: [ticker]
---
```
Body: a generated mentions table (date, creator, stance, action, link to the claim) between
`<!-- auto:mentions -->` markers, a disagreement note, and open predictions. The auto block is the only part a
script rewrites; text outside it is preserved.

### Predictions ledger entry (phase 4, test)
A single file `ledger/predictions.md` with one table, plus the same rows in `data/ledger.yaml` for scripts:

| id | video | creator | ticker | statement | made | resolve by | rule | status | checked | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| JmPBceO_UH4-p02 | [[videos/...]] | financial-education | AMD | ... | 2026-10-06 | 2026-11-03 | close >= 700 | open | | |

Statuses: `open`, `hit`, `miss`, `partial`, `void` (condition never arose or rule unusable),
`unresolvable` (too vague to ever score). Only predictions with a resolution rule enter the table; vague
forecasts stay as claims. The point is tracking and learning, not ranking creators on a handful of calls,
so the ledger reports counts with sample size and avoids a single score.

### Weekly digest (phase 4, test)
```yaml
---
type: digest
week: 2026-W41
range: [2026-10-05, 2026-10-11]
videos: 10
creators: 4
tags: [digest]
---
```
Sections: `## Themes` (rates, oil, earnings season, each with the supporting videos), `## Most discussed
tickers` (table with count and stance mix), `## Where creators agree and disagree`, `## New calls`,
`## Ledger movement` (predictions resolved or coming due), `## Numbers worth knowing`, `## Gaps` (things claimed
but unchecked). Every line links back to the video note and claim anchor.

### index.md and log.md
`index.md`: one line per page grouped by type, newest first within videos:
`- [[videos/2026-10-07-...]] - Financial Education - bullish on AMD/CELH, scale-in sizing, 6 verified / 9 unchecked`
`log.md`: append-only, prefixed so it can be grepped:
```
## [2026-10-08] ingest | JmPBceO_UH4 | note rendered, 6 verified, 9 unchecked
## [2026-10-08] lint | 0 errors, 2 warnings (missing creator disclosures)
## [2026-10-12] digest | 2026-W41
```

## Pipeline
```
/watch <url> --testing   (existing)         -> watch-output/video-data/<id>/  (frames, transcript, cues)
  1 ingest    snapshot raw/<id>/ (info.json trimmed, transcript, cited frames)
  2 extract   LLM pass over the transcript in timestamped chunks -> claims, calls, numbers, outline, disclosures
              (outputs the YAML sidecar; each item must carry a timestamp)
  3 normalize ticker aliases -> canonical tickers (alias map; unknown names flagged for review)
  4 verify    per claim: screen check from frames, then web/data check where the claim is checkable; write status
  5 render    sidecar + metadata -> videos/<date>-<id>-<slug>.md
  6 link      update creator page, ticker pages (phase 4), index.md, log.md
  7 lint      anchors present, vocab valid, links resolve, counts match, no orphan pages
```
Code lives in `src/agent_skills/wiki.py` with CLI commands `agent-skills wiki ingest|render|lint|index|digest`,
matching the style of `train.py` and `gc.py`. The LLM steps (extract, verify, digest prose) are done by Claude
following `WIKI.md`; the scripts do the deterministic work (snapshot, render, lint, indexes, auto blocks).
The `/watch` SKILL.md gets a short "after the report" section pointing to this flow.

Lint rules (errors): claim, call, number or outline item with no timestamp; unknown vocab value; a link that
does not resolve; a verified claim with no source or date; counts in frontmatter not matching the sidecar;
frontmatter missing a required field. Warnings: promo without a timestamp, creator positions unknown, an
alias with no canonical ticker, a note older than 30 days with unchecked checkable claims.

## Phases and acceptance
| Phase | Work | Done when |
|---|---|---|
| 0 | Resolve the open questions below; freeze `WIKI.md` and `vocab.yaml` v1 | Questions answered (see the decisions log). `WIKI.md` and `vocab.yaml` are frozen in phase 1 together with the template |
| 1 | Template and a pilot: rewrite `aT5AaRmohrs` (Options With Ryan, 19 min, data dense) in the new format, running the verification process end to end (triage, check ladder, follow-ups) | The note renders from the sidecar, every item has a working timestamp link, and you can read the TL;DR and calls table in under two minutes |
| 2 | Migrate the other nine summaries; create creator pages; hand-built `index.md` and `log.md` | All ten videos have notes and sidecars; `index.md` lists them |
| 3 | `wiki` CLI (ingest, render, lint, index); ticker alias map seeded from the garbled names seen so far (AAT to AMAT, COR to COHR, Amcor to AMKR, Wind to WYNN, Flicks to NFLX); alias map grown whenever extraction finds an unknown name | Lint passes on all notes; a new video goes from `/watch` to a rendered note with one command plus the LLM steps |
| 4 | Test runs: ticker pages (11), predictions ledger (12), weekly digest (13) for week 2026-W41 | Digest built from sidecars only (no rereading transcripts); at least a handful of ledger entries resolved; you judge whether each of the three is worth keeping |

| 5 | Deferred: import the wiki into your brain. Not scheduled; the format stays portable so this is a copy, not a rewrite | Decided when the brain is ready |

Phase 4 criteria are deliberately soft because these three are tests. Keep a view if you actually open it;
drop or merge it if not.

## Pilot choice and what it will teach us
The pilot is `aT5AaRmohrs` because it is dense in checkable figures (oil, FedWatch odds, expected moves, prices)
and has screen-verifiable pages. Expected hard parts to watch: how many claims are checkable at all, how much
effort verification costs per video, whether extraction yields too many trivial claims, and whether
"verified-screen" feels honest. Those answers decide how much verification to automate.

## Risks
- **Verification cost and drift.** Web checks per claim are slow and prices move. Mitigation: check only
  claims flagged as checkable and material (they feed a call or a number table), pin checks to an as-of date,
  cap checks per video, and record "unchecked" without apology.
- **Over-extraction.** Hundreds of trivial claims bury the note. Mitigation: extraction is limited to
  thesis, call, number, risk and topic-change items; target 15 to 40 claims per 20-30 minutes.
- **Caption errors on names and numbers.** Mitigation: ticker alias map, frame cross-check, and a
  `transcript_source` field so low-trust sources are visible.
- **Looks like advice.** Mitigation: attributive wording enforced in `WIKI.md`, no recommendations in notes or
  digests.
- **Creator attribution.** `PLAN.md` for testing mode says creator names are stored for training only. The wiki
  surfaces them. This needs an explicit decision (question 3).
- **Schema churn.** A format change forces a migration. Mitigation: `schema_version` in frontmatter and in the
  sidecar, and a render step that can rebuild any note from its sidecar.

## Open questions (defaults in brackets)
1. **Where does the wiki live?** [A `wiki/` folder in this repo; it can be moved or opened as an Obsidian
   vault later.] Or a separate vault repo that this project writes into?
2. **Link style?** [Obsidian `[[wikilinks]]` for wiki pages, normal markdown links for timestamps and URLs.]
3. **Creator names:** testing mode keeps creators out of normal output. Is it fine for the wiki to name creators
   and keep creator pages and per-creator ledger stats? [Yes.]
4. **What counts as "verified"?** [Primary document or reputable data source, or a second reputable outlet; the
   creator's own screen share is labelled `verified-screen`.] Is a web search per claim acceptable, and is a
   price-data library (for example yfinance) allowed for price claims? [Web search yes; add a price source in
   phase 3 if you want.]
5. **Frames in the wiki:** keep only the cited frames in `raw/` (small), or the full contact sheets? [Only
   cited frames.]
6. **Migrate old summaries** into the new format, or leave them and apply the format going forward only?
   [Migrate all ten.]
7. **Digest cadence:** weekly, Monday to Sunday, covering whatever was ingested that week? [Yes, ISO weeks.]
8. **Scope beyond finance?** The vocab is finance-shaped (calls, tickers). Should the wiki also hold other kinds
   of video later, using a different note type? [Keep finance only; add a `type: video` variant later if needed.]
9. **How strict on timestamps** when captions are rolling duplicates (the same line repeated at slightly
   different times)? [Use the first appearance of the line.]
10. **Which transcript wins** when captions and Whisper both exist? [Captions unless missing; record
    `transcript_source`.]

## Decisions log
- 2026-10-20: Defaults accepted for all ten open questions (wiki folder in this repo, wikilinks for pages and
  normal links for timestamps, creators named with creator pages, web search allowed for verification and a
  price source can be added in phase 3, cited frames only, migrate all ten summaries, ISO-week digests,
  finance only, first appearance of a caption line for timestamps, captions win over Whisper).
- 2026-10-20: The wiki itself (the brain) is introduced later. The `wiki/` folder here is staging in a format
  that follows the brain's conventions (something similar to the Karpathy pattern), so moving it later is a
  copy. Phase 5 records this.
- 2026-10-20: Verification must be a defined process, with a way to flag what is worth looking into. Added the
  Verification process section (triage, check ladder, time handling, outcomes, follow-ups, review) and the
  `follow_ups` field. Standard for verified: one primary source, or two independent reputable sources.
