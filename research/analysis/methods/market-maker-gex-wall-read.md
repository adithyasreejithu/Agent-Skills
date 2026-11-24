# Market maker GEX wall read

_Generated 2026-11-23 from `_data/`. Do not edit by hand._

Reading market maker gamma exposure data to find call walls (resistance), put walls (support) and acceleration levels, plus the expected two-week market maker range of an index. Used to check where hedging flows might support or accelerate a move before choosing strikes.

- **Type:** options analysis
- **Seen in:** 2 video(s), 2026-10-10 to 2026-11-21
- **Sites/software:** Unusual Whales, Unidentified charting site
- **Indicators:** GEX, Call wall, Put wall, Expected market maker range

## Step by step

### 1. Find call and put walls

- **Does:** Open the GEX or market maker view for a ticker and read call wall, put wall and acceleration levels.
- **Why:** Locate resistance, support and zones where moves may accelerate.

Seen in 1 video(s):

- [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA&t=658s) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md)), 10:58 **[explicit]** Opens market maker/GEX data for each candidate, reads where call and put walls sit and whether support exists, and for QQQ reads the expected two-week range. _Why:_ To see whether option market makers provide support under a candidate and where upside resistance is before selling puts.
  - Data: QQQ expected range high 771, low 727; AAT no put wall; above 512 may accelerate, resistance 535; GLW call wall 165, acceleration below 145; HOOD call wall 120; BE put wall support at 270; photonics ETF call wall at 30
  - Tools: Unusual Whales
  - Indicators: GEX; Call wall; Put wall; Expected market maker range
  - Conclusion: BE has put wall support so this may be the pullback; AAT has no put wall support so more downside is possible.

### 2. Read expected market maker range

- **Does:** Read the option-implied expected move range of an index ETF for the coming days.
- **Why:** To size realistic downside and upside from volatility and options pricing.

Seen in 1 video(s):

- [Stock Market Crash Warning / VIX Hit 40 + My $240K TQQQ Trade (Options With Ryan)](https://www.youtube.com/watch?v=u4r391ks_U8&t=405s) ([note](../../summaries/u4r391ks_U8-stock-market-crash-warning-vix-hit-40-240k-tqqq-trade.md)), 06:45 **[explicit]** Reads the market maker move for QQQ based on volatility: up to 644 and down to 585 over the next 7 days. _Why:_ To see the potential downside implied by volatility and options pricing.
  - Data: upper range 644; lower range 585; 7-day horizon
  - Tools: Unidentified charting site
  - Indicators: Expected market maker range
  - Conclusion: A final Monday flush is possible but VIX/VXN levels make it less typical.

## Videos using this method

- 2026-11-21 Options With Ryan: [Stock Market Crash Warning / VIX Hit 40 + My $240K TQQQ Trade (Options With Ryan)](https://www.youtube.com/watch?v=u4r391ks_U8) ([note](../../summaries/u4r391ks_U8-stock-market-crash-warning-vix-hit-40-240k-tqqq-trade.md))
- 2026-10-10 Options With Ryan: [AI Stock Pullback Coming? 3 Stocks Im Preparing To Buy + BE & HOOD Update (Options With Ryan)](https://www.youtube.com/watch?v=33Yqdsr_vcA) ([note](../../summaries/33Yqdsr_vcA-ai-stock-pullback-coming-3-stocks-im-preparing-to-buy-be-hood-update.md))
