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

## Six-week bench

Level 8, on 2026-11-14, in one `strategies.bench` run with `all_in_75` on `tour-r1-ff2bb5ca`, `tour-r1-d0cceb91`,
`tour-r2-8e605453`, `tour-r2-cb24a8ee`, `tour-r2-32a6c4eb` and `tour-r2-3dcdedfe`. Every week is ranked, none has an
undelivered order, and the weeks are saved under `data/scrape/runs/L8/` with the policies `all-in-65` and `all-in-75`.

| Seed               | Margin         |    Orders |   On time |
| ------------------ | -------------- | --------: | --------: |
| `tour-r1-ff2bb5ca` | €12,340.71     |       346 |     98.6% |
| `tour-r1-d0cceb91` | €11,426.56     |       405 |     98.8% |
| `tour-r2-8e605453` | €11,345.03     |       389 |     96.7% |
| `tour-r2-cb24a8ee` | €15,561.94     |       448 |     98.7% |
| `tour-r2-32a6c4eb` | €9,660.22      |       347 |     99.1% |
| `tour-r2-3dcdedfe` | €6,367.20      |       368 |     91.8% |
| **Total**          | **€66,701.66** | **2,303** | **97.3%** |

`all_in_75` won 2,505 orders in the same run, 202 more than this system's 2,303: 417.5 against 383.8 a week. It made
€65,937.61, €764.05 less in total, but more on four of the six seeds. `all_in_65` therefore makes more per order (€28.96
against €26.32), while `all_in_75` reaches the 400-to-480-order range of the leading weeks more often. Six weeks are
not enough to put one ahead of the other with confidence; other changes to a week move it by more than the difference.
