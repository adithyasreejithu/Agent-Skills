# Cash-secured put strike selection

_Generated 2026-11-23 from `_data/`. Do not edit by hand._

Choosing the expiry and strike of a cash-secured put on an options chain by delta, premium return and distance to assignment, with the chart used as a sanity check. Used as the entry leg of the wheel strategy.

- **Type:** options analysis
- **Seen in:** 2 video(s), 2026-10-04 to 2026-10-10
- **Sites/software:** TradingView, Unidentified brokerage app, Unidentified options broker
- **Indicators:** Bollinger Bands, 50-day moving average, VWAP, Delta, Theta decay, Premium ROI, Mid price

## Step by step

### 1. Set expiry and delta targets

- **Does:** Decide on days to expiration and a delta range before opening the chain.
- **Why:** Capture the fastest theta decay while keeping enough time to be right.

Seen in 1 video(s):

- [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo&t=980s) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)), 16:20 **[explicit]** States the setup: 25-30 days to expiration (up to 35), 25-30 delta, drop to 20 delta or lower for safety, hold to expiration or roll up if 80% profit with about 20 days left. _Why:_ Stay inside the 60-day theta decay window; far-dated puts do not pay for the time risk.
  - Data: 25-35 DTE; 25-30 delta; 20 delta when cautious; roll at 80% profit with ~20 days left
  - Indicators: Delta; Theta decay
  - Conclusion: 30 days and 25-30 delta is his standard.

### 2. Compare strikes on the options chain

- **Does:** Open the options chain for the chosen expiry and compare strikes by delta, mid price and ROI on capital.
- **Why:** Balance premium against chance of assignment.

Seen in 1 video(s):

- [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo&t=1054s) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)), 17:34 **[explicit]** Opens the CRDO chain for October 30th (28 days), clicks the 200 strike bid to see the mid price of $935 (about 4.9% ROI at roughly 29 delta), and compares with the 190 strike (21 delta, about $560) and 185 strike. _Why:_ Higher delta means more premium but more assignment risk; lower delta means less premium and less risk.
  - Data: 200 strike mid $935, ~4.9% ROI; 190 strike 21 delta, ~$560; 185 strike needs 15% drop; 200 strike needs 8% drop
  - Tools: Unidentified options broker
  - Indicators: Delta; Premium ROI; Mid price
  - Conclusion: Picks around 190 (21 delta) or 185 for safer assignment distance; 25 delta is typical these days.

### 3. Check Bollinger Bands for entry risk

- **Does:** Look at where price sits relative to Bollinger Bands on the chart before choosing how far out of the money to sell.
- **Why:** Price outside the bands tends to revert to the mean, so being at the upper band means more near-term pullback risk.

Seen in 2 video(s):

- [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo&t=1137s) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)), 18:57 **[explicit]** Notes CRDO trading near the upper Bollinger band after a two-week run, and that it breached the lower band before and snapped back in. _Why:_ Judge whether to take a safer strike given the stock's elevated position and volatility.
  - Data: price near upper Bollinger band; prior lower band breaches reverted; two-week run
  - Tools: TradingView
  - Indicators: Bollinger Bands
  - Conclusion: A bit more risk here, so he leans toward the safer 185-190 strike.
- [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=583s) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)), 09:43 **[explicit]** For each candidate, places cash-secured put strikes at or below the lower or mid Bollinger Band, the 50-day average or VWAP, and shows the strikes already layered in his account. _Why:_ Get assigned only at prices he is comfortable owning while collecting rich premium.
  - Data: AAT puts at 500, 475, 445; GLW 135 to 140 strikes below lower band; HOOD 105 and 99 puts, maybe low 90s next; BE 240 and 225 puts, 225 near VWAP; photonics ETF around 23 strike near lower band, monthly options only
  - Tools: TradingView; Unidentified brokerage app
  - Indicators: Bollinger Bands; 50-day moving average; VWAP
  - Conclusion: Layer puts at several strikes rather than going in at one price.

## Rules of thumb

- Stay within about 25-35 days to expiration; do not sell far-dated puts because time decay does not pay for the risk. **[explicit]** ([The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)))
- Typical delta is 25-30; go to 20 or lower for caution. **[explicit]** ([The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)))
- Layer into a stock with several strikes rather than going all in at one strike. **[explicit]** ([AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)))
- Prefer puts below the lower Bollinger Band. **[explicit]** ([AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)))
- For a $100K account a high-priced stock like COR ties up too much per put, so use a smaller ETF. **[explicit]** ([AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)))

## Videos using this method

- 2026-10-10 Options With Ryan: [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md))
- 2026-10-04 Options With Ryan: [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md))
