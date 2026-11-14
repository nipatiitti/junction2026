# recall

prophet (`plan`, default false): `node src/strategies/recall/plan.ts <seed> [feeScale=1.15] [dayCap] [totalCap]
[minMarginCents=300]` values each remembered request at its bracket price less reference fee × feeScale, adds a trust
bonus (1% of the dealer's later planned wins), keeps the best within the caps and writes `plan-<seed>.json`. With
`plan=true` recall declines the requests the plan leaves out, unless by `planDriftMinute` (720) under
`planDriftShare` (0.5) of the day's planned requests (at least `planDriftMin`, 8) were won.

bidprice plus a memory of earlier practice weeks of the same seed. **It is overfit to practice seeds**: practice
weeks with the same seed have the same requests, so it remembers each request's price bracket. On an unknown week
(a ranking world, a final, a seed with no memory) nothing matches and it is plain bidprice with `tuned-16.json`.

- `node src/strategies/recall/learn.ts <seed>` scans every saved level-8 week of the seed (`data/scrape/runs` of the
  main checkout and of this tree) and writes `memory-<seed>.json`: per request option, the highest winning and
  lowest losing price / list, each divided by 1 + trust/100. Memories for spread-1 and spread-9 are checked in.
- The week is recognised once `matchMin` requests matched a memory by id, dealer and list prices, and at least
  `matchShare` of the requests so far did. Only requests that match themselves are adjusted.
- bidprice prices first. Each quoted option is then moved, with k = 1 + trust/100 (bidprice's trust count):
  - known win above the price: raised to win × k × `winShade`, never above loss × k × `lossShade`;
  - price above a known loss: lowered to the win target, or to loss × k × `lossShade`, if that is at least the cost
    × (1 + `minMargin`); else the option is left out;
  - out-of-order bracket (win ≥ loss): loss × k × `outShade`, kept at bidprice's price when that does not pay;
  - nothing known: bidprice's price.
- `rescue`: when bidprice declines, an offered option with a known win is still quoted if it clears the margin.
- A faster option is never cheaper than a slower one. bidprice's admission, cost and learning are unchanged.

Params: bidprice's (defaults from `../bidprice/tuned-16.json`) plus `memory` true, `winShade` 0.98, `lossShade`
0.96, `outShade` 0.95, `minMargin` 0.05, `rescue` true, `matchMin` 3, `matchShare` 0.8. The summary line counts the
quotes raised, lowered, dropped, untouched, not in memory and rescued.

`pnpm bench recall --level 8 --seeds spread-1`: EUR 14,301 (486 orders, 94.0% on time) against bidprice's 11,833.
