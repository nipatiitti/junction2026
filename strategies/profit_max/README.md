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

## Bench

To be played.
