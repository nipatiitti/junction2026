# Ceiling pricing

A copy of our dispatch system whose quotes are as high as we still win, never above our maximum and never below
what the driver will likely cost us. Issue #64. It copies the root `dispatch.py` of `main` at commit `74f0de6` and
builds on `strategies/pricing` and `strategies/admission`. Those and the root `dispatch.py` stay as they are.

| File           | What it holds                                                                                        |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| `dispatch.py`  | A copy of the root `dispatch.py` that quotes with the two strategies below                           |
| `pricing.py`   | `CeilingPricing`: the adaptive quoting of `strategies/pricing`, under the maximum and over the floor |
| `admission.py` | `ChainAdmission`: the admission control of `strategies/admission`, with a timed return leg           |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/ceiling/dispatch.py --level 8 --seed spread-1                         # a practice week
uv run python -m strategies.bench strategies/ceiling/dispatch.py dispatch.py --jobs 4   # against the root system
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `ceiling` instead of `dispatch`, so
they form their own group in `out/spread.sqlite`.

## The strategy

1. **The maximum.** We quote at most the list price × (1 + `max_markup`). At level 8 the competitor quotes about 40%
   over the list price, so `max_markup` is 0.39: just under it. Every price starts at the maximum, at every level
   from 4. Two rules of the game lift it: see [Where the maximum is lifted](#where-the-maximum-is-lifted).
2. **Down after a loss, up after a win.** A lost quote lowers the price and a won quote raises it again, never above
   the maximum. A win at the maximum moves nothing, so wins there do not pile up above it. A request's estimate can
   still sit above the maximum, after wins on other requests that share its pickup, delivery or dealer. Then it
   takes more than one loss to bring its price under the maximum.
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

Up to level 3 every quote wins the first option at its list price. There the desk quotes only when admission picked
the first option, and sends no quote otherwise.

### Where the maximum is lifted

The rules let a dealer accept more from us than the competitor's price in two places. There the learned price and
the maximum are both multiplied by the lift (`CeilingPricing.uplift`):

- for a dealer who trusts us at level 8: 1% for each order on time, up to ×1.25;
- in the outage region during the outage, where dealers turn to a backup that costs about 30% more: ×1.2 when we
  flag the outage, learning up to ×1.5.

So a quote can reach about 2.6 × the list price, not only 1.39 ×. The maximum stays just under what the dealer would
otherwise pay, not at a flat 39% over the list price.

## The variables

`CeilingParams` in `pricing.py` holds the two new ones, next to those it takes from `strategies/pricing`.

| Variable       | Default | What it does                                                                              |
| -------------- | ------- | ----------------------------------------------------------------------------------------- |
| `max_markup`   | 0.39    | The maximum and the starting price: the list price × (1 + `max_markup`), before the lift  |
| `risk_premium` | 0.10    | The floor: the driver cost × (1 + `risk_premium`). Above the maximum, we decline          |
| `target_win`   | 0.5     | The share of quotes the price settles to win                                              |
| `step`         | 0.03    | The world's step per outcome, in logs: a loss lowers the price 1.5%, a win raises it 1.5% |
| `key_step`     | 0.015   | The same for each pickup, delivery and dealer offset: 0.75% per outcome                   |
| `floor`        | 0.9     | The learned multiplier never falls below 0.9 × the list price                             |

`ChainParams` in `admission.py` holds the return leg's: `near`, `wait`, `back` and `spare` (see
[The return leg](#the-return-leg)), next to the thresholds of `strategies/admission`.

Why 10%: in the saved level 8 week of the starter (`smoke-1` in `data/scrape/starter`), 31% of the orders had a
driver drop the gig at least once. Those orders paid 1.94 times their typical fee in driver fees, against 1.57 for
the others: 24% more. In plain euros the gap is only 4%, because drops are commoner on cheap lanes. The cost
estimate scales with the typical fee, so the 24% is the figure that counts. Failed visits, waiting and releases added
1.5% of the fees. Together that is about 9% on top of the fee of a gig that goes well. On the saved level 8 requests (`smoke-1` and `smoke-2`), the driver
cost plus 10% is above 1.39 × the list price for 35% of the requests, and its median is 1.28 × the list price.

## How the price is learned

As in `strategies/pricing`: the price of each option is `list price × m`, with
`m = exp(world + pickup + delivery + dealer)`, one log multiplier for the world and an offset for the pickup place,
the delivery place and the dealer. `m` stays between `floor` and the maximum, and each offset within ±25%. An outcome
moves the world estimate by `step × (won − target_win)` and each offset by `key_step × (won − target_win)`, except
that a win at the maximum and a loss at the floor move nothing. Every step fades the older results, so the price
follows the competitor when it moves. The price war, the outage and dealer trust work as described in
`strategies/pricing/README.md`; during the war the price follows the competitor down, but never below the floor.

When we flag the outage, what the outcomes in its region moved today is taken back, in one step for each estimate.
Each outcome keeps the step it really made, which the maximum may have cut. So the world estimate ends where the
region's outcomes would have left it, on every lane. Taken back one outcome at a time, as in `strategies/pricing`,
the maximum would cut the undo of each loss while the world estimate is at the top, and every lane would end lower.

In a world where the competitor is far above our maximum, we win most quotes everywhere, so a run of wins in one
region can be flagged as the outage when there is none. The undo then lowers the world estimate by what that
region's wins added that day, and the region's boost falls with the losses it brings.

## The return leg

`ChainAdmission` answers admission's return leg question (`pairs`) with a timed check. The request's car is a return
leg of one of our orders that is not delivered yet, with or without a driver, when:

- the order's last delivery is within 30 road minutes of where the car waits (`near`);
- its driver gets there, from the order's pickup window or now, plus its drive, at most 2 hours before the car is
  ready (`wait`) and before the car's pickup window ends;
- they can deliver the request's cars an hour (`spare`) before its earliest deadline;
- the request's last delivery is within 60 road minutes of the order's first pickup (`back`), close to where the
  order's driver set out. This tests how near the car ends, not which way it goes: in the Helsinki area, where
  places are 25 to 35 road minutes apart, a car that ends a little past that pickup counts too;
- a premium car needs a premium order, whose driver is experienced.

Orders that a driver holds come first. Each order carries one return leg: the request that admission accepts claims
it until that request is lost, or its own order is delivered or late. A request that the desk declines after
admission took it (no price fits, or the note's deadline passes before the car is ready) frees its order at once,
and its place in the area too (`release`). A return leg takes half a place in the area's capacity and costs 0.85 of
the usual driver cost, as in `strategies/admission`.

After a restart in the final, the new desk rebuilds its orders from the history, but not the claims. `restore`
claims them again: each request we won and still hold is checked again, in the order they came, at the minute it
came, against the orders won before it as far as they were delivered then. The drivers who hold the orders are
today's, so it comes close, not exact.

The 0.85 assumes that the order's driver takes the car back. In the five weeks of the first bench, that happened for
14 of the 526 return legs we won, and the return legs paid the same driver fees as other cars. Issue #154 is to make
the saving real or to stop counting it.

## Bench

The bench of this version, against the root `dispatch.py` of `main` at `74f0de6` on `spread-1` to `spread-5` at
level 8, is running. Its results follow in this PR.
