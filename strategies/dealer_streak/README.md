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

Two practice weeks, level 8 (`spread-1`, `spread-2`), against the dealer ladder, the streak ladder, the shared price
ladder and the root system:

| System          | spread-1  | spread-2  | Total      | Orders | On time |
| --------------- | --------- | --------- | ---------- | ------ | ------- |
| `dealer_streak` | €7,692.75 | €4,537.73 | €12,230.48 | 665    | 97.7%   |
| `dealer_ladder` | €6,339.07 | €4,563.94 | €10,903.01 | 697    | 97.8%   |
| `streak_ladder` | €7,381.12 | €5,465.42 | €12,846.54 | 754    | 97.6%   |
| `price_ladder`  | €6,200.04 | €4,512.08 | €10,712.12 | 816    | 97.9%   |
| `dispatch.py`   | €8,063.40 | €6,155.98 | €14,219.38 | 722    | 98.6%   |

The per-dealer streak step beats both of the ladders it is built from: +€1,327 over the dealer ladder and +€1,518 over
the shared price ladder, and it wins `spread-1` outright among the ladder family (€7,692.75, above the streak ladder's
€7,381.12). Against the shared streak ladder it loses €616 in total, on `spread-2` alone, because the per-dealer state
splits the market: it wins fewer orders (665 against 754) at a higher price. All three keyed and streak ladders sit
below the root `dispatch.py`. Two seeds is thin, so read the order as a guide.
