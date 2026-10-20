# Stock-Analysis Methodology Extraction

**Source video:** [Top 4 AI Stocks I'm Buying In August + PLTR, HOOD & SOFI Update](https://www.youtube.com/watch?v=nnD3vSOQAZw)
**Uploader:** Options With Ryan · **Duration:** 25:42
**Evidence base:** full timestamped transcript (678 caption segments) + 46 scene-detected frames + 23 targeted frames pulled at transcript-flagged "look here" moments (69 frames total)

> **Scope note (not a generic summary):** this document extracts *process*, not video content. Each step is tagged **[explicit]** (presenter said it directly), **[visual]** (shown on screen, not narrated), or **[inference]** (reasonable read of the workflow, not directly stated). Nothing below is added that isn't traceable to the transcript or a frame.

## Who this is

Screen captures at 11:02–12:16 show an Instagram profile (`itsryanhildreth`) and an X/Twitter profile ("Options With Ryan" / "Options Trading University"). The presenter is **Ryan Hildreth**, a retail **options-income / "wheel strategy"** trader-educator — not an institutional fundamental analyst. His process blends macro reads, technical analysis, valuation multiples, and options-flow data, but the end goal in every case is an **options trade** (covered call / cash-secured put) around a stock he already holds, not a standalone buy/sell fundamental thesis. **[inference]**

---

## The methodology, in the order it's performed

### Step 0 — Portfolio check-in (0:00–0:52)
- **Does:** Opens his brokerage account summary (total value, day/month % change) and a realized gain/loss report. **[visual]**
- **Why:** Establishes where the account stands before discussing new ideas; explicitly ties it to freeing up cash. **[explicit]** — *"we took some profits on some Apple cash-secured puts to free up some cash."*
- **Data examined:** Account total value, % change, realized short-term gains, total gains/losses, a "gain/loss ratio" (95.94%). **[visual]**
- **Tools:** Brokerage dashboard (unbranded) + a "Wheel Trader P&L Tracker" web app (0:31, 0:47) showing monthly P&L, win rate, days-in-trade. **[visual]** / **[inference]** that this is a purpose-built tool for wheel-strategy traders, separate from the brokerage.

### Step 1 — Macro/inflation scan (0:52–4:19)
- **Does:** Reviews the just-released US jobs report, then checks two inflation trackers. **[explicit]**
- **Why:** Determines pressure on the Fed to hike/cut rates — the top-down driver he applies to the whole portfolio. **[explicit]**
- **Data:** Jobs added/lost vs. consensus (loss of 23K vs. +83K expected), unemployment rate, hourly wages (spoken only, no chart shown); nowflation.com's real-time inflation gauge (1.84%) vs. official core CPI (~3.8%) (frame at **2:52**); CME FedWatch Tool's rate-hike probability table (frame at **4:19**). **[explicit] + [visual]**
- **Tools:** nowflation.com ("free alternative to Trueflation," pulls Zillow/AAA gas-price data etc. for a daily, non-lagging inflation estimate — **[explicit]**); CME FedWatch Tool, checked "on a weekly basis" **[explicit]**.
- **Metrics calculated:** Delta between nowflation gauge and official CPI; probability % of a 2nd/3rd rate hike at each future FOMC meeting (odds of a second hike fell 90%→71%). **[visual]**
- **Conclusion:** Softening jobs + falling rate-hike odds + nowflation trending below official CPI = bullish backdrop. **[explicit]**
- **Rule of thumb [explicit]:** *"What would concern me is if I saw this [nowflation] reading going above what the BLS is releasing on core CPI."* — alternative data outrunning official data to the upside is his macro red flag.

### Step 2 — Index & volatility check (5:23–9:00)
- **Does:** Checks QQQ/SPY daily performance and RSI, then VIX level, then a personal "VIX cash allocation" model. **[explicit] + [visual]**
- **Why:** Volatility level directly sets how much of the portfolio he keeps in cash vs. deployed. **[explicit]**
- **Data/metrics:** QQQ/SPY daily % change; RSI (not yet overbought); market-maker-implied expected range (700–748 on QQQ); VIX level (~14, "greed zone" = 12–15); his current cash % (22.5%) vs. model target (30–40% at this VIX band). **[explicit] + [visual]**
- **Tools:** A TradingView-style charting terminal (Bollinger Bands, moving averages, RSI/MACD panes, visible throughout the video) and a proprietary VIX-to-cash-allocation chart (frame at **8:05**). **[visual]**
- **Conclusion:** Sub-15 VIX historically precedes pullbacks, so he stays slightly underweight his own cash target rather than fully invested, keeping "dry powder" for a black-swan dip. **[explicit]**
- **Rule of thumb [explicit]:** *"I don't want to be fully invested when the VIX is trading below 15."* VIX 12–15 → hold 30–40% cash (he's at 22.5%, i.e. more aggressive than his own rule).

### Step 3 — Per-stock analysis (repeated pattern, 9:00 → end)
Same sub-routine run on each name: CLS (9:00), IREN (12:16), DRAM/WDC (14:33–19:00), PLTR (19:23), HOOD/SOFI (21:54–end).

**(a) Catalyst/news check [explicit]** — e.g. CLS's $3B share offering ("dilution, but bullish — they're raising capital because demand for data-center switches is so high"); IREN short-interest buildup ("Michael Burry recently start shorting NBIS… same thing happens with IREN"); WDC/DRAM sector read-through from SK Hynix and WDC's own "earnings were stellar but expectations were too high"; PLTR's post-earnings rally.

**(b) Chart/technical read [visual]** (e.g. 9:50, 12:43, 16:22, 18:45, 22:50) — candlestick chart with Bollinger Bands, a rising trendline, and RSI/MACD sub-panes. Checks: price vs. lower Bollinger Band (buy-zone signal), a highlighted "volume weighted average price line" as a proxy for institutional cost basis (WDC, 16:52–17:01 **[explicit]**), circled prior short-interest clusters as squeeze setups (IREN, 12:43), RSI/MACD bullish crossovers (HOOD, 22:50).

**(c) Valuation check [explicit]** — current P/E stated and compared to the stock's own historical P/E range: CLS "33 PE… trading at a discount"; PLTR "trading at a 700 PE [before]… 140 PE right now" despite the company "outpacing at historic levels"; WDC "25 PE… hasn't seen a 25 PE since April"; HOOD "41 PE, I think this thing's headed higher."

**(d) Options-flow / dealer-positioning check [visual]** (22:59–23:23) — Unusual Whales' gamma-exposure / "Gamma Heat Zones" tool for HOOD, identifying institutional support ("put wall" at 93) and resistance ("call wall"/rejection at 120).

**(e) Own-position review [visual]** (e.g. 11:02, 13:36, 15:49, 17:42, 20:51) — a positions blotter showing existing share count, cost/assignment basis, and open covered calls / cash-secured puts, e.g. "200 shares at 390… selling covered calls at my cost," IREN "2,600 shares… selling 49 covered calls," WDC "bought 100 shares to lower cost basis from 600 to 537... sold the 545 covered call."

**(f) Price target + trade plan [explicit]** — a specific target range/% upside and the next options move: CLS "$400–460 range… 25–44% upside"; IREN "definitely a $60 stock"; DRAM "70s and 80s"; SOFI "back above $20… maybe 24–25." Recurring plan: the **wheel strategy** — sell covered calls near cost basis → shares get called away → sell cash-secured puts to re-enter → repeat.

**(g) Position-sizing rule [explicit]** (stated re: PLTR) — *"keeping no more than 10% of your portfolio in any one individual stock."* He flags himself as a self-aware exception on CLS ("I'm a little bit over-allocated, but that's fine").

---

## What would cause him to reject an investment (#7)

He doesn't reject any of the four featured names in this video — all are framed as "still at a discount." The rejection/caution triggers below are the **inverse conditions** of his bull cases:

- Macro: nowflation gauge rising *above* official core CPI (inflation reaccelerating) — **[explicit]**, stated directly as a concern trigger.
- Macro: rate-hike odds on the FedWatch Tool rising instead of falling — undercuts the bull case for rate-sensitive names (HOOD, SOFI). **[inference]**
- Portfolio-level: VIX pushing back above 15 → he'd raise cash toward the 30–40% target rather than stay near 22.5% (a de-risking trigger, not a single-stock sell signal). **[explicit]**
- SoFi-specific: his discount thesis is explicitly conditioned on the priced-in 2nd rate hike *not* happening — if it does, "trading at a much deeper discount than forward guidance states" no longer holds. **[inference]** from his stated conditional.
- Valuation logic: a high P/E is acceptable only if earnings growth is "outpacing at historic levels" (his PLTR framing) — the implied red flag is a rich multiple *without* matching earnings growth, though he never applies this negatively on-screen. **[inference]**

## Consolidated rules of thumb (#8)

1. nowflation gauge above official BLS core CPI → inflation concern. **[explicit]**
2. Never fully invested when VIX < 15; hold 30–40% cash at VIX 12–15 ("greed zone"). **[explicit]**
3. Oversold RSI + high VXN historically mean-reverts to overbought before any real pullback. **[explicit]**
4. Never allocate more than 10% of the portfolio to one stock. **[explicit]**
5. A widening gap between share price and its own historical P/E range (with intact/improving fundamentals) = "trading at a discount." **[inference]** from repeated pattern across CLS/PLTR/WDC/HOOD.
6. Rising short interest into a low + prior squeeze pattern = bullish setup, not a bearish signal. **[explicit]**, re: IREN.
7. Circled institutional cost-basis / VWAP levels and "put wall" gamma levels = expected support. **[visual] + [explicit]**

---

## Evidence index

| Timestamp | Evidence | Frame |
|---|---|---|
| 0:31 | Wheel Trader P&L Tracker | `frames/frame_0003.jpg` |
| 2:52 | nowflation.com inflation gauge | `frames/frame_0016.jpg` |
| 4:19 | CME FedWatch Tool probability table | `cues/frames/cue_0002.jpg` |
| 5:23 | QQQ chart, RSI | `cues/frames/cue_0003.jpg` |
| 8:05 | VIX cash-allocation model | `cues/frames/cue_0005.jpg` |
| 9:50 | CLS chart (Bollinger, trendline) | `cues/frames/cue_0006.jpg` |
| 11:02 | CLS position blotter | `frames/frame_0018.jpg` |
| 12:43 | IREN short-interest squeeze setup | `cues/frames/cue_0010.jpg` |
| 13:36 | IREN position blotter | `frames/frame_0020.jpg` |
| 16:52–17:01 | WDC chart, VWAP institutional cost-basis line | `cues/frames/cue_0015.jpg` |
| 17:42 | WDC position blotter | `frames/frame_0029.jpg` |
| 19:23 | PLTR chart | `frames/frame_0032.jpg` |
| 22:50 | HOOD chart, RSI/MACD crossover | `frames/frame_0040.jpg` |
| 22:59–23:23 | Unusual Whales GEX / Gamma Heat Zones (HOOD) | `frames/frame_0041.jpg`, `frame_0042.jpg`, `frame_0043.jpg` |

Full transcript: `download/video.en.vtt` (or run `transcribe.py` on it for the cleaned, timestamped text).
