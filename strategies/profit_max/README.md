# Expected-profit pricing

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md), as `ceiling` builds on the root `dispatch.py`:
its `Desk` is a subclass of the ceiling desk that prices with the strategy below. Issue #187. Ceiling and the root
system stay as they are.

| File          | Class           | Builds on        | What it decides                                        |
| ------------- | --------------- | ---------------- | ------------------------------------------------------ |
| `pricing.py`  | `ProfitPricing` | `CeilingPricing` | The price with the most expected margin on a win curve |
| `dispatch.py` | `Desk`          | the ceiling desk | The system: the ceiling desk with the pricing above    |

## Run it

From the repository root:

```sh
uv run strategies/profit_max/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/profit_max/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `profit-max`. The pricing line at the end of a week reads like ceiling's, plus how
many quotes the curve put under and over the learned price.

## The strategy

Ceiling pricing learns one price per request: the list price times a multiplier where half of our quotes win, and
quotes it whatever the car costs us, unless the driver cost floor is above it. That leaves money in two places: a
cheap car is worth winning more often at a little less, and a dear car is not worth winning at a price that barely
pays its driver.

1. **The win curve.** The learned price is the middle of a logistic curve: at the middle half of the quotes win, and
   the chance falls by `spread` (0.08) in logs for each step of e: at 8% over the middle 27% win, at 8% under 73%.
2. **The best price.** Between the driver cost floor (cost × 1.10) and the lifted maximum, the desk tries `grid` (41)
   prices and quotes the one where (price − cost × 1.10) × chance is highest. With cost × 1.10 at 50% of the middle,
   the best price is 12% under the middle (84% win); at 70%, 6% under (69%); at 90%, 4% over (39%).
3. **The maximum.** When the learned price sits at the maximum, more than half of those quotes win, so the middle is
   above it. The share of capped quotes that won (smoothed with `capped_prior` = 10 quotes at one half) moves the
   middle up by `spread × log(share / (1 − share))`.
4. **Learning.** Each outcome moves the learned price by `step × (won − chance)`, the chance that the curve gave the
   price we sent. A quote at the middle learns exactly as in ceiling; a win at a price the curve called likely moves
   it little.

Everything else is ceiling's: the maximum and its lift for trust and the outage, the war, the timed return leg.

## Offline replay

`analysis.replay`'s quote replay, run with this desk on the ten distinct saved `ceiling` weeks (seeds `spread-1` to
`spread-5`, two each). Admission does not change, so the same 3,233 orders are kept. Of the quotes whose answer the
week can tell, 43.2% win against 45.4% for ceiling's own, but 3,058 quotes have an unknown answer against 2,040 for
ceiling, because they differ from the week's price. The replay cannot price this idea; the bench below does.

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), the same 1,327 orders are kept. The curve put 218
to 321 quotes a week under the learned price and 225 to 401 over it, and 47.7% of the known answers win against 54.7%
for ceiling's own.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy `profit-max`.

| Seed       |  `ceiling` | `profit_max` | Difference | On time |
| ---------- | ---------: | -----------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |    €9,076.00 |   −€755.09 |   98.2% |
| `spread-2` |  €6,673.95 |    €6,537.88 |   −€136.07 |   98.7% |
| `spread-3` |  €4,312.02 |    €3,629.56 |   −€682.46 |   99.1% |
| Total      | €20,817.06 |   €19,243.44 | −€1,573.62 |         |

Behind ceiling on all three seeds, by €1,573.62 in total. Its won orders paid 1.353 × the list price against 1.373 for
ceiling, and it won 926 orders against 952. Matched by order id with ceiling's weeks, it won 127 orders that ceiling did
not (€1,928 of margin) and lost 153 that ceiling won (€3,261): the curve gave up dear cars to win cheap ones.
Its `spread` of 0.08 is an assumption, not a fit; as it stands, the curve costs money.
