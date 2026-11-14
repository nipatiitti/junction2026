# Dawn fees

A fee schedule that follows the drivers' day, for the systems of [`strategies/headroom`](../headroom/README.md) and up.
Issue #200. `strategies/fees` and the root system stay as they are.

| File      | Class            | Builds on    | What it decides                                                   |
| --------- | ---------------- | ------------ | ----------------------------------------------------------------- |
| `fees.py` | `DawnFeePlanner` | `FeePlanner` | The fee schedule of a gig: held low, then a ladder from dawn      |
| `fees.py` | `dawn_plan`      |              | The schedule of a gig with a morning to wait for, a pure function |
| `fees.py` | `sprint_plan`    |              | The schedule of a gig with none: a short ladder to the top fee    |

`DawnFeePlanner` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `FeePlanner`, with
the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`. A desk uses it in place of
`FeePlanner`: `self.fees = DawnFeePlanner(roster, world_map, level)`. `LaneFeePlanner` of `strategies/lane_fee` is this
planner on the lane fee, and every system from `headroom` up plays with it.

## What the saved weeks show

The 31 saved level 8 weeks that used the schedule of `strategies/fees` (policies `ceiling`, `scarcity-ceiling`,
`scarcity-cost`, `delivery-urgency`, `price-ladder`) hold 10,664 bookings of one-order gigs:

- **The morning takes what the app shows.** Of the gigs still open at 06:00 on the morning after their post, 74%
  were booked between 06:00 and 08:00, at 1.38 times the typical fee and at 1.06 times alike (hourly booking rate
  0.43 and 0.48). Drivers plan their day then. But that schedule moves a top fee due at night to 22:00 the evening
  before, so the morning often pays 2.5 times the typical fee: the 1,844 bookings made on a later day than the post
  cost 1.48 to 1.64 times the typical fee.
- **The early raises come before the drivers decide.** A gig posted a day before its pickup day and booked on the
  day of the post cost 0.99 times the typical fee (4,569 bookings). The schedule still raises every gig to 1.06 after
  an hour and to 1.38 after three, when most drivers who will take a car tomorrow have not looked yet. Cars with 60
  hours or more to their last pickup booked at the opening fee only 39% of the time.

## The schedule

`dawn_plan` in `fees.py`, a pure function of the gig's facts and the time. A gig has a *last dawn* when 06:00 comes
after the post and at least 3 hours (`reach`) before its `lastPickupAt`.

1. **A gig with a last dawn** opens at 0.9 times the typical fee (`open`) and rises once, to 1.0 (`hold`), 2 hours
   after the post (`patience`), unless that falls after 22:00 or on another day.
2. **It holds that fee** through every evening and night until its last dawn.
3. **From its last dawn it climbs**: 1.15 at 06:00 (`dawn`), then one step an hour (`step`) in even ratios, to the
   top fee a travel margin (6 to 8 hours, as in `strategies/fees`) before `lastPickupAt`, and an hour after dawn at
   the earliest.
4. **A tight morning.** When the top is due before the last dawn, the gig rises to 1.4 (`tight`) at 20:00 the
   evening before, for the drivers who must set out then, starts its dawn at 1.4 and reaches the top at 07:00.
5. **A gig with no dawn to wait for** climbs a sprint ladder (`sprint_plan`): a car to collect today, or a gig that
   came back after a drop on its last morning. The schedule of `strategies/fees` opens such a gig close to its top
   fee, and a driver takes it within minutes, so it never learns what a lower fee would have found: in the saved
   weeks those gigs opened at about 2.4 times the typical fee and booked in a median of 3 minutes. The sprint opens
   at 1.1 (`sprint_open`) and climbs to the top in even ratios, one step each 15 minutes (`sprint_step`), by `reach`
   before the last pickup and 2 hours (`sprint`) after the post at the latest.
6. **Every other gig** gets the schedule of `strategies/fees`: a gig with less than `reach` to its last pickup, a
   late car, a gig after its deadline warning, and every gig at level 1.

The top fee, its ceiling of twice the order's price, and the rule that no step before the top goes above the price
are those of `strategies/fees`. After a drop with little time left, the gig steps up from the dropped fee on the same
schedules. Bundles of several orders keep the root desk's schedule.

| Example                                 | `strategies/fees`                                  | Dawn fees                                                         |
| --------------------------------------- | -------------------------------------------------- | ----------------------------------------------------------------- |
| Posted Mon 11:00, last pickup Tue 17:00 | 0.90, 1.06 at 12:00, 1.38 at 14:00, 2.50 Tue 11:00 | 0.90, 1.00 at 13:00, Tue 1.15 at 06:00, 1.34, 1.57, 2.50 at 11:00 |
| Posted Mon 15:00, last pickup Tue 11:00 | 1.10, 1.24, 1.52, 2.50 at Mon 22:00                | 0.90, 1.00 at 17:00, 1.40 at 20:00, 2.50 Tue 07:00                |
| Posted Mon 10:00, last pickup Wed 16:00 | 0.90, 1.06, 1.38 at 13:00, 2.50 Wed 10:00          | 0.90, 1.00 at 12:00, Wed 1.15 at 06:00, 1.40, 2.50 at 10:00       |
| Posted Mon 10:00, last pickup Mon 17:00 | 2.50                                               | 1.10, 1.22 at 10:15, 1.35, 1.50, 1.60 at 11:00, 2.50 at 12:00     |

Fees are multiples of the typical fee, for an order priced at 1.6 times it.

## The variables

`Params` in `fees.py`, exported as `DawnParams`. Each fee is a multiple of the gig's typical fee.

| Variable      | Default | What it does                                                               |
| ------------- | ------- | -------------------------------------------------------------------------- |
| `open`        | 0.9     | The opening fee                                                            |
| `hold`        | 1.0     | The fee after `patience`, held until the last dawn                         |
| `patience`    | 2 hours | How long the opening fee stays                                             |
| `quiet_from`  | 22:00   | No raise on the posting day from this hour                                 |
| `evening_at`  | 20:00   | The evening before the last dawn: the hold fee at the latest, or `tight`   |
| `tight`       | 1.4     | That evening's fee when the top is due before dawn                         |
| `dawn_at`     | 06:00   | When the drivers plan their day                                            |
| `dawn`        | 1.15    | The fee at the last dawn                                                   |
| `reach`       | 3 hours | The time a driver who books at dawn needs to get to the car                |
| `step`        | 1 hour  | How often the ladder from the dawn fee to the top fee rises                |
| `top`         | 2.5     | The top fee, before the ceiling of `strategies/fees` cuts it               |
| `sprint`      | 2 hours | The sprint ladder reaches the top this long after the post; 0 turns it off |
| `sprint_open` | 1.1     | Where the sprint ladder opens                                              |
| `sprint_step` | 15 min  | How often the sprint ladder rises                                          |

## Played

Level 8, seed `spread-1`, each week saved in `data/scrape/runs` under the policy named:

| What was played                                                  | Policy               | Margin     | Orders | On time | Fees over the typical fee |
| ---------------------------------------------------------------- | -------------------- | ---------- | ------ | ------- | ------------------------- |
| `ceiling`, the reference                                         | `ceiling`            | €9,831.09  | 386    | 97.4%   | 1.13                      |
| `ceiling` with `DawnFeePlanner`, before the sprint ladder        | `dawn-fees`          | €9,923.03  | 372    | 97.6%   | 1.09                      |
| The lane-fee stack with the fees of `strategies/fees`, a control | `x-cap-lane-oldfees` | €10,573.65 | 384    | 97.9%   | 1.07                      |
| The same stack with `DawnFeePlanner`, before the sprint ladder   | `x-cap-lane`         | €12,346.00 | 389    | 98.5%   | 1.00                      |
| The same stack with the sprint ladder                            | `y-sprint`           | €12,435.82 | 389    | 99.0%   |                           |

On the ceiling desk alone the week won 14 orders fewer and the lower fees only just paid for that. With the lead-cost
admission and the lane fee beside it, the dawn schedule is the difference between €10,574 and €12,346: the bookings on
a later day than the post cost 1.27 to 1.34 times the typical fee, against 1.46 to 1.60 with `strategies/fees`. The
sprint ladder added €1,425 over `spread-1`, `spread-2` and `spread-4` (`y-sprint` against `y-base`: +€90, −€112,
+€1,446); one week of one seed moves by more than that between two versions with little in common.
