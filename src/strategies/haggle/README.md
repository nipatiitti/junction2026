# haggle

A pure feedback controller for quotes, with no statistical model. Each dealer has one price level (log of a
multiple of list); delivery regions and options have small offsets on top. After a win the dealer's level goes up
by `step`, after a loss down by `step x w/(1-w)`, with `w = targetWin`. The expected move is zero when the win
rate is `w`, so each dealer settles at the win rate we chose (the one that maximises (price - cost) x win rate),
and the level follows trust growth, a price-war day or a competitor cut by itself. The step decays from
`stepStart` to `stepMin` over `stepDecay` results. An unseen dealer starts from the pooled level, which every
result also moves by `poolGain`. No quote goes under `cost x (1+minMargin)` or `cost + minMarginCents`, with
cost = `costMult` x the typical fee. Options are offered only when `canServe` passes.

Fees open at `feeOpen` x typical and rise linearly to `feeTop` by `riseLeadMin` minutes before the last pickup;
reposts open `repostBump` higher; after the deadline warning they go from `urgentOpen` to `urgentTop` in 30-minute
steps. Stops and audience come from `src/ops` (`gigShape`, `retryAfter`).

Params (defaults in `index.ts`): `startMult`, `targetWin`, `stepStart`, `stepMin`, `stepDecay`, `offsetGain`,
`offsetCap`, `poolGain`, `minMult`, `maxMult`, `costMult`, `minMargin`, `minMarginCents`, `allOptions`, `feeOpen`,
`feeTop`, `riseLeadMin`, `repostBump`, `urgentOpen`, `urgentTop`, `premiumMult`.
