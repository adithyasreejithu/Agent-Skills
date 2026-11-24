# VIX-based cash allocation

_Generated 2026-11-23 from `_data/`. Do not edit by hand._

Using the VIX level to decide how much of the portfolio to keep in cash versus invested, with higher VIX meaning more fear and a lower cash buffer, plus a per-stock exposure cap. Used to stay liquid for volatility spikes without sitting out long calm rallies.

- **Type:** stocks analysis
- **Seen in:** 3 video(s), 2026-10-04 to 2026-11-21
- **Sites/software:** TradingView
- **Indicators:** Position size, P/E ratio, VIX, Bollinger Bands

## Step by step

### 1. Read VIX level against allocation bands

- **Does:** View the VIX chart and match the current level to a table of cash-versus-invested bands.
- **Why:** Low VIX signals greed and a higher chance of a spike, so more cash is kept; high VIX is a better time to deploy.

Seen in 2 video(s):

- [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo&t=806s) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)), 13:26 **[explicit]** Shows a slide of VIX bands and a TradingView VIX chart with Bollinger-style bands, explains VIX as the fear index, and places the current VIX around 15-17 in the slight-fear band. _Why:_ Decide how much cash to hold on the sidelines for better entries.
  - Data: VIX about 17; 15-20 band: 20-25% cash, 75-80% invested; below 15 is greed zone; VIX 2019 range 14 to sub-10
  - Tools: TradingView
  - Indicators: VIX; Bollinger Bands
  - Conclusion: Keep 20-25% cash and 75-80% invested; not too cash heavy because low VIX can persist for months.
- [Stock Market Crash Warning / VIX Hit 40 + My $240K TQQQ Trade (Options With Ryan)](https://www.youtube.com/watch?v=u4r391ks_U8&t=1134s) ([note](../../summaries/u4r391ks_U8-stock-market-crash-warning-vix-hit-40-240k-tqqq-trade.md)), 18:54 **[explicit]** Matches the VXN level to a VXN cash allocation table (extreme fear above 35 means 0-5% cash; 30-35 means 5-10% cash). At the day's start VXN was 30-35 with about 6.5% cash, so that cash was put into TQQQ. _Why:_ To follow a rules-based plan for deploying cash into fear rather than act on emotion.
  - Data: VXN above 35: 0-5% cash; VXN 30-35: 5-10% cash; about 6.5% cash left; cash deployed into TQQQ
  - Indicators: VIX
  - Conclusion: Following the allocation levels led to buying TQQQ today.

### 2. Cap single-stock put exposure

- **Does:** Limit total cash-secured put assignment value in one stock to a percentage of the portfolio.
- **Why:** Avoid concentration if assigned.

Seen in 2 video(s):

- [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo&t=946s) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)), 15:46 **[explicit]** Caps CRDO at 10% of the portfolio via cash-secured puts; with a $200K account that allows about one put (about $20K assignment). _Why:_ Keep any single assignment at or below 10% of the portfolio.
  - Data: 10% max; $200K portfolio; about $20,000 assignment per put
  - Indicators: Position size
  - Conclusion: Only one put on a $200K account.
- [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=635s) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)), 10:35 **[explicit]** States the cap on exposure per stock when layering puts. _Why:_ Limit risk of assignment in any one name; smaller for higher P/E names.
  - Data: no more than 10% of portfolio in AAT; about 5% in BE because of higher P/E
  - Indicators: Position size; P/E ratio
  - Conclusion: Room for one or two more AAT puts.

## Rules of thumb

- Do not go all in when the VIX is very low; keep cash (about 20-25% at VIX 15-20). **[explicit]** ([The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)))
- Never allocate more than 10% of the portfolio to a single stock via cash-secured puts. **[explicit]** ([The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md)))
- Keep a higher P/E stock like BE to about 5% of the portfolio. **[explicit]** ([AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)))
- Deploy cash by VXN band: above 35 hold 0-5% cash, 30-35 hold 5-10%, 25-30 hold 10-20%. **[visual]** ([Stock Market Crash Warning / VIX Hit 40 + My $240K TQQQ Trade (Options With Ryan)](https://www.youtube.com/watch?v=u4r391ks_U8) ([note](../../summaries/u4r391ks_U8-stock-market-crash-warning-vix-hit-40-240k-tqqq-trade.md)))

## Videos using this method

- 2026-11-21 Options With Ryan: [Stock Market Crash Warning / VIX Hit 40 + My $240K TQQQ Trade (Options With Ryan)](https://www.youtube.com/watch?v=u4r391ks_U8) ([note](../../summaries/u4r391ks_U8-stock-market-crash-warning-vix-hit-40-240k-tqqq-trade.md))
- 2026-10-10 Options With Ryan: [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md))
- 2026-10-04 Options With Ryan: [The Wheel Options Strategy / My NEW Credo Technology (CRDO) Trading Plan 2026 - Options With Ryan](https://www.youtube.com/watch?v=ioSr_jyNKoo) ([note](../../summaries/ioSr_jyNKoo-the-wheel-options-strategy-my-new-credo-crdo-trading-plan-2026.md))
