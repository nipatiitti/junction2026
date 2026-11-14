# All in 75

A dispatch system built on [`strategies/all_in`](../all_in/README.md): the all-in system whose prices aim to win 75%
of its quotes, not 45%. Issue #296. All-in and the systems it builds on stay as they are.

| File          | Class            | Builds on       | What it decides                                       |
| ------------- | ---------------- | --------------- | ----------------------------------------------------- |
| `pricing.py`  | `AllIn75Pricing` | `PriorPricing`  | The price of a quote, aiming at 75% of the quotes won |
| `dispatch.py` | `Desk`           | the all-in desk | The system: the all-in desk with the pricing above    |

`AllIn75Pricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `PriorPricing`, with
the constructor `(roster, world_map, level=8, params=None, priors=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/all_in_75/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/all_in_75/dispatch.py strategies/all_in/dispatch.py --jobs 2
```

Its weeks are saved with the policy `all-in-75`.

## Why

All-in wins about 320 orders in its mean week at level 8, for €12,268 over `spread-1` to `spread-22`
([`strategies/all_in/README.md`](../all_in/README.md)). Other teams' level 8 weeks win 400 to 480 orders at a similar
margin per order, so most of the gap is the number of quotes that win, not the profit on each.

All-in prices to win about 45% of its quotes: the learned price settles where `target_win` of its quotes win, and its
maximum where `cap_win` of the quotes at the maximum win. On the 22-week base, the probe `q-high50`, which aimed at
50% and 55%, won about 17 more orders a week for about the same margin: the extra orders paid for the lower price.
This system takes that further, to about 75% of the quotes won.

## The strategy

Every other decision is the all-in system's: the same `AllInAdmission` (the fastest option that still pays, and the
flu guard), the same `AllInPlanner` fees, the same lane priors and the same bundle fees. Two variables of the price
change, and they are the only ones:

| Variable     | Default | What it does                                                                  |
| ------------ | ------- | ----------------------------------------------------------------------------- |
| `target_win` | 0.75    | The learned price settles where this share of its quotes win (0.45 in all-in) |
| `cap_win`    | 0.80    | ... and the maximum where this share of the quotes at it win (0.50 in all-in) |

All-in, [`strategies/headroom`](../headroom/README.md) and the probes in its README keep a five-point gap between the
two, so they do here. Under a maximum that is above the learned price, `target_win` is what mostly sets the price.

A lower price wins more cars for less each, so this system should win more orders at a lower margin per order. The
driver cost floor of the pricing (the cost times 1.10) still holds: no quote goes below what its cars cost us.

## Six-week bench

Level 8, on 2026-11-14, in one `strategies.bench` run with `all_in_65` on `tour-r1-ff2bb5ca`, `tour-r1-d0cceb91`,
`tour-r2-8e605453`, `tour-r2-cb24a8ee`, `tour-r2-32a6c4eb` and `tour-r2-3dcdedfe`. Every week is ranked, none has an
undelivered order, and the weeks are saved under `data/scrape/runs/L8/` with the policies `all-in-75` and `all-in-65`.

| Seed               | Margin         |    Orders |   On time |
| ------------------ | -------------- | --------: | --------: |
| `tour-r1-ff2bb5ca` | €9,327.61      |       372 |     96.2% |
| `tour-r1-d0cceb91` | €11,448.52     |       448 |     98.0% |
| `tour-r2-8e605453` | €12,411.97     |       422 |     96.9% |
| `tour-r2-cb24a8ee` | €16,319.46     |       480 |     98.1% |
| `tour-r2-32a6c4eb` | €11,398.22     |       401 |     99.0% |
| `tour-r2-3dcdedfe` | €5,031.83      |       382 |     92.9% |
| **Total**          | **€65,937.61** | **2,505** | **97.0%** |

This system won 202 more orders than `all_in_65` in the same run: 417.5 against 383.8 a week, with at least 400 orders
on four seeds against two. It made €764.05 less in total, but more on four of the six seeds: the higher win target
buys 202 additional orders for €3.78 of total margin forgone per additional order. Six weeks are not enough to put this
system ahead with confidence, especially as one seed has it €3,013 behind.
