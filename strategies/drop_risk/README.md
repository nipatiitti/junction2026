# Drop-risk fees

A dispatch system built on [`strategies/headroom`](../headroom/README.md). It changes only the fee planner: the lane-fee
dawn schedule costs more where drivers give booked gigs back or fail to show, and its raises come sooner there. The
headroom desk, its admission and pricing, and the systems it builds on stay unchanged.

| File          | Class                | Builds on         | What it decides                                      |
| ------------- | -------------------- | ----------------- | ---------------------------------------------------- |
| `fees.py`     | `DropRiskFeePlanner` | `LaneFeePlanner`  | The drop-rate estimate, fee premium and raise timing |
| `dispatch.py` | `Desk`               | the headroom desk | The system, and each posted gig's pickup town        |

`DropRiskFeePlanner` is a `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the usual constructor and a
frozen `Params`, which extends `DawnParams`. The desk feeds it every event and calls `register` after each accepted
post so it can associate later bookings and failures with a pickup town.

## Run it

From the repository root:

```sh
uv run strategies/drop_risk/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `drop-risk` through the same recorder as the other systems.

## The estimator

Each pickup town has two exponentially faded quantities: booking weight `B` and failure weight `D`. On every
`gig_booked`, and on an accepted direct offer, old weights are multiplied by `fade` (0.9) and `B` gains 1. Every
`gig_dropped` or `no_show` adds 1 to `D`. Booking the same gig again after a failure is another booking. The town rate
is `min(1, D / B)`, so it is events per booking rather than a probability: repeated failures of one gig can make the
raw ratio exceed 1. No time-based decay or cross-town prior is used.

A bundle counts at its first pickup town, as identified by its first pickup stop. Its other pickups do not get separate
observations.

## Premium and clamps

For a town rate `r`, each fee in the base lane-fee schedule is multiplied by

```text
1 + drop_premium × r
```

with `drop_premium` 0.75. The result is clamped between the base schedule's opening fee and its top fee. Those are the
floor and cap produced by the base dawn planner after its own lane-fee multiples, pickup urgency, order-worth limit and
ceiling have been applied. Consequently the premium cannot push a schedule above the base planner's top. This same
rule applies when the base planner supplies an after-drop reprice; when it leaves the app's schedule unchanged, this
planner does too.

At a rate of at least `high_risk` (0.08), the schedule also flattens: every other intermediate raise is kept, and each
kept raise moves `earlier` (0.5) of the way from its base time towards the post. The opening and final top keep their
base times. The common schedule validator removes collapsed or duplicate steps and keeps whole cents, ordered times and
nondecreasing fees. Later, smaller raises therefore compete less with the fee intended to keep the first booking.

## Cold start

A town with no bookings has rate zero. A town whose observed bookings have produced no drops or no-shows also has rate
zero. Both return the base schedule object unchanged, with no premium and no flattening. There is no assumed background
drop rate and no learning from another town.

`Params` adds `drop_premium`, `fade`, `high_risk` and `earlier` to the inherited dawn-schedule variables. The defaults
are explicit strategy assumptions, not fitted performance claims.
