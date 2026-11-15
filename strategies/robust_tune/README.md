# Robust tune

A deliberately reduced-parameter dispatch system built on [`strategies/headroom`](../headroom/README.md). It is a
robustness hypothesis for unseen worlds, not a claim of better performance. **No tuning, online run or online
comparison was performed.** The system should be benched against headroom on many seeds before drawing any conclusion.

| File          | Class           | Builds on         | What it decides                                   |
| ------------- | --------------- | ----------------- | ------------------------------------------------- |
| `pricing.py`  | `RobustPricing` | `HeadroomPricing` | One world price estimate under one moving maximum |
| `dispatch.py` | `Desk`          | the headroom desk | The headroom system with only its pricing changed |

## Run it

From the repository root:

```sh
uv run strategies/robust_tune/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `robust-tune`.

## What changes

1. **Pickup, delivery and dealer offsets are switched off by default** (`use_offsets=False`). Headroom learns three
   offsets for every request in addition to its world multiplier. Each is updated only by the subset of outcomes for
   that place or dealer, so these effects are weakly identified within one week. Robust pricing neither learns nor
   applies them: each request starts from the same learned world multiplier.
2. **The learned price and maximum stay on that world estimate.** With no request offsets, a lane cannot move its
   learned multiplier or effective maximum away from the world's measured level. Headroom's maximum still moves from
   wins and losses at it, within its usual bounds.
3. **Old outcomes fade more slowly** (`fade=0.5`). Each world-estimate update and each move of the maximum is half
   headroom's usual step. This roughly doubles the outcome window and limits how far one unusual run or day can move
   the price.
4. **Trust and outage lifts stay unchanged.** Dealer trust at level 8 and the regional outage premium are given by the
   challenge rules rather than fitted per-lane effects. They still lift both the quote and its maximum.

The driver-cost floor, risk premium, price-war handling and all other headroom pricing behaviour remain unchanged.
So do the desk's [`LaneFee`](../lane_fee/README.md), [`LaneCostAdmission`](../lead_cost/README.md) and
[`LaneFeePlanner`](../dawn_fees/README.md): the lane fee, lead-time cost model and dawn fee schedules are reused
without new parameters or fitting.

## Defaults

`RobustParams` in `pricing.py` is frozen and extends `HeadroomParams`.

| Variable      | Default | What it does                                                                 |
| ------------- | ------- | ---------------------------------------------------------------------------- |
| `use_offsets` | `False` | Whether pickup, delivery and dealer offsets are learned and applied          |
| `fade`        | `0.5`   | The share of headroom's usual world-estimate and moving-maximum update steps |

The inherited defaults are unchanged: the maximum starts at 1.39 times list price (`max_markup=0.39`), moves in
0.012 log steps before `fade`, targets 50% wins at the maximum, and stays between 1.20 and 1.62 times list price. The
world estimate targets 45% wins and has a 0.9 list-price floor; the driver-cost risk premium is 10%. Trust remains
enabled. Setting `use_offsets=True` restores headroom's offset learning, still scaled by `fade`.
