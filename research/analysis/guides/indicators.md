# Indicator fact sheet

_Written 2026-11-20. This page is **reference**: general market knowledge written to teach, not something any creator said. What a creator actually did with an indicator is in the footnotes of each method guide. Not investment advice._

Use it as a lookup. When a guide or report names a term, find it here to learn **what it is, how it is built and how to read it anywhere**. The method guides cover only how and why a term is used in one particular analysis.

**Contents:** [Candlestick chart](#candlestick-chart) · [Timeframe](#timeframe) · [Moving averages](#moving-averages) · [Bollinger Bands](#bollinger-bands) · [VWAP](#vwap) · [RSI](#rsi) · [MACD](#macd) · [P/E ratio](#pe-ratio)

**A note that applies to every indicator below.** All of them are built from past prices (and sometimes volume). None of them sees the future. They describe what price has been doing, which is why they are used to frame odds and levels, never to promise an outcome. Two indicators agreeing is more informative than one, but several indicators built from the same price history often move together, so agreement is weaker evidence than it looks.

---

<a id="candlestick-chart"></a>
## Candlestick chart

- **In one line:** a price chart where each bar shows one period's open, high, low and close.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 1](technical-read-on-a-stock-chart.md#step-1-open-the-ticker-on-the-standard-chart-layout).
- **How it is built:** each candle covers one period (a day on a daily chart). The thick body runs from the open to the close. The thin lines (wicks) reach to the period's high and low. Convention: a green or hollow body means the close was above the open; red or filled means below.
- **How to read it:** long bodies mean strong one-directional moves; long wicks mean price went somewhere and was pushed back; a run of green candles is a rally, a run of red candles a decline.
- **Good for:** seeing the shape of price movement, gaps and reversals at a glance, and giving a base layer for every indicator drawn on top.
- **Not good for:** telling you why price moved.
- **Common mistake:** reading a single candle as a signal. One candle is noise; patterns across several candles at a meaningful level carry more weight.

<a id="timeframe"></a>
## Timeframe

- **In one line:** how much time one candle represents (1 minute, 1 hour, 1 day, 1 week).
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 1](technical-read-on-a-stock-chart.md#step-1-open-the-ticker-on-the-standard-chart-layout).
- **Why it matters:** every indicator is calculated in candles. "50-day moving average" is a daily-chart statement; on an hourly chart the same setting means 50 hours. Always check which timeframe a chart is on before comparing readings.
- **Rule of thumb:** a longer timeframe shows the bigger trend and is harder to fool; a shorter timeframe shows timing but contains more noise. Many analysts read the longer one first, then zoom in.
- **Common mistake:** mixing readings from different timeframes (a daily RSI with a weekly average) without noticing.

---

<a id="moving-averages"></a>
## Moving averages (20-day, 50-day, 200-day)

- **In one line:** the average closing price over the last N periods, redrawn every period, so it forms a smooth line that follows price.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 4](technical-read-on-a-stock-chart.md#step-4-locate-price-against-the-200-day-50-day-and-yearly-vwap).
- **How it is built:** add up the last N closes and divide by N (the simple version). Each new day the oldest close drops out and the newest enters, so the line moves. An exponential version (EMA) weights recent days more; if a chart does not say, assume simple.
- **The three common lengths:**

| Length | Usually taken to represent | How it tends to behave |
|---|---|---|
| 20-day | short-term trend, roughly one trading month | hugs price closely; breaks often |
| 50-day | medium-term trend | the level many traders watch for pullback support |
| 200-day | long-term trend | slow; widely used as the dividing line between a long-term uptrend and downtrend |

- **How to read it:** price above a rising average means the trend over that horizon is up; price below a falling one means it is down. When price falls to a rising average and holds, the average is acting as **support**; when price rises to a falling average and fails, it is acting as **resistance**. The slope matters as much as the position: a flat average says "no trend".
- **Why they work as levels:** not because of anything magical in the maths. Many participants watch the same lines, so many orders cluster there. This is commonly explained as partly self-fulfilling, and such levels often fail when the market is stressed.
- **Not good for:** early warning. Because it averages the past, a moving average always lags price.
- **Common mistakes:** expecting a bounce at an average every time; treating a brief poke below as a trend change; forgetting that the average moves each day, so the level is a moving target.
- **Related terms:** *golden cross* is the 50-day crossing above the 200-day (read as a long-term turn up); *death cross* is the 50-day crossing below it. Both are lagging confirmations, not forecasts.

---

<a id="bollinger-bands"></a>
## Bollinger Bands

- **In one line:** a channel drawn around a moving average that widens when price is volatile and narrows when it is calm.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 2](technical-read-on-a-stock-chart.md#step-2-set-the-index-range-and-near-term-support-qqq-sp-500), [step 3](technical-read-on-a-stock-chart.md#step-3-check-how-stretched-price-is-against-the-bollinger-bands).
- **How it is built:** three lines. The **middle band** is a 20-period simple moving average. The **upper and lower bands** sit 2 standard deviations above and below it. (Standard deviation is a statistic for how widely recent prices have scattered around their average, so a more volatile market pushes the bands apart.)
- **Default settings:** 20 periods, 2 standard deviations.
- **How to read it:**
  - Most price action stays inside the bands, but not a guaranteed share of it, and moves outside are common in strong trends. Price touching or hugging the **upper band** means the move is stretched relative to its recent average; touching the **lower band** means it is stretched downward.
  - The **middle band** is the average price is pulled back toward. After a large run that rides the upper band, a return toward the middle band is a common outcome, and it is often treated as the first area of support.
  - **Narrow bands** (a "squeeze") mean volatility has been low and are commonly followed by a larger move in either direction, though not reliably.
  - In a strong trend, price can stay near an outer band for a long time. A touch is not an automatic reversal signal.
- **Good for:** judging how stretched a move is and picking likely pullback levels.
- **Not good for:** direction. The bands say how far, not which way.
- **Common mistakes:** selling or buying purely because price touched a band; ignoring that the bands are themselves based on the 20-day average, so on a daily chart the middle band is the 20-day moving average.

---

<a id="vwap"></a>
## VWAP (volume-weighted average price)

- **In one line:** the average price at which a stock has traded, counting heavy-volume prices more than light-volume ones.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 4](technical-read-on-a-stock-chart.md#step-4-locate-price-against-the-200-day-50-day-and-yearly-vwap).
- **How it is built:** running total of (price × volume) divided by the running total of volume, starting from an anchor point. On intraday charts the anchor is normally the start of each day. Charting software also lets you anchor it to a longer period, a week, month or **year**, or to a specific event, which gives a "yearly VWAP": the volume-weighted average price since the start of that year.
- **How to read it:** it works like a fair-value line for the period since its anchor. Price above it means buyers since the anchor are, on average, in profit; price below it means they are underwater. For a longer anchor, traders use it as a rough reference for where recent buyers' average cost sits. It is a heuristic, because VWAP reflects trades, not holdings.
- **Good for:** a level to watch for support or resistance, and a quick check of whether current price is rich or cheap relative to the period's volume-weighted average.
- **Not good for:** short signals on its own, and it is meaningless without knowing the anchor.
- **Common mistakes:** comparing a daily-reset VWAP with a yearly one as if they were the same thing; forgetting that a longer-anchored VWAP changes slowly and so behaves like a long-term average.

---

<a id="rsi"></a>
## RSI (relative strength index)

- **In one line:** a 0 to 100 gauge of how strong recent gains have been compared with recent losses.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 5](technical-read-on-a-stock-chart.md#step-5-glance-at-rsi-and-macd-for-momentum).
- **How it is built:** over the last 14 periods, compare the average size of up-moves with the average size of down-moves, then scale the ratio to a 0–100 range (Wilder's formula, which uses a smoothed average rather than a plain one). More and bigger gains push it up; more and bigger losses pull it down.
- **Default settings:** 14 periods; reference lines at 70 and 30.
- **How to read it:**
  - Above **70** is conventionally called "overbought" (rallied hard and fast); below **30** "oversold".
  - A **mid-range** reading, roughly 40 to 60, says momentum is neither stretched nor washed out, so there is no momentum argument for a turn either way. In strong uptrends RSI often stays between roughly 40 and 80, so what counts as neutral depends on the trend.
  - **Divergence**: price makes a new high but RSI makes a lower high, which suggests the move is losing force.
- **Good for:** judging whether a move is momentum-driven or exhausted.
- **Not good for:** timing. In a strong uptrend RSI can sit above 70 for weeks; "overbought" does not mean "about to fall".
- **Common mistake:** treating 70 and 30 as automatic sell and buy signals.

---

<a id="macd"></a>
## MACD (moving average convergence divergence)

- **In one line:** a momentum indicator built from two exponential moving averages that shows whether a trend is gathering or losing speed.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 5](technical-read-on-a-stock-chart.md#step-5-glance-at-rsi-and-macd-for-momentum).
- **How it is built:** the **MACD line** is the 12-period EMA minus the 26-period EMA. The **signal line** is a 9-period EMA of the MACD line. The **histogram** is the gap between the two lines.
- **Default settings:** 12, 26, 9.
- **How to read it:**
  - MACD line **above zero**: the shorter average is above the longer one, so the trend is up; **below zero**: down.
  - MACD line **crossing above the signal line** is read as momentum turning up; crossing below it, turning down.
  - **Histogram shrinking** toward zero while price still rises means momentum is slowing, which is sometimes noticed before price itself turns, though not reliably. This is the sense in which a trader says "MACD is slowing".
- **Good for:** confirming whether a move still has speed behind it.
- **Not good for:** precise entries; it lags because it is built from averages, and it produces many false crosses in sideways markets.
- **Common mistake:** treating each cross as a trade signal without checking the larger trend.

---

<a id="pe-ratio"></a>
## P/E ratio (price-to-earnings)

- **In one line:** the stock price divided by the company's earnings per share, in effect how many dollars investors pay for each dollar of yearly profit.
- **Used in:** [Technical read on a stock chart](technical-read-on-a-stock-chart.md), [step 6](technical-read-on-a-stock-chart.md#step-6-check-the-longer-trend-and-how-far-the-stock-has-been-beaten-up).
- **How it is built:** price ÷ earnings per share. **Trailing P/E** uses the last 12 months of reported earnings; **forward P/E** uses analysts' estimates for the next 12.
- **How to read it:** a higher P/E means investors pay more for each dollar of profit, usually because they expect fast growth; a lower P/E means a cheaper price per dollar of profit, sometimes because growth is expected to be slow or earnings are at risk. A P/E can fall because price fell, because earnings rose, or both. One-off items can also distort a single year's earnings.
- **It is only meaningful when earnings are positive.** A loss-making company has no usable P/E.
- **Good for:** a quick sanity check of whether a price rise is backed by earnings, and for comparing similar companies.
- **Not good for:** comparing across very different industries, or timing.
- **Common mistakes:** calling a low P/E "cheap" without asking why; comparing a trailing figure with a forward one.
- **Note on this page:** unlike the others, the P/E ratio is a valuation measure, not a chart indicator. It is listed because creators check it alongside charts.
