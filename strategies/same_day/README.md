# Same-day admission

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `Desk` is a subclass of the headroom
desk whose admission quotes the fastest option that a dealer asks for when it still pays. Issue #200. The systems it
builds on stay as they are.

| File           | Class              | Builds on           | What it decides                                          |
| -------------- | ------------------ | ------------------- | -------------------------------------------------------- |
| `admission.py` | `SameDayAdmission` | `LaneCostAdmission` | Which option to quote, with the faster one counted fully |
| `dispatch.py`  | `Desk`             | the headroom desk   | The system: the headroom desk with the admission above   |

`SameDayAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through
`LaneCostAdmission`, with the constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/same_day/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/same_day/dispatch.py strategies/headroom/dispatch.py --jobs 2
```

Its weeks are saved with the policy `same-day`. Its admission lines count the quotes that went to each option.

## What the saved weeks show

Admission quotes one option. The lead-cost admission picks the one with the most margin, which for a car that is
ready now, on a morning, is `next_day`: collected today it costs far more.

- **A dealer wants the fastest option.** In the saved weeks that quoted one option, a request that offered both
  `same_day` and `next_day` was won 65% of the time when we quoted `same_day` (7,121 quotes at 1.40 times the list
  price), and 33% of the time when we quoted only `next_day` (7,305 quotes at 1.45 times). In the weeks that quoted
  both at once, the dealer took `same_day` 54% of the time and `next_day` 3%.
- **A car to collect today cost 1.77 to 2.41 times its typical fee** in the saved weeks, but those gigs opened
  near their top fee and were booked within minutes (`strategies/dawn_fees`). On the sprint ladder they open at 1.1.

## The strategy

`SameDayAdmission` is the lane-cost admission with two variables changed:

1. **A slower option counts for half.** When the request has a faster option, an option's margin is multiplied by
   0.5 (`slower_win`) before admission compares the options: it wins about half as often.
2. **A cost for today that the sprint ladder can meet.** The driver cost of a car to collect within 8 hours is 1.6
   times the lane fee, and within 14 hours 1.35 times, instead of 2.40 and 1.77.

A request is still declined when the cost of every option, plus the risk premium, is above the highest price we would
quote.

## The variables

`Params` in `admission.py`, exported as `SameDayParams`, next to those of `strategies/lead_cost`.

| Variable     | Default                    | What it does                                                       |
| ------------ | -------------------------- | ------------------------------------------------------------------ |
| `slower_win` | 0.5                        | The weight of an option's margin when the request has a faster one |
| `cost`       | 1.60 and 1.35 in rows 1, 2 | The driver cost over the lane fee, by lead time                    |

The other rows of `cost` are those of `strategies/lead_cost`. With the rows measured under dawn fees instead, the
week on `spread-1` made €11,722.02 (policy `t-same`): the cheaper rows for cars with a night to wait pull quotes back
to the slower option. With a bolder cost for today, 1.4 and 1.2, the three weeks made €2,878 less in total (policy
`z-same-bold`), with 96.2% on time on `spread-1`: same-day cars are the ones that arrive late.

## Bench

Level 8, seeds `spread-1`, `spread-2` and `spread-4`, with
`uv run python -m strategies.bench strategies/<system>/dispatch.py --seeds spread-1,spread-2,spread-4`. Every week is
ranked, and each is saved in `data/scrape/runs/L8/` under its system's policy. `ceiling` is the saved week of
`strategies/ceiling` on the same seed.

| Seed       | `ceiling`      | `headroom`     | `lane_prior`   | `same_day`     | `soft_top`     |
| ---------- | -------------- | -------------- | -------------- | -------------- | -------------- |
| `spread-1` | €9,831.09      | €12,670.71     | €12,170.85     | €12,283.73     | €13,297.12     |
| `spread-2` | €6,673.95      | €9,378.79      | €10,492.81     | €9,371.17      | €9,816.59      |
| `spread-4` | €8,147.90      | €13,089.25     | €13,086.78     | €13,975.61     | €13,658.73     |
| **Total**  | **€24,652.94** | **€35,138.75** | **€35,750.44** | **€35,630.51** | **€36,772.44** |
| On time    | 97.9%          | 98.2%          | 98.6%          | 98.4%          | 98.4%          |

**Three weeks prove little.** The same seed moves by several hundred euros between two versions with little in common:
a booking a minute earlier changes which driver is free for the next car, and the rest of the week with it.
[`strategies/all_in/README.md`](../all_in/README.md) compares the systems over 22 weeks, where a difference of €200 a
week is still within what chance gives.

Against `headroom`, same-day quoting made €492 more over the three weeks: less on `spread-1` (−€387), the same on
`spread-2` (−€8), more on `spread-4` (+€886), with 98.4% of the orders on time against 98.2%.
