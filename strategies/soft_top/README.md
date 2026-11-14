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

## A series of 22 weeks

`soft_top` on `spread-1` to `spread-22`, level 8, one week each, saved under the policy `soft-top`:

| Seed | Margin | Orders | On time | Ranked |
| ---- | ------ | ------ | ------- | ------ |
| `spread-1` | €13,297.12 | 358 | 98.9% | yes |
| `spread-2` | €9,816.59 | 299 | 97.7% | yes |
| `spread-3` | €5,297.53 | 231 | 98.3% | yes |
| `spread-4` | €13,658.73 | 348 | 98.6% | yes |
| `spread-5` | €7,161.91 | 284 | 93.7% | yes |
| `spread-6` | €8,593.70 | 235 | 98.7% | yes |
| `spread-7` | €10,709.46 | 303 | 98.0% | yes |
| `spread-8` | €13,130.54 | 353 | 98.9% | yes |
| `spread-9` | €14,054.62 | 294 | 98.3% | yes |
| `spread-10` | €11,327.90 | 294 | 98.0% | yes |
| `spread-11` | €9,276.08 | 267 | 97.4% | yes |
| `spread-12` | €12,531.29 | 376 | 93.6% | yes |
| `spread-13` | €9,952.94 | 254 | 98.4% | yes |
| `spread-14` | €9,055.44 | 272 | 98.9% | yes |
| `spread-15` | €9,920.60 | 320 | 96.2% | yes |
| `spread-16` | €15,360.98 | 373 | 95.2% | yes |
| `spread-17` | €13,268.32 | 318 | 99.7% | yes |
| `spread-18` | €11,949.95 | 337 | 95.8% | yes |
| `spread-19` | €14,720.82 | 344 | 96.8% | yes |
| `spread-20` | €13,251.67 | 325 | 96.9% | yes |
| `spread-21` | €10,588.55 | 340 | 88.5% | no |
| `spread-22` | €11,069.83 | 333 | 96.1% | yes |
| **Mean** | **€11,272.48** | 312 | | 21 of 22 |

The mean week makes €11,272. 9 of the 22 weeks are over €12,000, 14 over €10,000, and the weeks run
from €5,298 to €15,361: the world decides more than the system. For comparison, in the level 8 ranking round
"Saturday 09:00" the leading team's five weeks made €10,735 to €20,883, and the organisers' own system €12,225 to
€15,491 in the round before.

The week on `spread-21` is not ranked: 88.5% of its orders were on time. It is the week of the flu on a Friday with
101 orders due; [`strategies/flu_guard`](../flu_guard/README.md) is the answer to it.
