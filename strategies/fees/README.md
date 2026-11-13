# Fee schedules

Plans the fee schedule of each gig at levels 7 and 8. It replaces the starter's `rising` fees (the typical
fee, plus 10% an hour up to 1.5 times) and `steep` fees (1.5 to 2.5 times, only after `deadline_close`),
whose top comes too late for many cars.

`dispatch.py` calls it from `Desk.fees_for`, which every post, repost and reprice of one order uses, from
`Desk.dropped`, after `gig_dropped`, and through `plan` and `after_drop` for a bundle of several orders'
cars (`strategies/bundling`).

| File          | What it holds                                                                   |
| ------------- | ------------------------------------------------------------------------------- |
| `schedule.py` | The schedule: pure functions of a gig's facts and the time, with every constant |
| `market.py`   | Where the drivers live, from the map and the driver list                        |
| `__init__.py` | `FeePlanner`: turns an order and its request into a gig's facts                 |
| `results/`    | The bench that compares versions of the constants, and every week it played     |

## How a schedule is built

1. **Top fee and when it is due.** The top fee is 2.5 times the typical fee, the top of the starter's
   steep fees, cut to the ceiling. It is due a travel margin before `lastPickupAt`: an hour to see the
   gig, plus 1.5 times the road minutes from the homes of the 10 nearest drivers to the pickup, at least
   6 hours and at most 8. Most late cars had drivers who would take them at the top fee but could no
   longer reach the pickup inside its window, so the top comes early in the pickup day. A top fee due at
   night (23:00 to 07:00) moves to 22:00 the evening before, because drivers rarely look at the app at
   night.
2. **Opening fee.** 0.9 times the typical fee. With less than 8 hours left before the top fee is due,
   the opening moves towards the top fee, in proportion to the time that is short. With an hour or less
   left, the schedule is the top fee alone. The opening premiums of #15 (`OPEN_SCARCE`, `OPEN_EVENING`,
   `OPEN_SATURDAY`, `OPEN_LONG`) are set to 0: with admission control, two thirds of the gigs book at their
   opening fee, and the premiums made them dearer without booking more of them.
3. **Raises.** Two small raises, an hour and three hours after the post: 10% and 30% of the way from the
   opening fee to the top fee, 1.06 and 1.38 times the typical fee. The fee then holds until the top fee
   is due. Drivers who know they work the next day book early, before their day fills up, and few gigs
   book dear. Steps that would not change the fee are left out.
4. **Ceiling.** No step before the top goes above the order's price for the gig's cars, so the order
   still breaks even. The top fee may reach twice the price: the price plus the refund of a car late by
   more than two business days, the whole price. An on-time car never costs more than a late one.
5. **A late car.** When `lastPickupAt` has passed, the schedule is the top fee at once.
6. **Drops.** After `gig_dropped`, a gig with less than 6 hours left before its top fee is repriced. It
   opens at least 15% above the fee that the driver dropped: that fee only just paid them, and they
   book again only for more. With more time left, the schedule in the app stays.

The rules hold for every schedule: whole minutes and cents, steps in time order, fees never falling,
1 to 48 steps, and one step at level 1 (the opening fee).

## Inputs

| Input                               | From                                                        |
| ----------------------------------- | ----------------------------------------------------------- |
| Typical fee and price, for the cars | The request's `referenceFeeCents`, the order's `priceCents` |
| `lastPickupAt`, ready time          | The order: its first car that is not delivered yet          |
| Drive minutes                       | The map's road minutes from the pickup to the delivery      |
| Scarcity and travel time of drivers | The driver list's home towns and the map, read once         |

All the constants are at the top of `schedule.py` and `market.py`.

## Bench results

Level 8, against the starter's fees (`starter`). Every week is a line in `results/bench.jsonl`, made with
`results/bench.py`, which also sums driver fees, refunds and penalties from the ledger, and saves the week to
`data/scrape/runs`. The bench plays a version of the constants on top of this checkout's `dispatch.py`; the
`Main` column is the main it ran on. Weeks are fast now: 8 at a time, 15 weeks take about 15 minutes.

```sh
uv run python strategies/fees/results/bench.py starter,v16 --seeds spread-1..5   # play
uv run python strategies/fees/results/bench.py --table --seeds spread-1..5       # the tables below
```

### On main with admission control and bundling

The constants in `schedule.py` are `v16`. Both criteria of #62 hold on `spread-1` to `spread-5`: more orders on
time than with the starter's fees, at no higher fee per delivered car. They also hold on `spread-6` to
`spread-10`, which played no part in choosing `v16`. `v3`, the schedule merged in #15, costs €3.50 more per
car than the starter's fees here.

| Seeds   | Version   | Margin  | On time | Fees per delivered car | Refunds and penalties per car |
| ------- | --------- | ------- | ------- | ---------------------- | ----------------------------- |
| 1 to 5  | `starter` | €30,566 | 97.1%   | €69.73                 | €0.95                         |
| 1 to 5  | `v3`      | €24,559 | 96.9%   | €73.24                 | €1.16                         |
| 1 to 5  | `v16`     | €31,569 | 97.5%   | €69.72                 | €0.88                         |
| 6 to 10 | `starter` | €41,396 | 97.8%   | €74.57                 | €1.23                         |
| 6 to 10 | `v16`     | €41,300 | 98.5%   | €74.11                 | €0.74                         |

`v16` has more orders on time than the starter's fees on 9 of the 10 seeds.

### Choosing the constants

Played on main `043e1c7`, with admission control and before bundling. Each version is a set of constants in
`VERSIONS` in `results/bench.py`.

| Version   | What it is                                                                                          |
| --------- | --------------------------------------------------------------------------------------------------- |
| `starter` | The starter's `rising` and `steep` fees                                                             |
| `v3`      | The schedule merged in #15: opening premiums, raises 1/3 and 2/3 of the way to a top of 2 times     |
| `v4`      | `v3` opening at 1.1 times or more, top due 4 hours or more before `lastPickupAt`, `LATE_SHARE` 0.75 |
| `v5`      | `v4` with a top of 2.5 times under twice the price                                                  |
| `v6`      | `v4` without the opening premiums                                                                   |
| `v7`      | `v6` with small early raises, 10% and 30% of the way to the top                                     |
| `v8`      | `v7` with the top due 5 hours or more before `lastPickupAt`                                         |
| `v9`      | `v8` opening at 0.9 times                                                                           |
| `v10`     | `v8` with the scarcity premium                                                                      |
| `v11`     | `v9` with the scarcity premium                                                                      |
| `v12`     | `v9` with the top due 6 to 8 hours before `lastPickupAt`                                            |
| `v13`     | `v9` with a top of 2.5 times under twice the price                                                  |
| `v14`     | `v8` opening at 0.95 times                                                                          |
| `v15`     | `v13` opening at 0.85 times                                                                         |
| `v16`     | `v13` with the top due 6 to 8 hours before `lastPickupAt`: `schedule.py` now                        |

| Seeds   | Version   | Margin  | On time | Fees per delivered car | Refunds and penalties per car |
| ------- | --------- | ------- | ------- | ---------------------- | ----------------------------- |
| 1 to 5  | `starter` | €32,326 | 97.1%   | €70.23                 | €1.00                         |
| 1 to 5  | `v3`      | €26,529 | 97.3%   | €73.38                 | €1.05                         |
| 1 to 5  | `v4`      | €22,198 | 97.7%   | €77.52                 | €1.06                         |
| 1 to 5  | `v5`      | €16,870 | 97.8%   | €80.71                 | €1.05                         |
| 1 to 5  | `v6`      | €27,648 | 97.3%   | €73.70                 | €1.28                         |
| 1 to 5  | `v7`      | €32,845 | 96.1%   | €69.94                 | €1.52                         |
| 1 to 5  | `v8`      | €31,967 | 97.2%   | €70.38                 | €1.37                         |
| 1 to 5  | `v9`      | €36,248 | 96.7%   | €66.58                 | €1.38                         |
| 1 to 5  | `v10`     | €31,102 | 96.8%   | €71.75                 | €1.17                         |
| 1 to 5  | `v11`     | €35,479 | 96.9%   | €66.79                 | €1.21                         |
| 1 to 5  | `v12`     | €36,808 | 97.0%   | €67.42                 | €1.31                         |
| 1 to 5  | `v13`     | €31,773 | 97.4%   | €70.38                 | €1.03                         |
| 1 to 5  | `v14`     | €35,756 | 97.0%   | €67.59                 | €1.12                         |
| 1 to 5  | `v15`     | €31,997 | 97.2%   | €68.78                 | €1.17                         |
| 1 to 5  | `v16`     | €31,078 | 97.9%   | €70.14                 | €0.98                         |
| 6 to 10 | `starter` | €40,647 | 98.1%   | €73.94                 | €0.64                         |
| 6 to 10 | `v3`      | €35,039 | 97.8%   | €77.62                 | €0.98                         |
| 6 to 10 | `v9`      | €48,366 | 97.1%   | €68.77                 | €1.26                         |
| 6 to 10 | `v16`     | €38,092 | 98.1%   | €75.90                 | €1.11                         |

What the runs show:

- With admission control the shortage is mild: the week wins 300 to 380 orders, not 950, and 97% of them are
  on time with any fees. Late cars cost about €1 per delivered car in refunds and penalties, so a fee schedule
  pays for more on-time orders only if it costs almost nothing more.
- About two thirds of the gigs book at their opening fee in every version. With `v3`'s premiums the
  average gig opened at 1.08 times the typical fee and no more of them booked at it, and its raises reached
  about 1.35 and 1.7 times within 3 hours, against the starter's 1.1 and 1.3.
- Most late cars had 100 to 150 viewers and no booking until their gig expired at the end of its window;
  posted again without windows, they booked within minutes at the top fee, for the next morning. Their
  drivers wanted the fee but could no longer reach the pickup in time. A top fee due earlier in the pickup
  day (`v12`, `v16`) books more of them.
- Opening at 0.9 times the typical fee saves €3.50 to €5 per car on both seed sets (`v9`). `v16` spends that
  on a higher, earlier top. On `043e1c7`, `spread-6` to `spread-10` did not repeat `v16`'s gain on the seeds
  that chose it; on main with bundling they did. One seed's on-time share moves by a point between two
  versions with little in common, so compare versions on 10 seeds. Whether fees should aim for margin (`v9`)
  rather than on-time share is issue #109.

### Earlier runs, #15

Played on main before admission control, when the week won about 950 orders and half of them were late.
`baseline` is the starter's fees, `v1` to `v3` as above.

| Seeds         | Version    | Margin    | On time | Fees per delivered car | Refunds and penalties per car |
| ------------- | ---------- | --------- | ------- | ---------------------- | ----------------------------- |
| spread-1 to 5 | `baseline` | −€334,779 | 52.0%   | €124.35                | €31.76                        |
| spread-1 to 5 | `v1`       | −€263,822 | 51.0%   | €107.50                | €31.81                        |
| spread-2, 3   | `v3`       | −€84,144  | 55.9%   | €103.88                | €25.85                        |
| spread-1, 3   | `v2`       | −€115,422 | 52.8%   | €111.27                | €32.58                        |
