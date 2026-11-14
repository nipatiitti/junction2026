# Combined fees

A dispatch system built on [`strategies/soft_top`](../soft_top/README.md): its `Desk` replaces
`SoftTopPlanner` with `CombinedTopPlanner`, adding the home-return and on-time-slack discounts. Issue #236.
`soft_top`, `adaptive_fees` and `home_return` stay as they are.

| File          | Class                | Builds on                         | What it decides                               |
| ------------- | -------------------- | --------------------------------- | --------------------------------------------- |
| `fees.py`     | `CombinedTopPlanner` | `AdaptiveFees` + `SoftTopPlanner` | The combined multipliers of the typical fee   |
| `dispatch.py` | `Desk`               | the soft-top desk                 | The system: keeps soft top, swaps the planner |

## Run it

From the repository root:

```sh
uv run strategies/combined_fees/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/combined_fees/dispatch.py strategies/soft_top/dispatch.py --jobs 2
```

Its weeks are saved with the policy `combined-fees`.

## What is composed

- **`soft_top`'s whole system**: lane-fitted typical fees, lead-cost admission, dawn fee scheduling and
  a top fee of 2.0 times the lane fee. Its base `headroom` already contains the cost-by-lead idea from
  `hazard_admission`, so that experiment is not added twice. Dawn fees already model when drivers wait,
  so `slack_fees` is not added separately either.
- **`adaptive_fees`**: if the running on-time share, smoothed with a prior of 10 orders, is at least **95%**,
  the typical fee gets a **0.85 multiplier**. Below 95% that discount disappears. The planner learns from
  every delivery and deadline, as `AdaptiveFees` does.
- **`home_return`**: the delivery town's share of driver homes gives another discount, reaching **0.85**
  when at least **5%** of drivers live there.

The multipliers apply independently, so if both discounts fire the typical fee is `0.85 * 0.85 = 0.7225` of the
lane fee at the full homecoming discount. It is bounded by 1 before the soft-top schedule runs.

Both discount the typical fee used by the planner, not the dealer price. Admission and pricing remain soft
top's. Bundles keep the root bundler's fee planning, as in the two smaller experiments.

## What this is testing

Only whether the two discounts add anything over `soft_top`, whose margin and on-time share were already the
best in the first spread-1 comparison. Relevant output is the `Dawn fees` counts and the
`Adaptive fees: N schedules discounted` line; the proper comparison is `combined-fees` against `soft-top`
on the same seeds.

`low_opening` was deliberately left out: it had failed its own earlier test despite winning a single-seed
bench, and its change belongs to the first step of a schedule, which this combination otherwise preserves.

No online weeks were played to construct this system.
