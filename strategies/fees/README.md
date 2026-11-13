# Fee schedules

Plans the fee schedule of each gig for a driver shortage (levels 7 and 8). It replaces the starter's
`rising` fees (the typical fee, plus 10% an hour up to 1.5 times) and `steep` fees (1.5 to 2.5 times,
only after `deadline_close`). The starter's fees come too late for most cars and teach drivers to wait
for the top.

`dispatch.py` calls it from `Desk.fees_for`, which every post, repost and reprice uses, and from
`Desk.dropped`, after `gig_dropped`.

| File          | What it holds                                                                   |
| ------------- | ------------------------------------------------------------------------------- |
| `schedule.py` | The schedule: pure functions of a gig's facts and the time, with every constant |
| `market.py`   | Where the drivers live, from the map and the driver list                        |
| `__init__.py` | `FeePlanner`: turns an order and its request into a gig's facts                 |

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
   than 24 hours: an on-time car never costs more than a late one.
5. **A late car.** When `lastPickupAt` has passed, the schedule is the top fee at once. A day after
   `lastPickupAt` it rises to 2.5 times the typical fee, under a ceiling of twice the price. Later, the
   refund is the whole price, and a car never delivered costs twice its price on top.
6. **Drops.** After `gig_dropped`, a gig with less than 6 hours left before its top fee is repriced. It
   opens at least 15% above the fee that the driver dropped: that fee only just paid them, and they
   book again only for more. With more time left, the schedule in the app stays.

The rules hold for every schedule: whole minutes and cents, steps in time order, fees never falling,
1 to 48 steps, and one step at level 1 (the opening fee).

## Inputs

| Input                                  | From                                                     |
| -------------------------------------- | -------------------------------------------------------- |
| Typical fee and price, for the cars    | The request's `referenceFeeCents`, the order's `priceCents` |
| `lastPickupAt`, ready time             | The order: its first car that is not delivered yet       |
| Drive minutes                          | The map's road minutes from the pickup to the delivery   |
| Scarcity and travel time of drivers    | The driver list's home towns and the map, read once      |

All the constants are at the top of `schedule.py` and `market.py`.

## Bench results

RESULTS
