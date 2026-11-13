# Fee schedules

Plans the fee schedule of each gig for a driver shortage (levels 7 and 8). It replaces the starter's
`rising` fees (the typical fee, plus 10% an hour up to 1.5 times) and `steep` fees (1.5 to 2.5 times,
only after `deadline_close`). The starter's fees come too late for most cars and teach drivers to wait
for the top.

`dispatch.py` calls it from `Desk.fees_for`, which every post, repost and reprice uses, and from
`Desk.dropped`, after `gig_dropped`.

| File          | What it holds                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------------- |
| `schedule.py` | The schedule: pure functions of a gig's facts and the time, with every constant                                     |
| `market.py`   | Where the drivers live, from the map and the driver list                                                            |
| `__init__.py` | `FeePlanner`: turns an order and its request into a gig's facts, with the typical fee of the trip the cars make now |

## How a schedule is built

1. **Top fee and when it is due.** The top fee is twice the typical fee, cut to the ceiling. It is due a
   travel margin before `lastPickupAt`: an hour to see the gig, plus 1.5 times the road minutes from the
   homes of the 10 nearest drivers to the pickup. The margin is at least 3 hours, the time of
   `deadline_close`, and at most 6. A top fee due at night (23:00 to 07:00) moves to 22:00 the evening
   before, because drivers rarely look at the app at night.
2. **Opening fee.** The typical fee, plus a premium for each thing that makes the work dearer than the
   typical fee assumes:
   - up to 30% where few drivers live within reach of the pickup. Each driver counts by the road time
     from their home (an hour away counts about a third), against the world's median place;
   - 10% when the drive ends after 18:00, when the trip home is dear;
   - 15% for Saturday work;
   - 5% for a drive of 3 hours or more, a long trip home from the delivery town.

   With less than 8 hours left before the top fee is due, the opening moves towards the top fee, in
   proportion to the time that is short. With an hour or less left, the schedule is the top fee alone.
3. **Raises.** Three raises at even times from now to the top fee's time, at even fees from the opening
   fee to the top fee. Steps that would not change the fee are left out. Three large raises, rather than
   the starter's hourly ones, give drivers less reason to wait for the next one.
4. **Ceiling.** No step before the top goes above the order's price for the gig's cars, so the order
   still breaks even. The top fee may reach the price plus half of it, the refund for a car late by more
   than 24 hours: an on-time car never costs more than a late one. When the trip's typical fee is above
   the price, after a change of destination (below), the typical fee takes the price's place in both
   rules. No fee on time goes above three times the price: a car never delivered loses its price and
   pays twice the price, so past that, leaving the car costs less than delivering it.
5. **A late car.** When `lastPickupAt` has passed, the schedule is the top fee at once. A day after
   `lastPickupAt` it rises to 2.5 times the typical fee, under a ceiling of twice the price. Later, the
   refund is the whole price, and a car never delivered costs twice its price on top. A top fee above
   twice the price, for a car sent farther, stays: fees never fall.
6. **Drops.** After `gig_dropped`, a gig with less than 6 hours left before its top fee is repriced. It
   opens at least 15% above the fee that the driver dropped: that fee only just paid them, and they
   book again only for more. With more time left, the schedule in the app stays.

The rules hold for every schedule: whole minutes and cents, steps in time order, fees never falling,
1 to 48 steps, and one step at level 1 (the opening fee).

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

Level 8, against the starter's fees (`baseline`). Every run is in `results/bench.jsonl`, made with
`results/bench.py`, which also sums driver fees, refunds and penalties from the ledger. Weeks take about
8 minutes each from a cloud session, so not every version ran on every seed.

| Version    | What it is                                                                                                |
| ---------- | --------------------------------------------------------------------------------------------------------- |
| `baseline` | The starter's `rising` and `steep` fees                                                                   |
| `v1`       | This module with raises at even times from now to the top fee                                             |
| `v2`       | `v1`, opening at 1.1 times or more, top fee due 4 hours or more before the last pickup, `LATE_SHARE` 0.75 |
| `v3`       | `v1` with the two raises before the top in the first 1 and 3 hours: the code in this folder               |

| Seeds         | Version    | Margin    | On time | Fees per delivered car | Refunds and penalties per car |
| ------------- | ---------- | --------- | ------- | ---------------------- | ----------------------------- |
| spread-1 to 5 | `baseline` | −€334,779 | 52.0%   | €124.35                | €31.76                        |
| spread-1 to 5 | `v1`       | −€263,822 | 51.0%   | €107.50                | €31.81                        |
| spread-2, 3   | `baseline` | −€102,344 | 57.9%   | €116.11                | €25.75                        |
| spread-2, 3   | `v1`       | −€85,273  | 55.2%   | €103.46                | €27.12                        |
| spread-2, 3   | `v3`       | −€84,144  | 55.9%   | €103.88                | €25.85                        |
| spread-1, 3   | `baseline` | −€128,049 | 51.8%   | €121.69                | €28.95                        |
| spread-1, 3   | `v2`       | −€115,422 | 52.8%   | €111.27                | €32.58                        |

What the runs show:

- Fees per delivered car fall by €10 to €17 in every version, and the margin rises by €12,000 to
  €71,000. Drivers stop waiting for raises: the median booked fee over the first fee viewed falls from
  1.3 to 1.5 with the starter's fees to 1.0.
- The on-time share does not rise yet with `v1` or `v3`. The issue's acceptance criterion is not met.
  `v2`, with dearer opening fees and an earlier top, beats the starter's on-time share on its two seeds,
  at a smaller margin gain.
- The shortage limits what fees can do. On `spread-1`, about 120 different drivers book on a working day,
  about one gig each, against 150 to 250 orders a day, and most late orders find their driver just after
  `lastPickupAt`, once their gig is posted again without windows. Fees decide which orders get the
  drivers and at what cost; winning fewer orders (issue #14) adds more on-time share than fees can.
- On `spread-3`, the orders that the starter delivered on time and `v1` did not had a lead of about a
  day: the starter's hourly raises had them booked 24 hours ahead. `v3` raises early for that reason.
