# All in 65

A dispatch system built on [`strategies/all_in`](../all_in/README.md): the all-in system whose prices aim to win 65%
of its quotes, not 45%. Issue #296. All-in and the systems it builds on stay as they are. It is
[`strategies/all_in_75`](../all_in_75/README.md) with the win shares five points lower.

| File          | Class            | Builds on       | What it decides                                       |
| ------------- | ---------------- | --------------- | ----------------------------------------------------- |
| `pricing.py`  | `AllIn65Pricing` | `PriorPricing`  | The price of a quote, aiming at 65% of the quotes won |
| `dispatch.py` | `Desk`           | the all-in desk | The system: the all-in desk with the pricing above    |

`AllIn65Pricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `PriorPricing`, with
the constructor `(roster, world_map, level=8, params=None, priors=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/all_in_65/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/all_in_65/dispatch.py strategies/all_in/dispatch.py --jobs 2
```

Its weeks are saved with the policy `all-in-65`.

## Why

All-in wins about 320 orders in its mean week at level 8, for €12,268 over `spread-1` to `spread-22`
([`strategies/all_in/README.md`](../all_in/README.md)). Other teams' level 8 weeks win 400 to 480 orders at a similar
margin per order, so most of the gap is the number of quotes that win, not the profit on each.

All-in prices to win about 45% of its quotes: the learned price settles where `target_win` of its quotes win, and its
maximum where `cap_win` of the quotes at the maximum win. On the 22-week base, the probe `q-high50`, which aimed at
50% and 55%, won about 17 more orders a week for about the same margin: the extra orders paid for the lower price.
This system aims at about 65% of the quotes won, the smaller of the two steps toward the volume of the leading weeks.

## The strategy

Every other decision is the all-in system's: the same `AllInAdmission` (the fastest option that still pays, and the
flu guard), the same `AllInPlanner` fees, the same lane priors and the same bundle fees. Two variables of the price
change, and they are the only ones:

| Variable     | Default | What it does                                                                  |
| ------------ | ------- | ----------------------------------------------------------------------------- |
| `target_win` | 0.65    | The learned price settles where this share of its quotes win (0.45 in all-in) |
| `cap_win`    | 0.70    | ... and the maximum where this share of the quotes at it win (0.50 in all-in) |

All-in, [`strategies/headroom`](../headroom/README.md) and the probes in its README keep a five-point gap between the
two, so they do here. Under a maximum that is above the learned price, `target_win` is what mostly sets the price.

A lower price wins more cars for less each, so this system should win more orders at a lower margin per order. The
driver cost floor of the pricing (the cost times 1.10) still holds: no quote goes below what its cars cost us.

## Not measured yet

No online week has been played for this system. It exists to measure whether the extra orders at 65% pay for the lower
price, so play it against `strategies/all_in` on the same seeds, and read a difference of a few hundred euros a week as
chance ([`strategies/all_in/README.md`](../all_in/README.md) gives the standard errors of the 22-week comparison).
