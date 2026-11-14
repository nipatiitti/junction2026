# A price ladder per dealer with a streak-scaled step

The dealer ladder of [`../dealer_ladder/`](../dealer_ladder/README.md) with the step of
[`../streak_ladder/`](../streak_ladder/README.md): one ladder position **and one run of consecutive wins and losses for
each dealer**, so a dealer's price moves further after a run against it. Everything else is the price-ladder system:
the same shadow admission (`ShadowAdmission`, reused from `strategies/price_ladder`), the same price war, outage and
dealer trust, and the same desk loop. Issue #202.

| File          | What it holds                                                                    |
| ------------- | -------------------------------------------------------------------------------- |
| `dispatch.py` | A copy of the dealer-ladder `dispatch.py` that quotes with `DealerStreakPricing` |
| `pricing.py`  | `DealerStreakPricing`: the dealer ladder whose step scales with the dealer's run |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/dealer_streak/dispatch.py --level 8 --seed spread-1                                  # a practice week
uv run python -m strategies.bench strategies/dealer_streak/dispatch.py strategies/dealer_ladder/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`record.py`), with the policy `dealer-streak` instead of `dispatch`, so
they form their own group in `out/spread.sqlite` and `summary.json`.

## The dealer's streak ladder

Like the dealer ladder, each dealer has its own position on the list price, inside `[floor, ceiling]` (1.0 to 1.5 ×
list by default) and starting at the top of its range; a dealer we have not quoted yet starts at the top. Only the
quoting dealer's ladder moves, and the price war, outage and dealer trust are the dealer ladder's, detected on the
world ladder that still moves on every outcome.

The change is the size of the step, and it is not the same up and down. The dealer ladder moves a dealer's position by
a fixed 1% up and 3% down. Here the step is scaled by that dealer's own run of the same outcome, and by a share that
differs by outcome:

- `streak` counts the dealer's consecutive wins (positive) or consecutive losses (negative), and resets to `±1` for
  that dealer when the direction changes;
- a win raises the dealer's price by `clamp(streak, ±streak_cap) × log(1 + win_rate)`: the first win 0.9%, the second
  in a row 1.8%, and a run of five or more 4.5% a step;
- a loss lowers it by `clamp(streak, ±streak_cap) × log(1 − loss_rate)`: the first loss 2%, the second in a row 4%,
  and a run of five or more 10% a step, so a loss moves the price further than a win of the same run;
- a run is capped at `streak_cap` (5), so one long run cannot walk a dealer across its whole range in a single step.

`summary()` prints how many dealers the week quoted, the range of their positions, how many sat at the floor or the top,
and the longest runs of wins and losses.

| Variable     | File         | Default | What it does                                              |
| ------------ | ------------ | ------- | --------------------------------------------------------- |
| `win_rate`   | `pricing.py` | 0.009   | Share per consecutive win; the dealer's run multiplies it |
| `loss_rate`  | `pricing.py` | 0.02    | Share per consecutive loss; a loss moves more than a win  |
| `streak_cap` | `pricing.py` | 5       | A dealer's run stops growing the step past this many      |
| `floor`      | `pricing.py` | 1.0     | The lowest multiple of the list price a dealer quotes     |
| `ceiling`    | `pricing.py` | 1.5     | The highest                                               |
| `start`      | `pricing.py` | 1.5     | Where a dealer's ladder starts, at the top of its range   |

## Bench

Not run yet: the bench plays online, which needs the user's approval. Run it against
`strategies/dealer_ladder/dispatch.py`, `strategies/streak_ladder/dispatch.py` and `strategies/price_ladder/dispatch.py`
on the same seeds, and compare each week's margin and on-time share.
