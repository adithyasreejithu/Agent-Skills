# Options Trading — Beginner's Guide (Notes)

**Source video:** [Options Trading for Beginners](https://www.youtube.com/watch?v=2Ii5Hl98s9E)
**Length:** ~37 minutes · **Format:** narrated explainer + live demo (Robinhood, Moomoo paper trading)
**Purpose of these notes:** define every term precisely, show the math behind it, and note how each concept is actually useful when you're managing your own investments (not just trading options for its own sake).

---

## 1. The core idea: what an option actually is

> An option is a financial contract that gives the holder **the right, but not the obligation**, to buy or sell an asset in the future at a price agreed on today.

That "right but not obligation" phrase is the single most important sentence in options — memorize it. It's what separates an option from a regular stock trade (where you're obligated the instant you buy) or a futures contract (obligated at expiration).

**Real-world analogy used in the video:** a home-sale contingency offer. You pay a non-refundable deposit for the *right* to buy a house at an agreed price within 30–60 days. If your own house doesn't sell, you walk away and lose only the deposit — not the full price of the house. That deposit is functionally identical to an **option premium**.

**Why this matters for investing:** options let you control the *price* and *timing* of a future trade for a small upfront cost, instead of committing full capital now. That's the source of both their leverage (upside) and their risk (the deposit/premium can go to zero).

---

## 2. Core vocabulary (definitions you need cold)

| Term | Definition | Investing use |
|---|---|---|
| **Underlying asset** | What the contract controls — usually 100 shares of a stock, or an index (e.g., S&P 500) | Determines what moves the option's value |
| **Derivative** | Any instrument whose value is *derived* from something else (the underlying) | Options, futures, and swaps are all derivatives — explains why option prices move with the stock |
| **Option premium** | The price you pay (buyer) or receive (seller) for the contract. Non-refundable once spent. Quoted per-share, but each contract = 100 shares, so multiply by 100 for actual cost | This is your max loss as a buyer, and your income as a seller |
| **Strike price** | The fixed price at which you can buy (call) or sell (put) the underlying | Compare to current market price to judge if a contract is "in," "at," or "out" of the money |
| **Expiration date** | The date the contract stops existing. After this, it's worthless if not exercised | Time pressure — the closer you get, the faster value erodes |
| **Exercise** | Actually using your right to buy/sell at the strike price | Requires having full capital ready (e.g., $10,000 to buy 100 shares at $100) — most traders never do this; they sell the *contract* instead |
| **Call option** | Right to **buy** at the strike price — a bullish bet | Used when you expect the price to rise |
| **Put option** | Right to **sell** at the strike price — a bearish bet | Used when you expect the price to fall, or to insure a position you own |
| **In the money (ITM)** | Contract has real/intrinsic value if exercised now (call: price > strike; put: price < strike) | Tells you if exercising today would be profitable |
| **At the money (ATM)** | Strike price ≈ current price | Break-even zone |
| **Out of the money (OTM)** | Exercising today would not be profitable (call: price < strike; put: price > strike) | Cheaper premium, but needs a bigger move to become profitable |
| **Bid / ask (spread)** | Bid = what buyers will pay; ask = what sellers want. The gap between them | Use **limit orders**, not market orders, on options — spreads can be wide, especially on low-volume contracts, so a market order can fill at a bad price |

---

## 3. What determines an option's price (premium)

Premium = **Intrinsic Value + Extrinsic Value**

- **Intrinsic value** ("real value"): the actual profit if exercised right now.
  - Call: `max(0, share price − strike price)`
  - Put: `max(0, strike price − share price)`
  - Example from the video: $100 strike call, stock at $120 → intrinsic value = $20. If OTM, intrinsic value is always exactly $0 (never negative).

- **Extrinsic value** ("time value"): the extra amount buyers are willing to pay above intrinsic value, based on:
  1. **Time until expiration** — more time = more chance to become profitable = more extrinsic value.
  2. **Volatility of the underlying** — a more volatile stock has a wider range of possible outcomes, so its options are worth more.
  3. **Probability of profitability** — how likely the market thinks it is that the contract finishes ITM.

- **Time decay**: extrinsic value shrinks continuously as expiration approaches — *even if the stock price doesn't move at all*, the option loses value simply because less time remains for it to become profitable. This is the single most important risk mechanic in options: doing nothing still costs you money if you're a buyer.

**Investing takeaway:** if you're new, this explains why options are often described as "wasting assets" — unlike a stock, which you can hold forever, an option has a built-in expiration on your thesis being right. If you're going to buy options, you're betting on both *direction* and *timing*.

---

## 4. Call options — worked example (bullish bet)

Setup: stock at $100/share. You buy a **call** with a $100 strike, 1-month expiration, $5 premium (= $500 total for one contract, since 1 contract = 100 shares).

| Scenario | What happens |
|---|---|
| Stock drops to $95 | Call is OTM (why buy at $100 when the market sells at $95 anyway); premium falls e.g. to $3 → you're down $200 if you sell now, or you can hold and hope it recovers before expiration |
| Stock rises to $105 | Break-even point: strike + premium ($100 + $5 = $105). Exercising here nets you back exactly what you paid |
| Stock rises to $120 | ITM by $20/share ($2,000 across 100 shares). Net profit after the $500 premium = $1,500 (or you can just sell the contract itself for a similar profit without ever exercising) |
| Stock drops to $85, near expiration | Premium collapses toward worthless (e.g., $0.50) — you either sell for pennies on the dollar or let it expire, losing up to 100% of your $500 |

**Key rule of thumb:** call value increases as the stock price rises and decreases as it falls, and it decays over time regardless of price movement.

**Most options are never exercised** — to exercise the example above you'd need the full $10,000 to actually buy 100 shares at $100. Instead, traders typically just *sell the contract itself* to lock in gains or cut losses.

---

## 5. Put options — worked example (bearish bet / insurance)

Setup: stock at $100/share. You buy a **put** with a $100 strike, 1-month expiration, $5 premium ($500 total).

Real-estate analogy given: agreeing to sell your $300,000 house — someone pays you a $5,000 deposit to lock in the right to force you to buy it from them at $300,000 even if the market crashes to $250,000. A put on a stock works the same way but on the stock's price.

| Scenario | What happens |
|---|---|
| Stock falls to $85 by expiration | Put is deep ITM — the right to sell at $100 is very valuable when the market price is $85. Premium might rise to $20 → sell the contract for $1,500 net profit on a $500 investment (300% ROI in this example) |
| Stock rises to $120 | Put moves further OTM — nobody wants the right to sell at $100 when the market pays $120. Premium collapses (e.g., to $0.25) → near-total loss |

**Investing takeaway — the "insurance" framing:** puts are the natural hedge for a stock you already own. If you hold shares and are worried about a drop (e.g., before earnings), buying a put on those shares caps your downside — if the stock craters, the put's gain offsets the share loss. This is functionally an insurance policy, and the premium is the cost of that insurance.

---

## 6. Intrinsic vs. extrinsic — the concept that explains time decay

Worked example from the video: a call, strike $100, stock at $120, 1 month to expiry, trading for a $25 premium.
- Intrinsic value = $120 − $100 = **$20**
- Extrinsic value = $25 − $20 = **$5** (the market's "hope premium" for further gains before expiry)

As expiration nears, that $5 of extrinsic value bleeds toward $0 — this is **time decay** (often called "theta" in options jargon, though the video doesn't use that Greek-letter term). Even a stock that goes nowhere will cause an option you own to lose value over time.

**Practical implication:** if you're buying options, time decay works *against* you constantly. If you're selling options (e.g., covered calls, discussed below), time decay works *for* you — you're the one collecting the premium that shrinks toward zero, which you get to keep.

---

## 7. Why people trade options — three groups, three purposes

This is the part most directly useful for someone using options to *support investing* rather than pure gambling.

### (a) Speculators — betting on price direction for profit
Example: a trader expects "John's Semiconductors" to beat earnings, so they buy call options expiring right after the earnings date. If right, big payoff (leverage); if wrong or flat, the contract can go to zero. Pure directional bet, no underlying stock ownership required.

### (b) Hedgers — using options as insurance on a position you own
Example: an investor owns semiconductor stock long-term and is bullish overall, but worried a "priced for perfection" stock could drop hard on an earnings miss. They buy **puts** expiring right after earnings as insurance. If the stock rises, the puts expire worthless (an acceptable "insurance premium" cost) — the equity gains fully. If the stock drops, put gains offset (partially or fully) the equity losses.

> **This is the most directly applicable concept for a long-term investor**: you don't have to sell your shares to protect against a known risk event (earnings, a macro announcement) — a protective put lets you keep your position while limiting the downside for a defined window, for a known, capped cost (the premium).

### (c) Income investors — selling covered calls
Example: an investor holds 10,000 shares long-term and would be happy to sell at $15/share. Instead of just placing a limit sell order, they **sell** (write) 100 call options at the $15 strike, collecting the premium immediately as income.
- If the stock stays below $15 through expiration: they keep the shares *and* the premium — pure extra income on a position they were holding anyway.
- If the stock rises above $15 and the option is exercised: they're forced to sell at $15 (the price they wanted anyway) — plus they already pocketed the premium.

This is the classic **"wheel strategy"** groundwork: sell covered calls near your cost basis on shares you own; if called away, you've profited on both the stock and the premium; then you can re-enter via selling cash-secured puts, repeating the cycle. (This exact "wheel" language shows up in your other notes file on stock-analysis methodology — the same author/strategy family.)

**Together, hedgers and speculators provide the liquidity** that lets these contracts trade freely; income sellers are effectively "renting out" the optionality embedded in shares they already own.

---

## 8. Reading a real options chain (Robinhood/Moomoo demo, ~20:00–31:00)

Key mechanics shown on-screen:
- **Expiration dates** are listed across the top of the option chain (near-term weekly dates out to multi-year LEAPS, e.g., Jan 2028).
- **Call/Put toggle** and **buy/sell toggle** — same chain, four possible actions (buy call, sell call, buy put, sell put).
- **Break-even price** is always strike ± premium, not just the strike — the chain typically displays this for you directly.
- **Contracts closer to expiration swing in price much faster** (bigger % moves per $1 stock move) because there's less extrinsic value cushioning the price — same underlying move causes a bigger relative price swing.
- **Contract quoting convention:** displayed price is per-share; actual cost = displayed premium × 100 (one contract = 100 shares).
- The presenter repeatedly stresses: **use limit orders on options**, since thin volume can create wide bid/ask spreads that punish market orders.

---

## 9. Practical, low-risk on-ramp mentioned in the video

1. **Paper trading first** — Moomoo (and most brokers) offer simulated trading with fake money that mirrors real market prices. Explicitly recommended as the single best way to learn before risking capital.
2. Progress only to real money if you're **consistently profitable in paper trading**.
3. Options are explicitly called "not for everyone" and a "high-risk activity" — appropriate primarily for investors who already understand the underlying stock/index well.

---

## 10. Consolidated rules of thumb

1. **"Right, not obligation"** is the entire distinction between owning an option and owning the stock — internalize this before anything else.
2. **Contract = 100 shares.** Every premium, break-even, and profit number must be multiplied by 100 to know the real dollar amount.
3. **Time decay is constant and directionless** — an option loses value every day it sits, independent of the stock price, purely from time passing.
4. **Most options are never exercised** — traders buy/sell the *contracts themselves* to realize gains/losses, since exercising ties up much more capital.
5. **Puts = insurance for stock you own; calls = leveraged upside bets; selling calls on stock you own = income.** These three uses map to hedgers, speculators, and income investors respectively.
6. **Use limit orders, not market orders**, on options due to wide bid/ask spreads on lower-volume contracts.
7. **Practice on a paper-trading platform before risking real capital.**
8. Options nearer to expiration are more volatile in percentage terms — don't mistake a cheap, near-dated OTM option for a "safe" small bet; it can lose 50%+ of its value in a single day.

---

## Suggested next step

If you want to go deeper into the **income/wheel strategy** angle specifically (selling covered calls and cash-secured puts as a recurring income process), your existing notes at `watch-output/stock-analysis-methodology.md` document a real trader's end-to-end workflow for exactly that — worth reading together with this glossary.
