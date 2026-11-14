# Lane-prior pricing

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `Desk` is a subclass of the headroom
desk whose prices start each delivery place at the offset it has in every world. Issue #200. The systems it builds on
stay as they are.

| File          | Class          | Builds on         | What it decides                                              |
| ------------- | -------------- | ----------------- | ------------------------------------------------------------ |
| `pricing.py`  | `PriorPricing` | `HeadroomPricing` | The price of a quote, lifted by its delivery place's offset  |
| `fit.py`      |                |                   | Fits the offsets on the saved weeks, into `priors.json`      |
| `priors.json` |                |                   | The fitted offsets                                           |
| `dispatch.py` | `Desk`         | the headroom desk | The system: the headroom desk with the pricing above         |

`PriorPricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `HeadroomPricing`,
with the constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/lane_prior/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/lane_prior/dispatch.py strategies/headroom/dispatch.py --jobs 2
uv run python -m strategies.lane_prior.fit            # fits priors.json from out/spread.sqlite
uv run python -m strategies.lane_prior.fit --split    # fits two halves of the seeds apart and compares them
```

Its weeks are saved with the policy `lane-prior`. The `Lane priors` line at the end of a week counts the quotes
lifted for a dear delivery place and lowered for a cheap one.

## What the saved weeks show

The handbook says that one part of the competitor's price on a lane is almost the same in every world: it is higher
where few drivers live near the delivery place. Pricing learns an offset for each pickup place, delivery place and
dealer from the week's own outcomes, 0.75% per outcome, which is too slow for a place with ten quotes a week.

`fit.py` fits a logistic win curve on the 198,543 priced quotes of the 297 saved level 8 weeks (10 seeds), with one
level for each day of each week and an offset for each pickup and delivery place:

- **The delivery place repeats between worlds.** Fitted apart on two halves of the seeds, the delivery offsets
  correlate 0.73. They run from −16% (Helsinki, Vantaa) and −11% (Espoo, Hyvinkää) to +11% (Joensuu), +15%
  (Savonlinna) and +16% (Kouvola).
- **The pickup place does not.** Its offsets correlate 0.05 between the two halves, so it has no prior.
- **The week's own learning does not catch up.** Quotes to the places with an offset under −10% won 38% of the time,
  and quotes to the places over +10% won 69%, where pricing aims at 50%: the first are quoted too high all week, and
  the second too low.

## The strategy

1. **The lift.** `priors.json` holds the fitted offset of each delivery place, in logs. A request's lift is
   `exp(prior_weight × offset)`, with the offset times the weight kept within ±`prior_limit`: × 0.89 into Helsinki
   and × 1.12 to Kouvola.
2. **It lifts the price and the maximum alike**, as dealer trust and the outage do in ceiling pricing
   (`CeilingPricing.uplift`). So admission, which takes a request only when its driver cost fits under the highest
   price we would quote, sees the lane's price too.
3. **The week still learns.** The offsets that pricing learns from the week's outcomes start at zero as before and
   move on top of the prior.

Up to level 3 every quote wins at the list price, so there is no lift.

## The variables

`Params` in `pricing.py`, exported as `PriorParams`, next to those of `strategies/headroom`.

| Variable       | Default | What it does                                                  |
| -------------- | ------- | ------------------------------------------------------------- |
| `prior_weight` | 0.7     | The share of a place's fitted offset that lifts its prices    |
| `prior_limit`  | 0.15    | No place's lift is larger than this, in logs, up or down      |

`fit.py` takes `--ridge` (default 400), the penalty that shrinks a place with few quotes towards zero. Run it again
when many new weeks are saved, and commit the new `priors.json`.
