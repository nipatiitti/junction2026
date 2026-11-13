# Fee models

The fee and capacity side of `src/BRIEF.md` (Design 2–4, findings 7–12) as pure TypeScript: no network,
no packages, plain data in and out. A strategy builds a `FeeGig` for a request or an order, asks `planFees` for
the schedule and its cost `c`, and passes every world event to `learn`.

```ts
import { featuresOf, feeParams, fewDriversNear, learn, newFeeState, planFees } from './models/fees/index.ts'

const params = feeParams(level) // or feeParams(level, { cold: true, solver: false, ... })
const state = newFeeState(params)
const features = featuresOf(order.legs, order.deadline, now, fewDriversNear(deliveryPlace, drivers, map))
const gig = { typicalCents, priceCents, lastPickupAt, region: pickupPlace, features, experienced, seen: false }
const { schedule, costCents } = planFees(gig, now, state, params)
learn(state, { kind: 'gig_posted', at: now, gigId, orderIds: [order.id], gig, schedule }, params)
learn(state, event, params) // every world event; the ones the models do not use change nothing
```

| File        | What it holds                                                               |
| ----------- | --------------------------------------------------------------------------- |
| `params.ts` | `feeParams`: the priors of `src/params/fees.json`, the flags, the constants |
| `hazard.ts` | `acceptHazard`, the clock factors and the time slices                       |
| `extras.ts` | `featuresOf`, `feeExtra`                                                    |
| `supply.ts` | `supply`, `fewDriversNear`                                                  |
| `plan.ts`   | `planFees`, `costOf`, `lambdaOf`, `muOf`                                    |
| `learn.ts`  | `learn`, `replay`                                                           |
| `state.ts`  | `FeeState`, `newFeeState`: plain JSON                                       |

## The functions

**`acceptHazard(fee, leadMinutes, seen, state, params)`**: bookings per open daytime hour. `fee` is over the
expected fee (typical × extras). Prior: the table in `fees.json`, by fee (linear between points, flat above 2.5),
by band of hours to the last pickup (under 3, 3–12, 12–24, 24 or more), fresh or seen. A gig is fresh in its
first daytime hour after the post; a repost, a retry or a gig after a drop is seen. At night (23:00–07:00) the
hazard is 0.30 of the daytime one, at the weekend 0.24. Learns: one scale each for fresh and seen, bookings seen
over bookings the prior expected for the same open hours, from 10 expected bookings at the prior, clamped to
0.33–3.

**`feeExtra(features, state, params)`**: the product of one multiplier for each feature of the gig: private
pickup, private delivery, trade-in, premium, due after Friday, posted on Friday, few drivers near the delivery
(under half the drivers within 30 km of the world's median place). Prior: 1 each; `measuredExtras` starts them
at the measured values instead. Learns: at each booking, `g` = fee paid over the fee the plan expected; each
feature of the gig moves by `exp(0.05 × (g / mean g − 1))`, against a running mean of `g` over every gig, so a
world that is dear everywhere moves no feature. Clamped to 0.8–1.6.

**`supply(region, drivers, map)`**: drivers who live within 30 km of a place, in a straight line, from
`GET /drivers`. Counted once per driver list. Learns nothing.

**`planFees(gig, now, state, params)`**: the schedule and `{ feeCents, lateCents, costCents, bookShare,
paidIfBookedCents }`. A gig is open from now to its last pickup, in hour slices; each slice books at the hazard
of its fee, and a booking holds unless dropped (the learned drop share, prior 13.7%). A car without a driver at
the last pickup pays the late fee (1.79 × the expected fee, what late orders paid) and refunds of 0.433 × its
price (the mean of `RULES.md`'s steps over the late orders of `dispatch.py`'s weeks, an undelivered car counted at
three prices) times `mu`. The search is a dynamic programme over (slice, fee, raises left): the least expected
cost over schedules that open at one fee of the grid 0.75–2.5 × the expected fee, raise at most twice, and are at
least 1.5 × by 6 hours before the last pickup (22:00 the evening before when that falls at night). No fee goes
above three times the price. The grid starts at the fee probe's median, 0.76: the cheapest driver of an idle
market. `costCents` is `(feeCents + lateCents) × lambda`. The same call gives `c` for a request (its option's
price and estimated last pickup), and the schedule of a won order, a retry, a repost (`seen: true`) and after the
deadline warning (seen, under 3 hours: it opens at the top). Past the last pickup, it is one step at the late fee.
At level 1 it is one step. About 0.2 ms a call.

**`lambdaOf(gig, state, params)`** (Design 3): one multiplier for each pickup region and day of the last pickup,
times one for experienced drivers. `lambda × exp(0.1 × (g − 1))` at each booking, with `g` the fee paid over the
fee expected, and `g` = 1.5 at a deadline warning. A day not seen yet starts from the region's latest value.
Clamped to 0.8–1.6. It scales `c` only: the fees follow the hazard scale and the extras.

**`muOf(state, params)`** (Design 4): `mu × exp(0.02 × (late share / 5% − 1))` at each delivery, late refund and
deadline warning. The projected late share counts late orders and half of the warned orders that no driver
holds, from 20 orders at 5%. Clamped to 0.5–2.

## Learning: `learn(state, event, params)`

`learn` folds one event into the state, in place, and returns it; `replay(events, params)` folds a whole log
from `newFeeState`. The state is plain JSON (a week is about 130 kB), so it can be saved and rebuilt.

| Event                                                      | Form                                                   | Teaches                                  |
| ---------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------- |
| `gig_posted`                                               | ours: `{ at, gigId, orderIds, gig: FeeGig, schedule }` | starts following the gig                 |
| `gig_repriced`                                             | ours: `{ at, gigId, schedule }`                        | the new schedule                         |
| `gig_withdrawn`                                            | ours: `{ at, gigId }`                                  | the gig's open hours                     |
| `gig_booked`                                               | kit                                                    | hazard, extras, `lambda`                 |
| `gig_dropped`, `no_show`                                   | kit                                                    | the drop share; the gig is open and seen |
| `gig_expired`, `order_cancelled`                           | kit                                                    | the gig's open hours                     |
| `deadline_close`                                           | kit                                                    | `lambda` (g = 1.5), `mu`                 |
| `ledger` (`revenue`, `late_refund`, `undelivered_penalty`) | kit                                                    | `mu`                                     |

Post the events for gigs the world accepted, with the `FeeGig` used to plan them. Views are not needed: the fresh
hour is timed from the post, as `planFees` assumes, since most views come in the first minutes.

## Flags

`feeParams(level, flags)`: `solver` (false: the fixed ramp of `src/dispatch.ts`, its cost still from the model),
`extras`, `measuredExtras`, `capacity` (`lambda`), `onTime` (`mu`), and `cold`: every prior neutral (one hazard
rising from 0.5 × typical for every lead and state, no night, weekend, feature or drop effect, a late car at the
2–24 hour refund and 2.5 × typical). The learners then fit the week from nothing.

## The priors

`uv run python -m analysis.priors_fees` (`analysis/priors_fees.py`) writes `src/params/fees.json` from
`out/spread.sqlite`. The hazard comes from the explore weeks only, whose fees were drawn at random: in
`dispatch.py`'s weeks a gig open at a high fee is a hard one (finding 8). Thin cells lean on their fee's rate over
all lead bands (10 open hours), and each row is made non-decreasing in the fee, so a raise never lowers the hazard;
the top of the seen rows is flat for that reason, not because drivers do not care. Rates, extras and lateness come
from `dispatch.py`'s 165 level-8 weeks.

## Offline comparison

On 32,759 plain single-car first gigs of `dispatch.py`'s saved weeks with 24 hours or more to the last pickup,
with the priors (no learning yet):

| Schedule                     | Opening, mean (p10–p90) | Expected fee / typical | `c` / typical | No driver by last pickup |
| ---------------------------- | ----------------------- | ---------------------- | ------------- | ------------------------ |
| `planFees`                   | 0.76 (0.75–0.80)        | 0.85                   | 0.86          | 1.0%                     |
| `planFees`, `solver: false`  | 1.00                    | 1.12                   | 1.12          | 0.1%                     |
| `dispatch.py`'s own schedule | 1.01 (0.90–1.10)        | 1.13 (model)           |               |                          |
| `dispatch.py`, booked        |                         | 1.12 (paid)            |               |                          |

The brief's 1.21 × typical is over every gig; on these plain, early gigs `dispatch.py` paid 1.12. A typical
schedule for a car 26 hours ahead opens at 0.85, rises to 0.95 in the evening and to 1.5 at 22:00 before the
pickup day. The model prices the schedules that were played about right: expected against paid, `dispatch.py`
1.13 against 1.12, explore-flat 1.08 against 1.06, explore-win 1.20 against 1.19, explore-slow 1.14 against 1.20
(47 small raises teach drivers to wait). It is optimistic on flat fees of 0.8–1.0 (it expects 95–99% booked,
77–89% of those gigs were done), which is why the schedule must reach 1.5 well before the pickup.
`dispatch.py`'s weeks book faster than the explore table expects (1.20 times fresh, 1.36 seen), which the hazard
scale learns within the week: a replayed week ends at 1.65 and 1.92.
