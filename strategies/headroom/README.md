# Headroom pricing

A dispatch system built on [`strategies/lead_cost`](../lead_cost/README.md): its `Desk` is a subclass of the
lead-cost desk whose price maximum moves with the wins and losses at it. Issue #200. The systems it builds on stay
as they are.

| File          | Class             | Builds on          | What it decides                                        |
| ------------- | ----------------- | ------------------ | ------------------------------------------------------ |
| `pricing.py`  | `HeadroomPricing` | `CeilingPricing`   | The price of a quote, under a maximum that moves       |
| `dispatch.py` | `Desk`            | the lead-cost desk | The system: the lead-cost desk with the pricing above  |

`HeadroomPricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `CeilingPricing`,
with the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/headroom/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/headroom/dispatch.py strategies/lead_cost/dispatch.py --jobs 2
```

Its weeks are saved with the policy `headroom`. The `Headroom` line at the end of a week gives where the maximum
ended, and the wins and losses at it.

## What the saved weeks show

Ceiling pricing quotes at most 1.39 times the list price, lifted by dealer trust and the outage. At level 8 the
competitor's price level is from 26% to 54% above the list price, new in every world, so one number cannot fit.

- On `spread-1`, 188 of the 677 quotes of the saved `ceiling` week were at the maximum, and the quotes at 1.65 to
  1.75 times the list price (the maximum with a trusted dealer's lift) won 63% to 70% of the time: the dealers would
  have paid more.
- The root pricing, which has no maximum and aims at half of its quotes won, earned €2,741 less than ceiling on
  `spread-1` to `spread-5`. So a maximum pays, but its height should come from the world.
- Over 198,543 saved quotes, a price 1% higher loses about 1.9 points of win share near 50%
  (`strategies/lane_prior/fit.py`). At that slope, an order whose driver costs two thirds of its price earns most
  when about 60% of such quotes win, not 50%.

## The strategy

1. **The maximum starts at 1.39** times the list price (`max_markup`), as in ceiling pricing, and every price
   starts there.
2. **A win at the maximum raises it, a loss at it lowers it.** After each quote that was priced at the maximum, it
   moves by `cap_step` × (won − `cap_win`), in logs: +0.46% after a win and −0.74% after a loss. It settles where
   62% of the quotes at the maximum win, and stays between 1.20 and 1.62 times the list price.
3. **A win at the maximum counts as a usual win.** In ceiling pricing it moves nothing. Here the learned price may
   follow the maximum up, so the next quote is at the new maximum.
4. **What does not move it.** A quote priced with the outage boost, a quote on the price war's day, and a quote at
   the driver cost floor: each has its own rule in ceiling pricing, and none says where the usual maximum is.

Everything else is ceiling pricing: the learned multiplier with its place and dealer offsets, the floor at the driver
cost plus its risk premium, dealer trust, the outage and the price war.

## The variables

`Params` in `pricing.py`, exported as `HeadroomParams`, next to those of `strategies/ceiling` and
`strategies/pricing`.

| Variable     | Default | What it does                                                        |
| ------------ | ------- | ------------------------------------------------------------------- |
| `max_markup` | 0.39    | Where the maximum starts: the list price × (1 + `max_markup`)       |
| `cap_win`    | 0.62    | The share of the quotes at the maximum that it settles to win       |
| `cap_step`   | 0.012   | The step of the maximum per outcome at it, in logs                  |
| `cap_low`    | 0.20    | The maximum never falls below the list price × (1 + `cap_low`)      |
| `cap_high`   | 0.62    | The maximum never rises above the list price × (1 + `cap_high`)     |
