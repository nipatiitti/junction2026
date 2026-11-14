# Streak-scaled ladder pricing

The price ladder of [`../price_ladder/`](../price_ladder/README.md) with a step that grows with the run of consecutive
wins and losses, and that lowers the price further on a loss than it raises it on a win. Everything else is the
price-ladder system: the same admission (`ShadowAdmission`, reused from `strategies/price_ladder`), the same price war,
outage and dealer trust, and the same desk loop. Issue #177, made asymmetric in #189.

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

The difference is the size of the step, and it is not the same up and down. The price ladder moves by a fixed share
every time, so it reacts at the same speed whether it is one quote out of step or ten. Here the step is scaled by the
current run of the same outcome, and by a share that differs by outcome:

- `streak` counts consecutive wins (positive) or consecutive losses (negative), and resets to `±1` when the direction
  changes;
- a win raises the price by `clamp(streak, ±streak_cap) × log(1 + win_rate)`: the first win moves it 0.9%, the second
  in a row 1.8%, and a run of five or more 4.5% a step;
- a loss lowers it by `clamp(streak, ±streak_cap) × log(1 − loss_rate)`: the first loss 2%, the second in a row 4%,
  and a run of five or more 10% a step, so a loss always moves the price further than a win of the same run;
- a run is capped at `streak_cap` (5), so one long run cannot walk the price across its whole range in a single step.

The price war, the outage and dealer trust are unchanged. `summary()` prints where the ladder ended the week, how often
it sat at either end of its range, and the longest runs of wins and losses.

Because a loss moves the price further than a win, the ladder settles lower than the symmetric one: the wins balance
the losses at `loss_rate / (win_rate + loss_rate)`, about **69% wins** with the defaults (the price ladder's fixed 1%
up, 3% down settles near 75%). So this one quotes a little lower and wins a few more quotes than the symmetric streak
ladder, and it finds the market faster after a sudden change, because a change shows up as a run of the same outcome.
Tune `win_rate` and `loss_rate` up for a coarser, faster ladder and down for a finer one.

| Variable     | File         | Default | What it does                                               |
| ------------ | ------------ | ------- | ---------------------------------------------------------- |
| `win_rate`   | `pricing.py` | 0.009   | Share per consecutive win; the run multiplies it           |
| `loss_rate`  | `pricing.py` | 0.02    | Share per consecutive loss; a loss moves more than a win   |
| `streak_cap` | `pricing.py` | 5       | A run stops growing the step past this many wins or losses |
| `floor`      | `pricing.py` | 1.0     | The lowest multiple of the list price the ladder quotes    |
| `ceiling`    | `pricing.py` | 1.5     | The highest                                                |
| `start`      | `pricing.py` | 1.5     | Where the ladder starts, at the top of its range           |

`win_step` and `loss_step` of the price ladder are inherited but unused: the streak shares replace them.
