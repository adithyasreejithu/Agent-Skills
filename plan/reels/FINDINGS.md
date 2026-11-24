# Reels trial: findings, creator value and pre-model filtering

Trial window: 30 days to 2026-10-22 (stockswithjonah reaches only 2026-10-02, see "Data notes").
151 reels from 5 creators, summarized in open-type mode. Raw tables: `plan/reels/TRIAL.md`.

## 1. Summary

- **Cost is low:** $2.16 of Claude for 151 reels ($0.0148 a reel), plus about 1,200 Gemini tokens a reel for
  transcripts.
- **About a quarter is filler.** Using the final type list below, 47 of 151 reels (31%) are filler or promo, and 40
  of those 47 come from stockswithjonah.
- **The creators differ a lot.** Join the 535 and Mo Invests give the most usable information per reel.
  stockswithjonah gives the most reels, but under half of them say anything usable.
- **About half the reels (48%) point at something on screen** (a chart, a ticker list, a trade table). Transcripts
  miss that part.
- **Every number in every summary appeared in the transcript or caption** (0 kept with unverified numbers).
- **Most filler can be spotted without Claude**, using duration, transcript length and the caption (section 4).

## 2. Agreed type list

The open run produced 32 type names. They are merged into 9 types:

| Type | Merges | Brief | Reels |
|---|---|---|---|
| stock-pick | stock-pick, stock-comparison, valuation-check, stocks-to-avoid | include | 36 |
| watchlist | watchlist, stock-rundown, stock-list | include | 14 |
| trade | trade-alert, trade-flex, trade-recap, strategy-showcase | include | 10 |
| portfolio-update | portfolio-update, portfolio-review | include | 8 |
| market-news | news-reaction, market-update, earnings-recap, earnings-preview, earnings-reaction | include | 23 |
| insider-trade | politician-trade, insider-trade | include | 7 |
| education | education, mindset, milestone | count only | 6 |
| promo | promo | skip | 7 |
| filler | no-speech, meme, lifestyle, hype-clip, stock-hype, brag, trade-roast, comparison | skip | 40 |

"Useful" below means one of the six `include` types. "Actionable" means useful and naming at least one ticker and
one level (a price, target or percentage).

## 3. Creator analysis

### 3.1 Numbers

| | Join the 535 | Mo Invests | Andre Invests | Wealth by Christy | Stocks with Jonah |
|---|---|---|---|---|---|
| Reels (30 days) | 7 | 21 | 20 | 17 | 86 (20 days) |
| Reels per week | 1.8 | 5.2 | 4.8 | 4.4 | 30.1 |
| Useful | 7 (100%) | 17 (81%) | 12 (60%) | 14 (82%) | 48 (56%) |
| Actionable | 100% | 76% | 60% | 76% | 42% |
| Filler or promo | 0% | 14% | 15% | 18% | 44% |
| Levels per useful reel | 5.4 | 7.8 | 7.2 | 3.2 | 5.0 |
| Distinct tickers | 7 | 56 | 18 | 20 | 31 |
| Median length | 1:20 | 0:43 | 0:48 | 0:50 | 0:18 |
| Median words spoken | 277 | 160 | 163 | 194 | 62 |
| Refers to the screen | 100% | 43% | 50% | 24% | 50% |
| Median views | 3.6k | 44k | 27k | 12k | 6.6k |
| Claude cost per useful reel | $0.015 | $0.018 | $0.025 | $0.018 | $0.027 |
| Bullish share of useful reels | 86% | 76% | 67% | 86% | 71% |

### 3.2 Value weight

The weight measures **information value per reel**: how often a reel is usable, and how much it says when it is.

```
weight = 0.5 × actionable share  +  0.3 × depth  +  0.2 × (1 − filler share)
depth  = min(levels per useful reel, 8) / 8
```

| Creator | Actionable | Depth | Not filler | **Weight** | Suggested priority |
|---|---|---|---|---|---|
| Join the 535 | 1.00 | 0.68 | 1.00 | **0.90** | 90 |
| Mo Invests | 0.76 | 0.98 | 0.86 | **0.85** | 85 |
| Andre Invests | 0.60 | 0.90 | 0.85 | **0.74** | 75 |
| Wealth by Christy | 0.76 | 0.40 | 0.82 | **0.67** | 65 |
| Stocks with Jonah | 0.42 | 0.63 | 0.56 | **0.51** | 50 |

The priority would go in `reel-sources.toml`. It decides queue order and could order creators in the brief.

What the weight does not measure:
- **Whether the calls were right.** No creator's picks have been checked against later prices yet; see 5.3.
- **Volume.** stockswithjonah has the lowest weight but still produced the most useful reels (48).

### 3.3 Per creator

**Join the 535 (weight 0.90).**
- Every reel is a disclosed politician trade with the entry price and whether the stock now trades above or below
  it.
- Nobody else in the list covers this.
- It posts slowly (under 2 a week) and its reels are the longest.
- Every reel shows a trade table on screen, so this creator gains most from looking at frames.

**Mo Invests (weight 0.85).**
- Mostly watchlists and buy lists with buy levels.
- It has the most distinct tickers (56), the most levels per reel (7.8) and the largest audience (44k median views).
- Its 3 non-useful reels are 2 lifestyle clips and 1 education reel.

**Andre Invests (weight 0.74).**
- The best source for why the market moved: 7 market or earnings explainers, such as Micron's Q4, the weekly
  pullback, and the earnings recap.
- 5 of its 20 reels are education or mindset. Those aren't filler, but they aren't actionable either, which pulls
  its weight down.

**Wealth by Christy (weight 0.67).**
- Mostly stock picks and dip buys (9 of 17).
- The picks are shallow: 3.2 levels a reel, and often no buy price.
- 3 reels are sponsored. The sponsor pitch is long speech, so the cheap filter in section 4 does not catch them.
- Least on-screen dependence (24%), so its transcripts carry the content well.

**Stocks with Jonah (weight 0.51).**
- 30 reels a week, short (18 s median).
- 44% are filler: memes, music clips, "follow for real setups" and brag clips.
- The useful half is real trades and alerts, with VST, ORCL and CRWV most often, but the tone is hype-heavy.
- It is worth keeping only if the filter in section 4 runs first. It also needs a higher scroll limit to reach 30
  days back.

### 3.4 Where creators agree

Six tickers came up from 4 of the 5 creators in the month: **AMD, META, CRWV (CoreWeave), AVGO (Broadcom), VST
(Vistra) and NBIS (Nebius)**. Next most shared: SOFI, RKLB, ORCL, MU and BE, from 3 creators each.

Agreement across creators is a natural headline for the brief's "Tickers mentioned" table, and it is free to compute.

## 4. Spotting filler before Claude

Every rule below was tested against the trial's own labels. "Filler" here means `filler` or `promo` (47 reels).

| Rule | Known when | Flagged | Filler caught | Wrongly flagged | Filler share of flagged |
|---|---|---|---|---|---|
| Length under 12 s | before download (page) | 39 | 34 of 47 | 5 | 87% |
| Length under 12 s **and** a caption with no info | before download | 22 | 20 | 2 | 91% |
| Fewer than 20 words spoken | after Gemini | 47 | 41 | 6 | 87% |
| Fewer than 20 words **and** a caption with no info | after Gemini | 26 | 23 | 3 | 88% |
| Caption asks to follow, repost, share or comment | before download | 48 | 12 | 36 | 25% |
| Views | before download | not useful: Mo's filler had *more* views than its useful reels | | | |

"A caption with no info" means the caption, with hashtags removed, contains no digit, no `$TICKER`, fewer than two
capitalized ticker-like words, and is under 150 characters.

**Findings:**
- **Length and word count work; engagement-bait captions alone do not.** Almost every creator asks for follows,
  including on useful reels.
- **Adding the caption check removes most mistakes.** Of the 3 "useful" reels the best rule flags, all are
  borderline: music-only clips where the caption alone hints at a trade ("averaging into energy", "shorted most of
  these at the highs", a ticker list shown only on screen). None names a level, so little is lost.
- **Sponsor reels need a keyword rule, not a length rule.** Christy's 3 promos are 31–53 s of speech. A caption or
  transcript check for "sponsored", "partner", "#ad", or the sponsor's name would catch them.

**Proposed two-stage filter:**
1. **Before download (free):** a reel under 12 s with a caption that has no info is recorded as `filler` from the
   caption alone. No download, no Gemini, no Claude.
2. **After transcription, before Claude:** a reel with fewer than 20 words spoken and a caption with no info gets
   a one-line `filler` entry written by Python ("No speech; caption: ...").

On this trial, the second stage alone would have taken 26 reels (17%) out of the Claude batches. 25 of them were
from stockswithjonah, which would drop from 86 to 61 reels and keep 45 of its 48 useful ones. The other creators
lose nothing useful.

**Creator-level warning signs, from poll data only:** posting more than 15 reels a week, a median length under 20 s,
and more than a third of reels under 12 s. stockswithjonah trips all three; no other creator trips any. A new
creator could be checked this way with a dry-run poll before adding them.

## 5. Recommendations

### 5.1 Now (done 2026-10-25, see section 7)
1. Write `reel-types.toml` with the 9 types above, and re-summarize the reels from cached transcripts.
2. Add the two-stage filler filter and a sponsor keyword check to `reels fetch` and `reels summarize`.
3. Set creator priorities from section 3.2 in `reel-sources.toml`.

### 5.2 Decide
- **Frames for on-screen reels.** About half the reels point at the screen, and Join the 535 always does. A good
  first test is 3 frames a reel for Join the 535 only.
- **stockswithjonah.** Keep it with the filter at priority 50, or cap it at a set number of reels a day.

### 5.3 Later: score the calls, not just the content
The weight measures how much a creator says, not whether they are right. Each actionable reel already stores
ticker, stance and stated levels with a date. A later step can price each call at its post date and again 30 and
90 days later. Hit rate and average return per creator would then become a fourth part of the weight. It needs a
price source and at least 2–3 months of reels before the numbers mean anything.

## 6. Data notes

- **stockswithjonah covers only 2026-10-02 to 2026-10-22.** It hit the 25-scroll trial limit. Its per-week
  figures use those 20 days.
- **One reel is still untranscribed** after a network timeout (`DeumBe9InWb`, stockswithjonah). It is not in the
  numbers.
- **The `speech` flag in `TRIAL.md` (99% with speech) is too loose.** It counts any non-empty transcript, and
  music lyrics or a single word count. Words spoken (section 4) is the better measure.
- Creator figures come from one month. Treat the weights as a starting point and recompute them after another
  month.

## 7. Applied (2026-10-25)

- **Types:** `.agents/skills/ingest/reel-types.toml` holds the 9 types with their fields.
- **Filter:** `scripts/reel_filter.py` runs in `reels fetch` (stage 1) and `reels summarize` (stage 2). `--no-rules`
  turns it off.
- **Sponsors are a hint, not a filter.** A keyword rule caught only 2 of Christy's 3 sponsored reels and also
  matched a real stock-pick ("partnered with"). Sponsor markers are therefore passed to the model as
  `sponsor_hint`.
- **Priorities:** set in `queue/reel-sources.toml`: 90 / 85 / 75 / 65 / 50.
- **Re-summarize:** all 152 reels from cached transcripts. 37 were written as filler by rule (no Claude call) and
  115 went to Claude, for $2.10 ($0.018 a Claude reel, or $0.014 averaged over all 152).
  - **Why 37 instead of the 26 predicted in section 4:** the shipped caption check ignores hashtags completely,
    while the analysis counted ticker hashtags such as `#vistra` as information.
  - The 11 extra reels are all 6–17 s caption-and-music clips ("It's pumping!!!", "JPMorgan's prediction was
    right!!!"), so nothing of substance was lost. They do lose the ticker that only appeared as a hashtag.
  - 36 of the 37 are from stockswithjonah.
- **Final mix:**
  - filler 48 (37 by rule, 11 by Claude)
  - stock-pick 38
  - watchlist 19
  - market-news 14
  - insider-trade 8
  - trade 8
  - portfolio-update 8
  - education 6
  - promo 3 (all 3 of Christy's sponsored reels)
- 0 reels kept with unverified numbers.
- **Downloads:** reel audio is deleted after each transcript, so the trial left none. The Instagram videos from
  earlier `watch.py` tests (about 81 MB in `watch-output/`) were deleted. Only the transcripts
  (`watch-output/video-data/reels/`) are kept, so future re-summaries need no download.
