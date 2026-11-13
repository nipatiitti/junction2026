# Admission control

Decides, before we quote, whether to take a price request: decline the cars we cannot move on time or at a
profit, and pick the delivery option to quote. Issue #14.

At levels 7 and 8 there are about a third of the usual drivers. The starter wins every car it can and ends at
44–60% on time at level 8, far under the 90% delivery minimum. Winning bad orders also uses up the drivers that
the good orders need.

## How it is used

`dispatch.py` loads the driver list (`world.roster()`) and the map (`client.map()`) once when the desk starts,
feeds every event to `Admission.observe`, and asks `Admission.assess(request, held, now)` in `Desk.quote`.
`held` is our orders, each with whether a driver holds all its undelivered cars now.

`assess` returns a `Verdict`:

- `accept` and `options`: the option kinds to quote. The desk quotes their list price.
- `expected_cost`: what we expect to pay drivers, in cents. The pricing logic (#13) can add its margin to it.
- `score`: the expected margin over the price; `reason` says why a request was declined.

A declined request gets a quote at ten times the list price, which loses at no cost. Up to level 3 every quote
wins, so there a declined request gets no quote.

The scoring needs no network, so it is tested offline on a hand-made map and roster.

## The score

For a request whose first car waits at place `P` on day `D`:

1. **Driver supply near the pickup.** Each driver counts `exp(-road minutes from home to P / 45)`. A premium
   car counts only experienced drivers (rating ≥ 4.8 and ≥ 50 gigs). During the week, a town's drivers count
   less as they drop our gigs: `(bookings + 2) / (bookings + 2 × drops + 2)`. The area's supply is divided by
   its stress, `1 + 2 × deadline warnings / (orders won there + 3)`.
2. **Load we already hold.** The orders that still wait for a driver, picked up within 60 road minutes of `P`
   on day `D`, plus the requests we have just quoted to take there and not heard back on. A return leg
   counts as half a car.
3. **Capacity.** `max(1, 0.10 × supply) × tightening`. When load + this car is over it, we decline.
4. **Time.** For each option, the slack is its deadline less the ready time (at least an hour from now) and the
   drive. Options with less than 5 hours of slack are out. We quote the earliest option with 9 hours of slack,
   else the one with the most. Both limits widen as admission tightens.
5. **Expected cost.** The typical fee × 1.15 (levels 7–8; 1.0 below), × `1 + 1.2 × exp(-supply at P / 15)`,
   × `1 + 0.5 × exp(-supply at the delivery / 15)`, × 1.15 for an evening pickup, × 1.15 on a weekend,
   × 1.1 for a private address, × 1.05 for a note that adds risk, × 0.85 for a return leg.
6. **Profit.** We decline when the expected cost is above the price we quote: the list price × `price_factor`
   (1.0 while we quote the list price).

**Tightening.** Our running on-time share counts delivered orders and orders past their deadline. An order
without a driver after its deadline warning counts as half late. It starts at 95% with the weight of 10 orders.
At 95% or more, the capacity is whole; it falls linearly to a quarter at 90%.

All thresholds are in `Params`.

## Signs of a good request

- **Towards towns where drivers live**: the supply at the delivery lowers the expected cost.
- **Pairs with an order we hold**: a car waiting where one of our cars arrives that day is a return leg. It
  costs less and takes half a place in the area's capacity.
- **A later option**: when the first option leaves too little time, we quote a later one.

Not used yet: views (`gig_viewed`). A view shows that a driver uses the app, not that they work today or that a
gig suits them, so it says little about capacity.

## Bench

Seeds `spread-1` to `spread-5`, level 8. The starter is `dispatch.py` on `main`.

| Seed      |   Starter margin | Starter orders | Starter on time | Admission margin | Admission orders | Admission on time |
| --------- | ---------------: | -------------: | --------------: | ---------------: | ---------------: | ----------------: |
| spread-1  |      -€72,612.51 |            949 |           45.5% |          -€94.87 |              339 |             95.9% |
| spread-2  |      -€46,907.28 |            785 |           55.9% |          €291.92 |              335 |             97.0% |
| spread-3  |      -€55,436.36 |            735 |           60.0% |         -€198.53 |              303 |             96.7% |
| spread-4  |      -€98,182.67 |            930 |           44.2% |         -€285.29 |              306 |             97.1% |
| spread-5  |      -€61,640.24 |            819 |           57.6% |         -€535.81 |              315 |             94.6% |
| **Total** | **-€334,779.06** |          4,218 |   0 of 5 ranked |     **-€822.58** |            1,598 |     5 of 5 ranked |

Every week is now ranked. The margin is near zero because we still quote the list price, which only just pays the
drivers in a shortage: on the starter's spread-1 week, the orders delivered on time cost 1.02 times their price in
driver fees. The competitor quotes 26% to 54% above the list price at level 8, so the pricing logic (#13) can raise
`price_factor` and add its margin to `expected_cost`. With higher prices, admission takes more requests, because
the profit check is the filter that declines most of them now.
