# Dawn fees

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling desk
whose fee schedules follow the drivers' day. Issue #200. Ceiling, the root system and `strategies/fees` stay as they
are.

| File          | Class            | Builds on        | What it decides                                           |
| ------------- | ---------------- | ---------------- | --------------------------------------------------------- |
| `fees.py`     | `DawnFeePlanner` | `FeePlanner`     | The fee schedule of a gig that has a morning to wait for  |
| `dispatch.py` | `Desk`           | the ceiling desk | The system: the ceiling desk with the fee planner above   |

`DawnFeePlanner` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `FeePlanner`, with
the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/dawn_fees/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/dawn_fees/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `dawn-fees`. The `Dawn fees` line at the end of a week counts the schedules that
got a dawn ladder and those that did not.

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
5. **Every other gig** gets the schedule of `strategies/fees`: a gig with no dawn before its last pickup, a late
   car, a gig after its deadline warning, and every gig at level 1.

The top fee, its ceiling of twice the order's price, and the rule that no step before the top goes above the price
are those of `strategies/fees`. After a drop with little time left, the gig steps up from the dropped fee on the same
schedule. Bundles of several orders keep the root desk's schedule.

| Example                                | `strategies/fees`                         | Dawn fees                                                              |
| -------------------------------------- | ----------------------------------------- | ---------------------------------------------------------------------- |
| Posted Mon 11:00, last pickup Tue 17:00 | 0.90, 1.06 at 12:00, 1.38 at 14:00, 2.50 Tue 11:00 | 0.90, 1.00 at 13:00, Tue 1.15 at 06:00, 1.34, 1.57, 2.50 at 11:00 |
| Posted Mon 15:00, last pickup Tue 11:00 | 1.10, 1.24, 1.52, 2.50 at Mon 22:00       | 0.90, 1.00 at 17:00, 1.40 at 20:00, 2.50 Tue 07:00                     |
| Posted Mon 10:00, last pickup Wed 16:00 | 0.90, 1.06, 1.38 at 13:00, 2.50 Wed 10:00 | 0.90, 1.00 at 12:00, Wed 1.15 at 06:00, 1.40, 2.50 at 10:00            |
| Posted Mon 10:00, last pickup Mon 17:00 | 2.50                                      | 2.50 (no dawn: the same schedule)                                      |

Fees are multiples of the typical fee, for an order priced at 1.6 times it.

## The variables

`Params` in `fees.py`, exported as `DawnParams`. Each fee is a multiple of the gig's typical fee.

| Variable     | Default | What it does                                                             |
| ------------ | ------- | ------------------------------------------------------------------------ |
| `open`       | 0.9     | The opening fee                                                          |
| `hold`       | 1.0     | The fee after `patience`, held until the last dawn                       |
| `patience`   | 2 hours | How long the opening fee stays                                           |
| `quiet_from` | 22:00   | No raise on the posting day from this hour                               |
| `evening_at` | 20:00   | The evening before the last dawn: the hold fee at the latest, or `tight` |
| `tight`      | 1.4     | That evening's fee when the top is due before dawn                       |
| `dawn_at`    | 06:00   | When the drivers plan their day                                          |
| `dawn`       | 1.15    | The fee at the last dawn                                                 |
| `reach`      | 3 hours | The time a driver who books at dawn needs to get to the car              |
| `step`       | 1 hour  | How often the ladder from the dawn fee to the top fee rises              |
| `top`        | 2.5     | The top fee, before the ceiling of `strategies/fees` cuts it             |
