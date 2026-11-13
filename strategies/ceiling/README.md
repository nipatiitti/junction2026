# Ceiling pricing

A copy of our dispatch system whose quotes are as high as we still win, never above our maximum and never below
what the driver will likely cost us. Issue #64. The root `dispatch.py`, `strategies/pricing` and
`strategies/admission` stay as they are: this folder builds on them.

| File           | What it holds                                                                                        |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| `dispatch.py`  | A copy of the root `dispatch.py` that quotes with the two classes below                              |
| `pricing.py`   | `CeilingPricing`: the adaptive quoting of `strategies/pricing`, under the maximum and over the floor |
| `admission.py` | `ChainAdmission`: the admission control of `strategies/admission`, with a timed return leg           |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/ceiling/dispatch.py --level 8 --seed spread-1                         # a practice week
uv run python -m strategies.bench strategies/ceiling/dispatch.py dispatch.py --jobs 4   # against the root system
```

Its weeks are saved like the root system's (`record.py`), with the policy `ceiling` instead of `dispatch`, so they
form their own group in `out/spread.sqlite` and `summary.json`.

## The strategy

1. **The maximum.** We quote at most the list price × (1 + `max_markup`). At level 8 the competitor quotes about 40%
   over the list price, so `max_markup` is 0.39: just under it. Every price starts at the maximum, at every level
   from 4.
2. **Down after a loss, up after a win.** A lost quote lowers the price and a won quote raises it again, never above
   the maximum. A win at the maximum leaves the price there, so the first loss brings it down at once.
3. **Never below the driver cost.** The floor is admission's expected driver cost × (1 + `risk_premium`). The
   premium pays for a driver who drops the gig and has to be replaced at a higher fee, failed visits, waiting and
   late cars, so that an order does not end at a loss. When the learned price is below the floor, we quote the
   floor. A loss there does not lower the learned price: our cost lost that request, not our price.
4. **Decline what does not pay.** When the floor is above the maximum, we decline: the desk quotes ten times the
   list price, which loses at no cost. Admission makes this check (the desk gives it the maximum as `price_factor`
   and `1 − 1 / (1 + risk_premium)` as `min_margin`), so a request it takes always has a price.
5. **Return legs cost less.** When one of our transports ends where the car waits, in time for its driver to
   collect the car and drive it back, the driver cost is 0.85 of the usual estimate (admission's return leg). Each
   transport lowers the cost of one request. See [The return leg](#the-return-leg).

The rules lift the maximum in two places, where the dealer accepts more from us than the competitor's price: in the
outage region during the outage (the backup costs about 30% more), and for a dealer who trusts us at level 8 (1% for
each order on time). There the learned price and the maximum are both multiplied by the lift.

## The variables

`CeilingParams` in `pricing.py` holds the two new ones, next to those it takes from `strategies/pricing`.

| Variable       | Default | What it does                                                                              |
| -------------- | ------- | ----------------------------------------------------------------------------------------- |
| `max_markup`   | 0.39    | The maximum and the starting price: the list price × (1 + `max_markup`)                   |
| `risk_premium` | 0.10    | The floor: the driver cost × (1 + `risk_premium`). Above the maximum, we decline          |
| `target_win`   | 0.5     | The share of quotes the price settles to win                                              |
| `step`         | 0.03    | The world's step per outcome, in logs: a loss lowers the price 1.5%, a win raises it 1.5% |
| `key_step`     | 0.015   | The same for each pickup, delivery and dealer offset: 0.75% per outcome                   |
| `floor`        | 0.9     | The learned multiplier never falls below 0.9 × the list price                             |

Why 10%: in the saved level 8 week of the starter (`smoke-1` in `data/scrape/starter`), 31% of the orders had a
driver drop the gig at least once, and those orders paid 24% more in driver fees than the others. Failed visits,
waiting and releases added 1.5% of the fees. Together that is about 9% on top of the fee of a gig that goes well.
On the saved level 8 requests (`smoke-1` and `smoke-2`), the driver cost plus 10% is above 1.39 × the list price for
35% of the requests, and its median is 1.28 × the list price.

## How the price is learned

As in `strategies/pricing`: the price of each option is `list price × m`, with
`m = exp(world + pickup + delivery + dealer)`, one log multiplier for the world and an offset for the pickup place,
the delivery place and the dealer. `m` stays between `floor` and the maximum, and each offset within ±25%. An outcome
moves the world estimate by `step × (won − target_win)` and each offset by `key_step × (won − target_win)`, except
that a win at the maximum and a loss at the floor move nothing. Every step fades the older results, so the price
follows the competitor when it moves. The price war, the outage and dealer trust work as described in
`strategies/pricing/README.md`; during the war the price follows the competitor down, but never below the floor.

In a world where the competitor is far above our maximum, we win most quotes everywhere, so a run of wins in one
region can be flagged as the outage when there is none. Its boost then falls with the losses it brings.

## The return leg

`ChainAdmission` answers admission's return leg question (`pairs`) with a timed check. The request's car is a return
leg of one of our orders that is not delivered yet, with or without a driver, when:

- the order's last delivery is within 30 road minutes of where the car waits (`ReturnLeg.near`);
- its driver gets there, from the order's pickup window or now, plus its drive, at most 2 hours before the car is
  ready (`wait`) and before the car's pickup window ends;
- they can deliver the request's cars an hour (`spare`) before its earliest deadline;
- the request's last delivery is within 60 road minutes of the order's first pickup (`back`): the car goes back
  towards where the driver set out, close to their home;
- a premium car needs a premium order, whose driver is experienced.

Orders that a driver holds come first. Each order carries one return leg: the request that admission accepts claims
it until that request is lost, or its own order is delivered or late. A return leg takes half a place in the area's
capacity and costs 0.85 of the usual driver cost, as in `strategies/admission`.

## Bench

Level 8, seeds `spread-1` to `spread-5`, against the root `dispatch.py` of `main` (commit `ce01491`), with
`uv run python -m strategies.bench strategies/ceiling/dispatch.py dispatch.py --jobs 2`. The weeks are saved in
`data/scrape/runs/L8/`: policy `ceiling` for this system, `dispatch` for the root one.

| Seed      | Ceiling margin |    Root margin | Ceiling orders | Root orders | Ceiling on time | Root on time |
| --------- | -------------: | -------------: | -------------: | ----------: | --------------: | -----------: |
| spread-1  |      €8,102.33 |      €7,738.40 |            387 |         379 |           97.7% |        97.9% |
| spread-2  |      €5,880.25 |      €4,577.46 |            332 |         360 |           98.2% |        98.1% |
| spread-3  |      €3,373.67 |      €2,760.04 |            241 |         300 |           99.2% |        99.0% |
| spread-4  |      €7,631.07 |      €6,707.48 |            359 |         360 |           98.1% |        95.6% |
| spread-5  |      €4,785.38 |      €4,745.99 |            319 |         326 |           97.5% |        96.3% |
| **Total** | **€29,772.70** | **€26,529.37** |          1,638 |       1,725 |           98.0% |        97.3% |

Ceiling pricing earns €3,243.33 more in total, more on every seed, and every week of both is ranked. What the saved
weeks show (from `out/spread.sqlite`, all five seeds):

- It wins fewer orders (1,638 against 1,725) at about the same price: the quotes it won averaged 1.37 × the list
  price against 1.36. Revenue per order is €87.81 against €90.24.
- The margin comes from cost: driver fees per delivered car are €68.25 against €73.38, and late refunds and
  penalties €1,260 against €1,809. Here a car is taken only when its driver cost plus 10% fits under the maximum;
  the root system takes a car whose cost fits under its learned price, with no premium.
- Where the competitor is dear, the cap holds the price down: on `spread-1` the root system's quotes that won had a
  median of 1.51 × the list price against 1.42 here (above 1.39 through dealer trust and the outage). It still ends
  ahead there, on cost.
