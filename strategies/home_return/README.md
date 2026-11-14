# Home-return fees

A dispatch system built on the root [`dispatch.py`](../../dispatch.py): its `Desk` replaces `FeePlanner` with
`HomeReturnFees`, which discounts a gig whose delivery is in a town where many drivers live. Issue #229. The
root dispatcher and `strategies/fees` stay as they are.

| File          | Class            | Builds on       | What it decides                           |
| ------------- | ---------------- | --------------- | ----------------------------------------- |
| `fees.py`     | `HomeReturnFees` | `FeePlanner`    | The typical fee used for a gig's schedule |
| `dispatch.py` | `Desk`           | the root `Desk` | The system: swaps in the planner above    |

## Run it

From the repository root:

```sh
uv run strategies/home_return/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/home_return/dispatch.py dispatch.py --jobs 2
```

Its weeks are saved with the policy `home-return`.

## The idea

The driver's cost includes getting home after the delivery. At a delivery town with many drivers, that last
trip is short for someone, so the gig should be bookable for less. The discount is proportional to that
town's share of the week's driver homes, reaching **15%** when at least **5% of drivers live there**:

```text
fee multiplier = 1 - 0.15 * min(1, homes at the last delivery / total homes / 0.05)
```

Only the `typical` value passed into the fee schedule changes; the order's price, admission cost, ceiling and
timing are otherwise the root fee planner's. The schedule's opening, raises and top therefore all move down
together. Bundled gigs keep the root bundler's fee planning; this scenario discounts one-order gigs.

Useful question to measure: whether this lowers the paid fee without leaving more late cars in the towns
where it is applied. Compare `paid fee / typical fee` and on-time share with the same seeds of the root system.

This is a deliberately simple roster-based hypothesis; a more precise version would use the drivers actually
available near the delivery at the expected arrival minute.
