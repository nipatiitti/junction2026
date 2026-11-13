# Direct offers

Sends a gig straight to drivers we know are near its pickup: to fill it cheaply, and to rescue it near its
deadline. Issue #16.

The app notifies a driver of a new gig only when its pickup is within 30 km of their home. A driver who
finishes one of our gigs far from home hears of nothing nearby, though for them the next car costs only the
extra time and tickets. A direct offer reaches them.

## How it is used

`dispatch.py` shares the driver list and the map it loads for admission, and it:

- registers each gig the world accepts (`Offers.register`), with where it starts and ends, the last minute to
  collect its first car (the order's `lastPickupAt`), its drive, who may take it and its fee schedule;
- feeds every event to `Offers.observe`, and tells it about reprices and withdrawals;
- sends the offers it returns with the next step. A refused offer is counted, and the week ends with a line
  `Offers: N sent, A accepted, D declined, E expired, R refused`.

The logic needs no network, so it is tested offline on a hand-made map and roster. Offers start at level 3,
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

Seeds `spread-1` to `spread-5`, level 8, against the same system without offers (admission control, #14).

BENCH_TABLE
