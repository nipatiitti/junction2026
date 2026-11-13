# Direct offers

Sends a gig straight to drivers we know are near its pickup: to fill it cheaply, and to rescue it near its
deadline. Issue #16.

The app notifies a driver of a new gig only when its pickup is within 30 km of their home. A driver who
finishes one of our gigs far from home hears of nothing nearby, though for them the next car costs only the
extra time and tickets. A direct offer reaches them.

## How it is used

`dispatch.py` builds it from the driver list and the map, as every strategy (`strategies/README.md`), and it:

- registers each gig the world accepts (`Offers.register`), with where it starts and ends, the last minute to
  collect its first car (the order's `lastPickupAt`), its drive, who may take it and its fee schedule;
- feeds every event to `Offers.observe`, and tells it about reprices and withdrawals;
- sends the offers it returns with the next step. A refused offer is counted, and the week ends with a line
  `Offers: N sent, A accepted, D declined, E expired, R refused`.

The logic needs no network: it reads only what it is given. Offers start at level 3,
where the game adds them.

## Where our drivers are

When a driver books one of our gigs, we expect them free at its last delivery place, about the drive after they
can collect the first car. When they deliver there, we know the place and the minute. A driver free more than 3
hours ago may have gone home, so they no longer count as near. Everyone else is at their home town.

## When an offer goes out, to whom, at what fee

- **A chain offer**, when we post a gig and whenever one of our drivers delivers a car: each open gig whose
  pickup is within 60 road minutes of where one of our drivers finishes, early enough to collect the car 30
  minutes before its last pickup minute. The fee is 85% of the gig's fee in the app now.
- **A rescue**, on `deadline_close`, right after the steep reprice: first the drivers who finish near the pickup,
  then the drivers who live within 45 road minutes of it and can still reach it, the most reliable first (fewest
  drops per gig). The fee is the gig's steep fee in the app: the offer reaches drivers the app never notified.

Closest first. Each driver must be allowed to drive the car: a manual licence for a gig that needs one, and
rating ≥ 4.8 with ≥ 50 completed gigs for a premium car.

## The limits

- At most three offers per driver in any 24 hours. That keeps the rule of three a day however the day is counted.
- At most three open offers per gig. An offer counts as open until its answer, or 11 minutes after we sent it.
- None from 23:00 to 07:00: no driver reads them.
- A driver who declined, did not read an offer (`expired`) or dropped a gig is not asked again that day: a driver
  who does not work today reads few offers. A driver is asked about each gig once.

## Bench

Level 8, against `main` without offers (admission control, #14, and the polling loop, #36). The run was stopped
before every seed had played on both versions, so only spread-3 and spread-4 are paired.

| Seed      |  Main margin | Offers margin | Main on time | Offers on time | Main fee per car | Offers fee per car |
| --------- | -----------: | ------------: | -----------: | -------------: | ---------------: | -----------------: |
| spread-3  |      -€53.27 |       -€21.42 |        97.0% |          96.7% |           €47.79 |             €47.66 |
| spread-4  |     -€285.29 |      -€298.49 |        97.1% |          96.7% |           €54.57 |             €54.66 |
| **Total** | **-€338.56** |  **-€319.91** |              |                |       **€51.20** |         **€51.18** |

spread-1 played only with offers: €456.36 margin, 96.4% on time.

Offers sent per week: 591 to 861, of which 3 to 7 were accepted, about a third declined and two thirds expired
unread. None was refused. An earlier version, which decided offers in the middle of a step, had 140 to 146 refused a
week: the gig had just been booked. Deciding once a step, after all the step's events, fixed that.

On the previous base, without the polling loop, the first version of offers lowered the driver fee per delivered
car from €52.54 to €52.14 over all five seeds (1,604 and 1,601 cars), at the same on-time share.

So far offers change little: drivers take under 1% of them. Most of the drivers we ask do not work that day or do
not read the offer in its 10 minutes, and the ones who read it decline at 85% of the app fee.
