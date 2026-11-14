# Soft top

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `Desk` is a subclass of the headroom
desk whose fee schedules end at twice the lane fee, not 2.5 times. Issue #200. The systems it builds on stay as they
are.

| File          | Class            | Builds on         | What it decides                                             |
| ------------- | ---------------- | ----------------- | ----------------------------------------------------------- |
| `fees.py`     | `SoftTopPlanner` | `LaneFeePlanner`  | The dawn fee schedule, with a top fee of twice the lane fee |
| `dispatch.py` | `Desk`           | the headroom desk | The system: the headroom desk with the fee planner above    |

`SoftTopPlanner` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `LaneFeePlanner`,
with the constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/soft_top/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/soft_top/dispatch.py strategies/headroom/dispatch.py --jobs 2
```

Its weeks are saved with the policy `soft-top`.

## What the saved weeks show

The top fee is what a gig pays when nothing lower found a driver: at the end of its dawn or sprint ladder, after a
drop with little time left, or after its deadline warning. In `strategies/fees` and `strategies/dawn_fees` it is 2.5
times the typical fee, under a ceiling of twice the order's price.

- **Few gigs reach it, and they cost a lot.** In the three headroom weeks of the bench, 9, 11 and 12 one-order gigs
  were booked at 1.75 times their typical fee or more. They cost €530, €1,808 and €2,209: 2.2 to 2.6 times their
  typical fees, and more than the price of most of their orders.
- **A late car costs less.** A car late by up to 2 hours gives 10% of its price back, and one late by up to 24 hours
  25% (`RULES.md`). Those weeks delivered 97.7% to 99.2% of their orders on time, against a minimum of 90%.
- **The team's fee bench said the same.** In `strategies/fees/README.md`, the version with a top of twice the
  typical fee (`v9`) made €36,248 on `spread-1` to `spread-5` against €31,078 for the one with 2.5 times (`v16`),
  with 96.7% on time against 97.9%. `v16` was chosen for its on-time share (issue #109).

## The strategy

`SoftTopPlanner` is the lane fee planner with `top` at 2.0. Every schedule of the dawn fee planner keeps its shape and
its timing: the fee held through the day of the post, the dawn ladder and the sprint ladder climb to the lower top in
even ratios, so each step is smaller too. The ceiling of twice the order's price and the rule that no step before the
top goes above the price are unchanged.

With the lower top, the gigs booked at 1.75 times their typical fee or more were 6, 8 and 10, and cost €276, €878 and
€1,672. Late orders went from 2 to 4 on `spread-1`, stayed at 5 on `spread-2` and fell from 8 to 5 on `spread-4`.

## The variables

`Params` in `fees.py`, exported as `SoftTopParams`, next to those of `strategies/dawn_fees`.

| Variable | Default | What it does                                                           |
| -------- | ------- | ---------------------------------------------------------------------- |
| `top`    | 2.0     | The top fee over the lane fee, before the ceiling of `strategies/fees` |

## Bench

Level 8, seeds `spread-1`, `spread-2` and `spread-4`, the code of this branch, with
`uv run python -m strategies.bench strategies/<system>/dispatch.py --seeds spread-1,spread-2,spread-4`. Every week is
ranked, and each is saved in `data/scrape/runs/L8/` under its system's policy. `ceiling` is the saved week of
`strategies/ceiling` on the same seed.

| Seed       | `ceiling`      | `headroom`     | `lane_prior`   | `town_open`    | `same_day`     | `soft_top`     |
| ---------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- |
| `spread-1` | €9,831.09      | €12,670.71     | €12,170.85     | €12,137.41     | €12,283.73     | €13,297.12     |
| `spread-2` | €6,673.95      | €9,378.79      | €10,492.81     | €8,320.56      | €9,371.17      | €9,816.59      |
| `spread-4` | €8,147.90      | €13,089.25     | €13,086.78     | €12,604.28     | €13,975.61     | €13,658.73     |
| **Total**  | **€24,652.94** | **€35,138.75** | **€35,750.44** | **€33,062.25** | **€35,630.51** | **€36,772.44** |
| On time    | 97.9%          | 98.2%          | 98.6%          | 97.8%          | 98.4%          | 98.4%          |

All five systems are over €12,000 on `spread-1` and on `spread-4`. No system is on `spread-2`: that world's prices
are low (the price that wins half of a day's quotes is 1.03 to 1.39 times the list price there, against 1.23 to 1.50
on `spread-1`), and `ceiling` makes €6,674 in it.

**One week proves little.** The same seed moves by several hundred euros between two versions with little in common:
a booking a minute earlier changes which driver is free for the next car, and the rest of the week with it.

Against `headroom`, the lower top made €1,634 more over the three weeks, and more on each seed (+€626, +€438, +€570):
the only one of the four additions that is ahead on all three.
