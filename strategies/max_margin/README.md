# Max margin

A dispatch system built on [`strategies/war_guard`](../war_guard/README.md) and
[`strategies/slack_fees`](../slack_fees/README.md), the two systems that beat `ceiling` in #188: its `Desk` is a
subclass of the war-guard desk that charges each world, lane and dealer as much as it accepts, and pays the patient
fees of slack fees. Issue #203. The systems it builds on stay as they are.

| File          | Class        | Builds on          | What it decides                                            |
| ------------- | ------------ | ------------------ | ---------------------------------------------------------- |
| `pricing.py`  | `MaxPricing` | `WarGuardPricing`  | The price of each quote, up to 2.0 x the list price        |
| `dispatch.py` | `Desk`       | the war-guard desk | The system: the pricing above, with `SlackFeePlanner` fees |

## Run it

From the repository root:

```sh
uv run strategies/max_margin/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/max_margin/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `max-margin`. Its pricing line ends with how many quotes went above ceiling's
old maximum of 1.39 x the list price.

## The idea

Ceiling pricing never quotes above 1.39 x the list price, lifted only for dealer trust and the outage. Its world
multiplier starts at that maximum, and the lane and dealer offsets add on top of the multiplier. So once the
multiplier is at the top, a dealer who would pay more never gets a higher price, and a world whose competitor sits at
1.54 x the list price, as level 8 allows, is quoted as if it sat at 1.39. It also aims to win half of its quotes,
while drivers, not dealers, are what a level-8 week runs short of.

What the saved weeks say (`out/spread.sqlite`, `analysis.oracle`):

- On `spread-1`, ceiling made €9,831. The oracle puts about €11,400 of revenue between the prices of the orders it won
  and what those dealers would have paid, and €4,591 of fees above the cheapest comparable gigs.
- Every system played so far wins at 1.33 to 1.40 x the list price on average. None has priced higher across the
  board, so the saved weeks cannot show what that wins; the bench below does.
- For dealers with 15 or more orders on time, half of the quotes at 1.6 to 1.7 x the list price won, and a third of
  those at 2.0. Some of that is selection: those prices were sent where a system lifted them, for trust or the outage.

## The strategy

1. **A far higher maximum.** The price may climb to `max_markup` = 1.0 over the list price, 2.0 x, before the trust
   and outage lift. The world multiplier starts at `start` = 1.42, just above ceiling's old maximum.
2. **Fewer wins, each dearer.** The price learns to win `target_win` = 40% of the quotes instead of half. Each
   outcome moves the world multiplier by 3% in logs, as in ceiling, and each pickup, delivery and dealer offset by
   `key_step` = 2% (ceiling: 1.5%), within `key_limit` = ±50% (ceiling: ±25%), so a dealer who pays more is charged
   more within the week.
3. **No thin orders.** No quote goes under the driver cost x (1 + `risk_premium`) = 1.25 (ceiling: 1.10). A car
   whose driver costs more than that leaves at the competitor's price.
4. **Admission's price.** Admission takes a request when its driver cost x 1.25 fits under the learned price x (1 +
   `headroom`) = 1.2, lifted for trust and the outage, never above the maximum. Counting on the maximum, it would
   take every car whose driver costs less than 1.6 x its list price.
5. **The rest.** The fees of `strategies/slack_fees` (a car with a day to wait keeps its early fee until the pickup
   day), the price war and the outage of `strategies/war_guard`, and the timed return legs of ceiling.

## Offline replay

`analysis.replay`'s quote replay with this desk on the three `ceiling` weeks of the bench in #188 (`spread-1` to
`spread-3`). A saved week knows the answer to a quote only at or below the price it sent, so the replay cannot price
this idea: 917 quotes have no known answer (ceiling's own: 611), and the learned world multiplier drifts down to 1.24
to 1.38 on the answers it does know. It quotes 87 to 405 requests a week above the old maximum, and admission takes
60.3% of the requests against 66.6% for ceiling, because no quote goes under the driver cost x 1.25.

## Bench

To be played: the online rules ask for the user's approval first.
