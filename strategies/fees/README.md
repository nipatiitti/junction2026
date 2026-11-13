# Fee schedules

Plans the fee schedule of each gig at levels 7 and 8. It replaces the starter's `rising` fees (the typical
fee, plus 10% an hour up to 1.5 times) and `steep` fees (1.5 to 2.5 times, only after `deadline_close`),
whose top comes too late for many cars.

`dispatch.py` calls it from `Desk.fees_for`, which every post, repost and reprice of one order uses, from
`Desk.dropped`, after `gig_dropped`, and through `plan` and `after_drop` for a bundle of several orders'
cars (`strategies/bundling`).

| File          | What it holds                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------------- |
| `schedule.py` | The schedule: pure functions of a gig's facts and the time, with every constant                                     |
| `market.py`   | Where the drivers live, from the map and the driver list                                                            |
| `fees.py`     | `FeePlanner`: turns an order and its request into a gig's facts, with the typical fee of the trip the cars make now |
| `results/`    | The bench that compares versions of the constants, and every week it played                                         |

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
   more than two business days, the whole price. An on-time car never costs more than a late one. When the
   trip's typical fee is above the price, after a change of destination (below), the typical fee takes the
   price's place in both rules. No fee on time goes above three times the price: a car never delivered
   loses its price and pays twice the price, so past that, leaving the car costs less than delivering it.
5. **A late car.** When `lastPickupAt` has passed, the schedule is the top fee at once: 2.5 times the
   typical fee under twice the price, where the starter's steep fees end. A top fee above twice the price,
   for a car sent farther, stays: fees never fall.
6. **Drops.** After `gig_dropped`, a gig with less than 6 hours left before its top fee is repriced. It
   opens at least 15% above the fee that the driver dropped: that fee only just paid them, and they
   book again only for more. With more time left, the schedule in the app stays.

The rules hold for every schedule: whole minutes and cents, steps in time order, fees never falling,
1 to 48 steps, and one step at level 1 (the fee the ladder below opens at).

## Level 1: the fee ladder

At level 1 a schedule has one step, drivers do not learn our fees, and they do not drop. At the typical
fee, 90% of the gigs of a level 1 week booked within 3 minutes, so the typical fee pays far more than the
cheapest driver needs. `ladder` in `schedule.py` plans the fees a gig goes through instead:

1. It opens at half the typical fee (`LADDER_OPEN`).
2. While no driver books it, `Desk.raises_due` in `dispatch.py` raises it with `reprice` every 30 minutes
   (`LADDER_STEP`, on the clock's half hours, so all gigs rise at the same minutes), in 12 even steps
   (`LADDER_RAISES`), up to the fee that the plan above would open at. Raises wait from 23:00 to 07:00,
   when drivers sleep, and end an hour before the top fee is due.
3. With less than 3 hours (`LADDER_MIN_SPAN`) before the top fee is due, there is no ladder: the gig goes
   at the plan's fee at once. The deadline warning raises the gig as at other levels.

The ladder stops when a driver books the gig, or the gig expires, is withdrawn or is cancelled.

## A change of destination

When a dealer sends a car to another place (`order_changed`), the world sends it there, and the driver
is paid for the trip they make. The order's legs then go to the new place, while the request's keep the
old one, and its `referenceFeeCents` is the typical fee of the old trip. The price stays the same.

`FeePlanner.typical` compares the two. When a car's pickup or delivery place has changed, the typical
fee is that of the new trip: €16.03 plus €23.19 an hour of road minutes from the pickup to the new place,
for the first car of the order. That line is fitted on the single-car requests of the saved level-8 weeks,
one week per seed (12 seeds); a trade-in's typical fee is about that of its first car's trip. Against the
mean typical fee of the new lane in the saved weeks, it is 5% off at the median on the 212 saved changes
of destination, where the request's own fee scaled by the road minutes is 28% off: the request's noise
says nothing about the new lane. Every schedule of the order then follows the new trip: posts, reposts,
reprices, drops and bundles.

A car sent farther often costs more than its price: the new trip's typical fee is above the price for 27
of the 40 cars sent farther on 12 seeds. The ceilings then follow the typical fee (rule 4), up to three
times the price. On those seeds, replayed with `FeePlanner` at the minute of the change:

| Cars sent            | Opening fee, before → now | Top fee, before → now | Top at the typical fee or more |
| -------------------- | ------------------------- | --------------------- | ------------------------------ |
| Farther (40 changes) | 0.50 → 0.99               | 0.86 → 1.33           | 40% → 80%                      |
| Nearer (35 changes)  | 2.17 → 1.30               | 3.81 → 1.94           | 100% → 100%                    |

Fees are medians over the new lane's mean typical fee. Turku to Raisio (8 road minutes, typical fee €12.03,
price €30.15) sent to Vaasa now tops at €90.45, three times its price, against €24.06 before; the lane's
typical fee is €105. A car whose new trip needs more than three times its price can still stay
undelivered, on purpose: 8 of the 40 cars sent farther.

On the bench (`uv run python -m strategies.bench dispatch.py origin/main`, level 8, `spread-1` to
`spread-5`), the orders whose destination changed:

| Sent    | Version       | Orders | On time | Late | Never delivered | Their net |
| ------- | ------------- | ------ | ------- | ---- | --------------- | --------- |
| Farther | `origin/main` | 23     | 15      | 6    | 2               | −€221     |
| Farther | this change   | 22     | 19      | 3    | 0               | −€131     |
| Nearer  | `origin/main` | 17     | 17      | 0    | 0               | €656      |
| Nearer  | this change   | 18     | 18      | 0    | 0               | €978      |

The three late cars were booked before the change: the world sends the booked driver to the new place,
and no fee of ours can move them. Over the whole weeks, the margin rose by €909 (higher on 3 of 5 seeds),
the on-time share from 96.9% to 97.1%, and no order was left undelivered, against 2.

## Inputs

| Input                               | From                                                                                          |
| ----------------------------------- | --------------------------------------------------------------------------------------------- |
| Typical fee and price, for the cars | The request's `referenceFeeCents`, or the new trip's after a change; the order's `priceCents` |
| `lastPickupAt`, ready time          | The order: its first car that is not delivered yet                                            |
| Drive minutes                       | The map's road minutes from the pickup to the delivery                                        |
| Scarcity and travel time of drivers | The driver list's home towns and the map, read once                                           |

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

The constants in `schedule.py` are `v16`. Both criteria of #62 hold on `spread-1` to `spread-5` on the latest
main (`338074c`, with the fees after a change of destination from #94): more orders on time than with the
starter's fees, at no higher fee per delivered car, and with fewer refunds and penalties. On main `babc458`,
just before #94, they also hold on `spread-6` to `spread-10`, which played no part in choosing `v16`. `v3`,
the schedule merged in #15, costs €3.50 more per car than the starter's fees there.

| Main      | Seeds   | Version   | Margin  | On time | Fees per delivered car | Refunds and penalties per car |
| --------- | ------- | --------- | ------- | ------- | ---------------------- | ----------------------------- |
| `338074c` | 1 to 5  | `starter` | €30,566 | 97.1%   | €69.73                 | €0.95                         |
| `338074c` | 1 to 5  | `v16`     | €31,845 | 97.5%   | €69.43                 | €0.83                         |
| `babc458` | 1 to 5  | `starter` | €30,566 | 97.1%   | €69.73                 | €0.95                         |
| `babc458` | 1 to 5  | `v3`      | €24,559 | 96.9%   | €73.24                 | €1.16                         |
| `babc458` | 1 to 5  | `v16`     | €31,569 | 97.5%   | €69.72                 | €0.88                         |
| `babc458` | 6 to 10 | `starter` | €41,396 | 97.8%   | €74.57                 | €1.23                         |
| `babc458` | 6 to 10 | `v16`     | €41,300 | 98.5%   | €74.11                 | €0.74                         |

On `338074c`, `v16` has more orders on time than the starter's fees on 4 of the 5 seeds, and on `spread-1`
0.05 points fewer. On `babc458` it has more on 9 of the 10 seeds.

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
