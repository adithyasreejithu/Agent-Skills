# Technical read on a stock chart: guide

_Written 2026-11-20 by hand from the video evidence on disk. Not auto-regenerated: `analyze --render-only` does not touch this folder. The shorter generated page is [../methods/technical-read-on-a-stock-chart.md](../methods/technical-read-on-a-stock-chart.md)._

Reading a candlestick chart with Bollinger Bands, moving averages, VWAP, RSI and MACD to judge trend, pullback depth and likely support. Used to decide where a stock may pull back to and whether it is a candidate.

- **Type:** stocks analysis
- **Seen in:** 1 video, 2026-10-10: [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md))
- **Sites/software:** TradingView
- **Indicators:** [Bollinger Bands](indicators.md#bollinger-bands), [50-day](indicators.md#moving-averages) and [200-day](indicators.md#moving-averages) moving averages, [VWAP](indicators.md#vwap), [RSI](indicators.md#rsi), [MACD](indicators.md#macd), [P/E ratio](indicators.md#pe-ratio)

## How to read this page

Each step has the same parts, so you can scan for the one you need:

| Part | What it contains | Where it comes from |
|---|---|---|
| **Do** | The action, written so it can be repeated on any ticker | Method (generalised from the video) |
| **Look at** | What to look at, linked to the [indicator fact sheet](indicators.md) | Method |
| **How to read it** | What the reading means in general | *Reference*: general market knowledge, **not from the video** |
| **The creator's reading** | What he concluded from it, with a footnote number | Video evidence, tagged `explicit`, `visual` or `inference` |
| **Why this step is here** | The reason for the step | Stated by him, or marked as inference |
| **Check before moving on** | A concrete test that the step is done | Method |

This page is reconstructed from one walkthrough, and the thresholds an agent would need are not in the video: see [open decisions](#open-decisions-before-an-agent-could-run-this).

Footnote numbers like <sup>[3](#fn3)</sup> jump to the evidence at the bottom: the video timestamp, what was on screen, and the numbers he read. Tags: **explicit** = he said it; **visual** = shown on screen, not said; **inference** = my reading, not stated.

## What goes in and what comes out

- **In:** a ticker, and a TradingView chart set to the **daily** timeframe with a saved layout that already draws the indicators below<sup>[1](#fn1)</sup><sup>[2](#fn2)</sup>.
- **Out, per ticker:** (a) a verdict, in this page's own shorthand: *stretched*, *at support* or *coiling* ("coiling" is his word, the other two labels are mine); (b) the price levels where a pullback would likely stop (mid band, 50-day, 200-day, yearly VWAP, lower band). Those levels feed the options methods listed under [what comes next](#what-comes-next).

## Terms used on this page

All definitions here are `reference` (general knowledge), except where marked.

- **Support / resistance:** a price level where falling price has tended to stop (support) or rising price has tended to stall (resistance).
- **Run:** a sustained rise over a few days or weeks. Example in the video: 18% in about three weeks.
- **Stretched:** price far from its average, so a return toward the average is more likely than a continuation at the same speed. No fixed cut-off exists; see the [open decisions](#open-decisions-before-an-agent-could-run-this).
- **Overshoot:** a pullback that goes past the level it was expected to stop at.
- **Base:** a period where a stock stops falling and trades in a range before the next move.
- **Rinsed out weak hands (his phrase):** holders who would panic-sell in a big decline have already sold, so less selling pressure is left.
- **Coiling (his word):** price tightening into a narrow range, often before a bigger move.
- **`close` in a legend such as `SMA 200 close`:** the average is calculated from each day's closing price.
- **`CC` in `CC SMA 50 close`:** not explained in the video, and I could not verify what it stands for `inference`.
- **Tickers:** SPY = S&P 500 ETF, QQQ = Nasdaq-100 ETF, SMH = semiconductor ETF, AMAT = Applied Materials, GLW = Corning, HOOD = Robinhood, BE = Bloom Energy. The photonics ETF's ticker is not verified.
- **Market-maker expected range, call wall, put wall (GEX):** levels derived from options data. The expected range is the span options pricing implies; a call wall is commonly described as a resistance level and a put wall as a support level. They belong to the options methods linked under [what comes next](#what-comes-next). The video does not show where his expected range comes from.
- **Cash-secured put:** selling a put option while holding enough cash to buy the shares. You are paid a premium and agree to buy at the strike price if assigned.

## The steps

**Order.** The order below is the clearest one for learning. He does **not** follow one fixed order: indices come first, then single stocks, and the order inside a stock varies<sup>[12](#fn12)</sup> `inference`.

### Step 1. Open the ticker on the standard chart layout

- **Do:** click the ticker in the watchlist so the same saved layout loads: daily candles, same overlays, same lower panels.
- **Look at:** the [timeframe](indicators.md#timeframe) (1D), the [candlestick chart](indicators.md#candlestick-chart), and the legend text that names each indicator and its settings.
- **How to read it** *(reference)*: every indicator is calculated in candles, so "50-day" only means 50 days on a daily chart. Using one layout for every ticker makes readings comparable.
- **The creator's reading:** he switches between SPY, SMH, AMAT, HOOD and BE by clicking the watchlist, and the same layout loads each time<sup>[1](#fn1)</sup> `visual`. He does not say why; a fixed layout lets him read every stock the same way `inference`.
- **Why this step is here:** consistency. If the layout changes between tickers, the numbers cannot be compared.
- **Check before moving on:** the legend shows the Bollinger Bands, the 50-day and 200-day averages, a yearly VWAP, and RSI and MACD panels<sup>[2](#fn2)</sup>.

### Step 2. Set the index range and near-term support (QQQ, S&P 500)

- **Do:** before single stocks, look at the broad market: where the index sits inside its expected two-week range and which level could hold it on a dip.
- **Look at:** the index chart's [mid Bollinger Band](indicators.md#bollinger-bands) and the range given by a separate market-maker source.
- **How to read it** *(reference)*: the middle band is the 20-day average. After a stretched move, traders often watch it as the first place a dip might stall, though price can pass straight through it.
- **The creator's reading:** QQQ is inside the market-maker expected range for the next two weeks, about 727 to 771. He thinks it can pull back a little, and names the mid band, about 737, as a place for short-term support. He says the S&P 500 has room to break out<sup>[3](#fn3)</sup><sup>[4](#fn4)</sup> `explicit`.
- **Why this step is here:** to decide whether the broad market and big tech are likely to cool off before picking single stocks `inference`.
- **Check before moving on:** you have a "pullback to X or range low Y" level for the index.

### Step 3. Check how stretched price is against the Bollinger Bands

- **Do:** on each chart, note whether price is near the upper band, the middle band or the lower band.
- **Look at:** [Bollinger Bands](indicators.md#bollinger-bands) (legend on screen: 20-period simple moving average, 2 standard deviations<sup>[2](#fn2)</sup>). The legend shows three price labels; from the SPY and AMAT charts they read as middle, upper, lower<sup>[4](#fn4)</sup> `inference`.
- **How to read it** *(reference)*: the upper band means "stretched up relative to the recent average", the lower band means "stretched down", the middle band is the average price drifts back to. A touch is not an automatic reversal, because strong trends can ride a band for weeks.
- **The creator's reading:**
  - A stock hugging the upper band after a big run normally pulls back to the mid band, maybe overshooting lower. His example is the semiconductor ETF SMH after an 18% run from September 16 to October 6<sup>[5](#fn5)</sup> `explicit`. (The legend numbers on that chart do not match his description; see [what the video does not show](#what-the-video-does-not-show).)
  - A stock sitting at the lower band, especially after a bounce, is a setup he likes (HOOD)<sup>[6](#fn6)</sup> `explicit`.
- **Why this step is here:** a big run pressed against the upper band is treated as normal to cool off, and the lower band is where he wants to be paid to buy<sup>[5](#fn5)</sup><sup>[6](#fn6)</sup> `explicit`.
- **Check before moving on:** each stock is labelled upper / middle / lower region, and has a mid-band price and a lower-band price written down. The video gives no cut-off for the regions (see [open decisions](#open-decisions-before-an-agent-could-run-this)).

### Step 4. Locate price against the 200-day, 50-day and yearly VWAP

- **Do:** see which of these lines price just bounced from, sits near, or could fall to.
- **Look at:** the [200-day and 50-day moving averages](indicators.md#moving-averages) and the [yearly VWAP](indicators.md#vwap) (legend: `SMA 200 close`, `CC SMA 50 close`, `VWAP Year`<sup>[2](#fn2)</sup>). I read `VWAP Year` as a VWAP anchored to the start of the year; his settings screen is not shown `inference`.
- **How to read it** *(reference)*: a rising moving average that price falls to and holds is acting as support. The 200-day is the long-term line, the 50-day the medium-term one. A yearly VWAP is the volume-weighted average price paid since the start of the year, a reference level for where many holders' cost sits.
- **The creator's reading:**
  - AMAT bounced off the 200-day, about 33% up from its lows, about 8% below its highs. He names the 50-day (about 490) and the yearly VWAP (about 460) as the next pullback targets<sup>[7](#fn7)</sup> `explicit`.
  - GLW is trading right below the yearly VWAP with the averages bunched together, which he calls "coiling"<sup>[8](#fn8)</sup> `explicit`.
  - HOOD bounced right off the 50-day; BE could pull back to the 50-day<sup>[9](#fn9)</sup> `explicit`.
- **Why this step is here:** he treats the lines he names as targets for a dip and as entry areas<sup>[7](#fn7)</sup> `explicit`. That a bounce at a rising average marks support is the general reading above (`reference`).
- **Check before moving on:** each stock has a ranked list of support levels below price, nearest first.

### Step 5. Glance at RSI and MACD for momentum

- **Do:** check whether momentum is stretched or fading before assuming a dip is coming.
- **Look at:** [RSI](indicators.md#rsi) and [MACD](indicators.md#macd), the two panels under price.
- **How to read it** *(reference)*: RSI around the middle of its range (roughly 40 to 60) means momentum is neither stretched nor washed out; in strong uptrends RSI often stays higher, so what is neutral depends on the trend. A MACD that is "slowing" means the trend's speed is fading, not that it has reversed.
- **The creator's reading:** for AMAT, RSI is "in the middle of the range" and MACD is slowing, so he says price may drop to the 50-day<sup>[10](#fn10)</sup> `explicit`. He does not comment on RSI or MACD for the other stocks, even though the panels are on every chart<sup>[10](#fn10)</sup> `visual`.
- **Why this step is here:** to check whether momentum is cooling before a dip to the 50-day `inference`.
- **Check before moving on:** you have noted RSI (conventionally above 70 stretched, below 30 washed out, in between middle) and MACD (histogram growing, shrinking or negative) for the stock, or recorded that you skipped it.

### Step 6. Check the longer trend and how far the stock has been beaten up

- **Do:** note which phase the stock is in (steady uptrend, base after a deep drop, near highs) and how far it fell, and check the earnings multiple.
- **Look at:** the whole price history, any trendlines you draw, and the [P/E ratio](indicators.md#pe-ratio).
- **How to read it** *(reference)*: a pullback inside an uptrend keeps making higher lows and stays above its rising long averages, while a stock that is still falling keeps making lower lows. A P/E can fall because price fell, because earnings rose, or both; compare it with the price move to tell which.
- **The creator's reading:** HOOD fell from about 150 to the low 60s, "cut in more than half", which he says rinsed out weak holders; now it is in a steady upward trend, which he likes<sup>[11](#fn11)</sup> `explicit`. GLW is in an upward trend and far off its highs, with a P/E of 71 against 120 when it was near 270<sup>[11](#fn11)</sup> `explicit`. BE is a "beautiful upward trending chart"<sup>[11](#fn11)</sup> `explicit`.
- **Why this step is here:** he prefers a stock that was flushed out and is building a base, or one in a steady uptrend `explicit`.
- **Check before moving on:** each stock has a one-line trend verdict.

## How the readings turn into a conclusion

All rows are the creator's rules or conclusions in this one video. They are examples of how one analyst reads a chart, not advice or proven rules.

| If the chart shows... | He concludes... | Step | Footnote |
|---|---|---|---|
| Price hugging the upper Bollinger Band after a big run | A pullback to the mid band is normal, maybe lower | 3 | [5](#fn5) |
| Price at the lower band after a bounce off the 50-day | A setup he likes | 3, 4 | [6](#fn6) [9](#fn9) |
| A bounce off the 200-day, then price falling back | Next targets are the 50-day and the yearly VWAP | 4 | [7](#fn7) |
| Price just below the yearly VWAP with the averages bunched | The stock is "coiling" | 4 | [8](#fn8) |
| RSI mid-range and MACD slowing | Momentum is cooling; a dip to the 50-day is plausible | 5 | [10](#fn10) |
| A deep drop followed by a steady uptrend | A good entry zone | 6 | [11](#fn11) |

## What comes next

The same video continues with two steps that belong to other methods in the master list, so they are not repeated here:

- He cross-checks chart levels with market-maker call and put walls: see [Market maker GEX wall read](../methods/market-maker-gex-wall-read.md).
- He turns the levels into stair-stepped cash-secured put strikes with a position-size cap, and says he is comfortable with strikes below the lower Bollinger Band<sup>[6](#fn6)</sup>: see [Cash-secured put strike selection](../methods/cash-secured-put-strike-selection.md).

## What the video does not show

- The settings dialogs. Only the legend text is visible (for example `BB 20 SMA 2 close`), so settings are known only to that extent<sup>[2](#fn2)</sup>.
- Charts for QQQ, GLW and the photonics ETF. His QQQ, GLW and ETF readings are known from speech only; no frame of those charts was captured.
- A third lower panel (a blue line) on AMAT, HOOD and BE. Its name is not legible.
- Which line colour is the 50-day and which is the VWAP. Only the tan line (the 200-day) is identifiable.
- How he measured the 18% SMH gain on screen.
- Stop-loss or exit rules for the stocks.
- One number does not reconcile. On the SMH frame the legend reads 597.04 (mid band) and 654.03 (upper band) while price in the same frame is 603.08, near the middle band, not "hugging the upper band" as he says about the run. It may be a hover position or a different date. It is recorded, not resolved<sup>[5](#fn5)</sup>.

## Open decisions before an agent could run this

This page is reconstructed from one walkthrough. He never presents it as a named method, and he gives no numeric cut-offs. An agent cannot execute it until someone decides:

- How near counts as "at" or "near" a band, average or VWAP (a percent, or a fraction of band width), and what counts as a "bounce".
- What size of move is a "big run", and how far past a level counts as an overshoot.
- The rule that maps readings to a verdict (*stretched*, *at support*, *coiling*), and what makes a stock a "candidate". The labels are this page's shorthand, not his.
- What to do when readings conflict, for example price at the upper band but RSI mid-range.
- How to handle a stock with under 200 days of history, or a loss-making stock with no usable P/E.
- Which P/E counts as acceptable. He cites 71 versus 120 without a threshold.
- Where the market-maker expected range comes from (not shown), and how to build the saved layout in TradingView (his settings screens are not shown).

## Worked example: AMAT, step by step

Pulled from the footnotes, so you can see the method applied once from start to end.

1. Layout loads on AMAT: daily candles, price 510.03<sup>[1](#fn1)</sup>.
2. Step 3: legend shows the mid band about 484.27 with price above it<sup>[7](#fn7)</sup>. He says the mid band is in the 490 to 500 area.
3. Step 4: price bounced off the 200-day, up about 33% from lows, about 8% off highs. Targets: 50-day about 490, yearly VWAP about 460 (legend 452.38)<sup>[7](#fn7)</sup>.
4. Step 5: RSI mid-range, MACD slowing, so a dip to the 50-day is plausible<sup>[10](#fn10)</sup>.
5. Step 6: about 8% below its highs; he gives no trend verdict for AMAT<sup>[7](#fn7)</sup>.
6. Result (my shorthand, `inference`): *at support after a bounce, with a dip toward the 50-day expected*. Support ladder: about 500, 490 and 460, which he then uses for put strikes (see [what comes next](#what-comes-next)).

---

## Footnotes

Video: [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update](https://www.youtube.com/watch?v=33Yqdsr_vcA). Evidence files: `watch-output/video-data/33Yqdsr_vcA/` (transcript, frames, sheets). Timestamps are `mm:ss`; a few are approximate to within seconds.

<a id="fn1"></a>**[1] Standard layout across tickers.** [08:31](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=511s) (also 08:33, 09:21, 13:22, 14:56) `visual`. TradingView, timeframe 1D, candlesticks (green up, red down). A watchlist panel named "Portfolio RH" lists NQ1, CL1, SPY, QQQ, SMH, VIX, IWM, GLD, AMAT, GLW, HOOD, BE and others. Prices on the chart header: SPY 778.08, SMH 603.08, AMAT 510.03, HOOD 109.11, BE 273.95. Frames `cue_0110`, `cue_0111`, `cue_0116`, `cue_0121`, `cue_0126`.

<a id="fn2"></a>**[2] Legend text.** [08:33](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=513s) onward `visual`. Legend reads `BB 20 SMA 2 close`, `SMA 200 close`, `CC SMA 50 close`, `VWAP Year`, with RSI and MACD panels under price. A third blue-line panel on AMAT, HOOD and BE is not legible.

<a id="fn3"></a>**[3] QQQ range and mid band.** [07:56](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=476s) to [08:10](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=490s) `explicit`. Quote: "mid Bollinger band kind of 737 area" (captions spell it "Ballinger"). Expected two-week range about 727 to 771. No QQQ chart frame was captured, so this is from speech only.

<a id="fn4"></a>**[4] S&P 500 / SPY.** [08:24](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=504s) `explicit` (room to break out); frame at 08:31 `visual`: price 778.08, Bollinger legend 767.95 / 781.79 / 754.12 (mid / upper / lower), hand-drawn green horizontal lines and trendlines, a tan 200-day line far below.

<a id="fn5"></a>**[5] SMH run and the upper band.** [08:44](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=524s) to [08:56](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=536s) `explicit`. 18% gain from September 16 to October 6. Quote: "hugging the upper Ballinger band to pull back a little bit". On-screen legend for SMH: 597.04 mid, 654.03 upper, 540.06 lower, price 603.08. Unreconciled with the quote (see the end of "What the video does not show").

<a id="fn6"></a>**[6] Lower band as the entry zone.** [13:24](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=804s): "Hood's at the lower Ballinger band" `explicit`. [16:14](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=974s): "cash secured puts that are below the lower Ballinger band I feel comfortable with" `explicit`. Also GLW at [12:58](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=778s), BE at 15:41 (legend 276.55 / 298.42 / 254.69), and the photonics ETF below its mid band at 17:12 `explicit`.

<a id="fn7"></a>**[7] AMAT and the 200-day.** [09:23](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=563s): "beautiful bounce off that 200 day moving average" `explicit`. About 33% up from lows, about 8% below highs. [09:49](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=589s): the 490 to 500 area, "somewhere around this VWAP" (about 460) `explicit`. On screen: Bollinger legend 484.27 / 566.58 / 401.95; `VWAP Year` label 452.38 `visual`. The chart header reads "Applied Materials, Inc." (the captions say "AAT"; see [13](#fn13)).

<a id="fn8"></a>**[8] GLW coiling.** [12:29](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=749s): "trading right below the yearly VWAP", with the 200, 50, 20-day averages and VWAP together `explicit`. No GLW chart frame captured.

<a id="fn9"></a>**[9] 50-day bounces.** HOOD [13:26](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=806s) "bounce right off the 50-day moving average" `explicit`. BE [15:41](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=941s) could pull back to the 50-day; 225 put strike near the VWAP at 16:30 `explicit`.

<a id="fn10"></a>**[10] RSI and MACD on AMAT.** [10:50](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=650s) to 10:58 `explicit`. Quote: "RSI looking kind of right in in the middle of the range. MACD kind of slowing down". On screen for AMAT `visual`: RSI about 59.70 / 55.69, MACD 13.24 / 9.17 / 4.06. Not commented for the others, though panels show SMH RSI 62.81 / 52.92 and HOOD RSI 52.10 / 45.92.

<a id="fn11"></a>**[11] Trend and drawdown.** HOOD [13:40](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=820s) to [13:48](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=828s): from 150 to the low 60s, "cut in more than half", rinsed out weak hands `explicit`; the frame has a hand-drawn blue rising trendline and two red ellipses (their meaning is not narrated) `visual`. GLW [12:26](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=746s): upward trend phase, far off highs, P/E 71 versus 120 when it was at 270 `explicit`. BE [15:27](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=927s): "beautiful upward trending chart" `explicit`.

<a id="fn12"></a>**[12] Order of the walkthrough.** `inference`. Indices first (QQQ, S&P 500, SMH), then single stocks. Inside AMAT the order is price levels, portfolio, RSI/MACD, then walls; GLW is trend and VWAP, then walls, then strikes; HOOD is band and 50-day, then history, then walls; BE is business story, chart, walls, portfolio. Walls always come after the chart read and strikes last.

<a id="fn13"></a>**[13] Correction: "AAT" is AMAT.** The captions, and the earlier generated page and video note, call the stock "AAT". The chart header at [09:21](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=561s) reads "Applied Materials, Inc." with price 510.03, so it is AMAT `visual`. The captions also garble Bollinger ("Ballinger") and Unusual Whales ("unusual wells").
