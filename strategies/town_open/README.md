# Town opening

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `Desk` is a subclass of the
headroom desk whose gigs open at a fee learned for each pickup town. Issue #200. The systems it builds on stay as
they are.

| File          | Class            | Builds on         | What it decides                                             |
| ------------- | ---------------- | ----------------- | ----------------------------------------------------------- |
| `opening.py`  | `TownOpening`    | `Strategy`        | The opening fee of each pickup town, from its bookings      |
| `opening.py`  | `TownFeePlanner` | `LaneFeePlanner`  | The dawn schedule on the lane fee, opened at the town's fee |
| `dispatch.py` | `Desk`           | the headroom desk | The system: tells `TownOpening` each gig it posts           |

Both classes are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the constructor
`(roster, world_map, level=8, params=None)`; `TownOpening` has a frozen `Params`, and the desk feeds it every event.

## Run it

From the repository root:

```sh
uv run strategies/town_open/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/town_open/dispatch.py strategies/headroom/dispatch.py --jobs 2
```

Its weeks are saved with the policy `town-open`. The `Town opening` line at the end of a week counts the gigs that
booked quickly at their opening fee and those that needed a raise, and gives the world's opening fee and the three
cheapest and three dearest towns.

## What the saved weeks show

Every gig opens at 0.9 times its typical fee (`strategies/fees`), or its lane fee (`strategies/lane_fee`). In the 31
saved level 8 weeks with that schedule, 58% of the one-order gigs booked at the opening fee, half of them within 6
minutes: for those cars the cheapest driver would have come for less. For cars ready 8 to 24 hours after the post, 70%
to 76% booked at the opening fee, with a median of 7 to 9 minutes. Level 8 gives each town its own share of the
drivers, new in every world, and the driver list does not say who works, so the right opening fee differs by town and
by world. At level 1, where drivers do not learn our fees, opening at half the typical fee raised the week's margin
from €21 to €6,037 (`strategies/fees`).

## The strategy

1. **One opening fee for the world, and an offset for each pickup town**, both as multiples of the lane fee. Every
   town starts at 0.9.
2. **A quick booking lowers it.** When a driver books a gig at its opening fee within 20 minutes of the post
   (`quick`), the world's fee falls 0.45% and the town's offset 0.9%.
3. **A raise lifts it.** When a gig is booked above its opening fee, or expires without a driver, the world's fee
   rises 1.05% and the town's offset 2.1%. The steps balance where 70% of a town's gigs book quickly
   (`quick_share`).
4. **A slow booking at the opening fee** moves nothing.
5. **Limits.** A town opens between 0.8 and 1.0, and its offset stays within 0.12 of the world's fee. The first
   week, played with a floor of 0.72 and a balance at 60%, paid less per gig (0.86 times the typical fee at the
   opening, against 0.92) but left more gigs waiting, and admission then took fewer cars: the gentler limits keep
   most of the saving without that.

Only a gig of one order that opened at its town's fee teaches: a gig with little time left opens higher
(`strategies/fees`) and says nothing of the town. An accepted direct offer does not say its fee, so it teaches
nothing. The rest of the schedule is the dawn schedule of `strategies/dawn_fees`: the fee after two hours and the
dawn ladder do not move with the opening.

## The variables

`Params` in `opening.py`, exported as `TownParams`.

| Variable      | Default    | What it does                                                        |
| ------------- | ---------- | ------------------------------------------------------------------- |
| `start`       | 0.9        | Where every town opens on Monday                                    |
| `low`, `high` | 0.8, 1.0   | No town opens below or above these                                  |
| `quick`       | 20 minutes | A booking at the opening fee within this of the post is a quick one |
| `quick_share` | 0.7        | The share of quick bookings that the opening settles at             |
| `step`        | 0.015      | The world's step per gig, times (raised − (1 − `quick_share`))      |
| `town_step`   | 0.03       | The same for the town's offset                                      |
| `town_limit`  | 0.12       | A town's offset stays within this of the world's opening            |
| `same`        | 0.05       | A gig that opened within this of its town's fee teaches             |

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

Against `headroom`, the town openings made €2,077 less over the three weeks, less on each seed. The opening fees did
fall, and the gigs that booked at them paid less, but the week did not keep that: this system is the weakest of the
five, and the one to drop first.
