# Streak-scaled ladder pricing

The price ladder of [`../price_ladder/`](../price_ladder/README.md) with a step that grows with the run of consecutive
wins and losses. Everything else is the price-ladder system: the same admission (`ShadowAdmission`, reused from
`strategies/price_ladder`), the same price war, outage and dealer trust, and the same desk loop. Issue #177.

| File          | What it holds                                                                      |
| ------------- | ---------------------------------------------------------------------------------- |
| `dispatch.py` | A copy of the price-ladder `dispatch.py` that quotes with `StreakLadderPricing`    |
| `pricing.py`  | `StreakLadderPricing`: the price ladder whose step scales with the run of outcomes |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/streak_ladder/dispatch.py --level 8 --seed spread-1                              # a practice week
uv run python -m strategies.bench strategies/streak_ladder/dispatch.py strategies/price_ladder/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`record.py`), with the policy `streak-ladder` instead of `dispatch`, so
they form their own group in `out/spread.sqlite` and `summary.json`.

## The step

Like the price ladder, one position on the list price for the whole week, inside `[floor, ceiling]` (1.0 to 1.5 × list
by default) and starting at the top of its range. A won quote raises it and a lost quote lowers it, in logs so the
price moves by a share of itself.

The difference is the size of the step. The price ladder moves by a fixed share every time, so it reacts at the same
speed whether it is one quote out of step or ten. Here the step is scaled by the current run of the same outcome:

- `streak` counts consecutive wins (positive) or consecutive losses (negative), and resets to `±1` when the direction
  changes;
- the step is `clamp(streak, -streak_cap, streak_cap) × streak_step`, so the first win moves the price 2%, the second
  in a row 4%, and a run of five or more 10% a step, and a loss lowers it the same way;
- a run is capped at `streak_cap` (5), so one long run cannot walk the price across its whole range in a single step.

The price war, the outage and dealer trust are unchanged. `summary()` prints where the ladder ended the week, how often
it sat at either end of its range, and the longest runs of wins and losses.

Because the step is symmetric, the ladder settles where the wins balance the losses, near **50% wins**; the price
ladder's unequal steps (1% up, 3% down) settle near 75%. So this one quotes higher and wins fewer quotes than the price
ladder, and it finds the market faster after a sudden change, because a change shows up as a run of the same outcome.
Tune `streak_step` up for a coarser, faster ladder and down for a finer one.

| Variable      | File         | Default | What it does                                               |
| ------------- | ------------ | ------- | ---------------------------------------------------------- |
| `streak_step` | `pricing.py` | 0.02    | Log step per consecutive outcome; the run multiplies it    |
| `streak_cap`  | `pricing.py` | 5       | A run stops growing the step past this many wins or losses |
| `floor`       | `pricing.py` | 1.0     | The lowest multiple of the list price the ladder quotes    |
| `ceiling`     | `pricing.py` | 1.5     | The highest                                                |
| `start`       | `pricing.py` | 1.5     | Where the ladder starts, at the top of its range           |

`win_step` and `loss_step` of the price ladder are inherited but unused: the streak step replaces them.
