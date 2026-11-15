# Offer probe

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `ProbeOffers` replaces the usual direct
offers with targeted measurements of which fee ratios drivers accept. Issue #253. Headroom and the systems below it
stay as they are; admission, fee schedules and pricing do not change.

| File          | Class         | Builds on         | What it decides                                   |
| ------------- | ------------- | ----------------- | ------------------------------------------------- |
| `offers.py`   | `ProbeOffers` | `Offers`          | Whom to offer a gig to, and the offered fee ratio |
| `dispatch.py` | `Desk`        | the headroom desk | The headroom system with the offer strategy above |

## Run it

From the repository root:

```sh
uv run strategies/offer_probe/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `offer-probe`. The strategy has a frozen `Params` and the usual constructor
`(roster, world_map, level=8, params=None)`.

## Targeting: no cold offers

The base strategy first chooses drivers who can reach the pickup in time and keeps its usual ordering. `ProbeOffers`
then admits a driver only with positive evidence of activity:

- they viewed, booked or started one of our gigs today; or
- they completed the last delivery of one of our gigs within `recent_hours` = 3 hours.

A driver with neither sign of life gets no offer, including during a rescue. The base audience and reachability checks
still apply: licence and experience, nearby position, time to reach the pickup, three offers per driver in 24 hours,
three open per gig, one offer per driver per gig, none from 23:00 to 07:00, and no re-asking after a decline, expiry
or drop.

## Acceptance estimator

Every offer records its configured fee ratio. An `offer_answered` event with `accepted` or `declined` updates two
counts at that ratio: one for the driver and one for the gig's pickup town. The acceptance rate is
`accepted / (accepted + declined)`, with no smoothing or minimum sample size. At a given ratio the driver's own rate
takes precedence; if the driver has no observation there, the town's rate is used.

**Expired offers teach nothing about price.** They were not read, so they update neither acceptance rate. They still
count as expired in the summary and suppress further offers to that driver that day, as in the base strategy.

`town_acceptance(pickup, ratio)` returns the town's observed rate at an exact grid ratio, or `None` when there is no
accepted/declined observation. It only reads the estimator and is available for later strategies; nothing else uses
it yet.

## Fee grid and cold start

For each driver, ratios are considered from lowest to highest in `fee_grid` = (0.65, 0.75, 0.85, 1.0), as shares of
the gig's current app fee. The first whose observed acceptance rate is at least `target_accept` = 0.25 is offered.
If observations exist but none clears the target, the top grid ratio is used. The fee is rounded to the nearest cent.

With no observations at any ratio, the cold start is the base rule: 0.85 of the app fee for a chain offer and 1.0 for
a rescue. Since a rescue uses the current app fee after its steep reprice, its cold-start offer is the steep fee.
The grid applies to that same current fee for later probes.

| Variable        | Default                 | What it does                                               |
| --------------- | ----------------------- | ---------------------------------------------------------- |
| `recent_hours`  | 3                       | How long a completed gig counts as recent driver activity  |
| `target_accept` | 0.25                    | Accepted share a ratio must reach to be chosen             |
| `fee_grid`      | (0.65, 0.75, 0.85, 1.0) | Nonempty set of app-fee ratios to consider, cheapest first |

No online weeks or performance measurements are reported here.
