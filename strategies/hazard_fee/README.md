# Hazard-priced fees

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Its `HazardFeePlanner` learns how often
this week's gigs book while they are open, then chooses the cheapest observed opening fee that is likely enough to
book before the last on-time pickup. Headroom and the other systems stay as they are. Issue #242.

| File          | Class              | Builds on         | What it decides                                         |
| ------------- | ------------------ | ----------------- | ------------------------------------------------------- |
| `fees.py`     | `HazardFeePlanner` | `LaneFeePlanner`  | The opening fee, from an online booking-hazard estimate |
| `dispatch.py` | `Desk`             | the headroom desk | The system, including the accepted-post observations    |

`HazardFeePlanner` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through
`LaneFeePlanner`, with the constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/hazard_fee/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `hazard-fee`.

## The estimator

The desk reports each accepted one-order post with its schedule and lane fee, and each accepted reprice or withdraw.
The planner then observes the same events as every other strategy. It follows an open spell until `gig_booked`, an
accepted direct offer, expiry, withdrawal or cancellation; `gig_dropped` and `no_show` start another spell. Raises
split a spell into fee bands. Only 07:00–23:00 counts as exposure, matching `day_minutes` in `gig_spells`
([`analysis/README.md`](../../analysis/README.md)); unlike the offline fit, weekend hours are not down-weighted.

Each band is 0.25 wide in fee over the lane fee by default: 0.75–1.0, 1.0–1.25, and so on. A band keeps bookings and
open daytime hours, so its hazard is bookings divided by hours. Both statistics fade exponentially with a 36-hour
wall-clock half-life. Fading is lazy at the next observation or query, not a separate clock process. A band needs six
faded daytime hours before the planner uses its rate; a band with no bookings can qualify nothing.

The data comes only from this system's own accepted gigs in the current run. Rejoined gigs use the schedule in the
current snapshot without replaying their earlier exposure a second time. Bundles retain the root desk's fee planner
and are not hazard observations.

## Choosing a fee

For a new gig the planner enumerates `ratios`: **0.75, 0.9, 1.0, 1.15, 1.4, 1.75 and 2.25** times the lane fee. The
base planner's actual opening fee is always a candidate and is a hard floor, so lower grid values cannot discount it.
For each distinct resulting fee, the estimated booking probability is

```text
1 - exp(-hazard × open daytime hours until lastPickupAt)
```

The first, cheapest candidate with probability at least **`target_prob` = 0.90** wins. If no candidate has enough
data or reaches the target, the planner returns the base lane-fee schedule. **Cold start is exactly that base
schedule.** Empty bands borrow neither a prior nor another band's rate.

Only `open` and `sprint_open` change. `dawn_plan` keeps the base raise times, top fee, price cap and ceiling; a higher
opening can collapse raises but never adds one. After a drop, the inherited planner keeps its usual dropped-fee
floor. These limits matter because a ladder with frequent or predictable raises can teach drivers to wait for a
better fee. The estimator must not create that incentive merely to explore cheaper openings.

## The variables

`Params` in `fees.py`, exported as `HazardFeeParams`, also contains every `DawnParams` field.

| Variable          | Default                               | What it does                                             |
| ----------------- | ------------------------------------- | -------------------------------------------------------- |
| `band_width`      | 0.25                                  | Width of a fee-over-lane-fee hazard band                 |
| `ratios`          | 0.75, 0.9, 1.0, 1.15, 1.4, 1.75, 2.25 | Candidate opening ratios, clamped to the base opening    |
| `target_prob`     | 0.90                                  | Required booking probability before the last pickup      |
| `min_hours`       | 6.0                                   | Minimum faded daytime exposure before a band can be used |
| `half_life_hours` | 36.0                                  | Half-life of exposure and bookings; 0 disables fading    |

This is an online estimator, not a fitted performance result. No offline or online score is claimed here.
