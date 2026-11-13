# The ratchet system

A dispatch system with one pricing strategy for both sides of an order (issue #70):

- **Quotes** stay just under the competitor. Each dealer's price starts at a maximum markup, falls only after we lose a
  quote to that dealer, and climbs back towards the maximum after each win. It never goes under the cost floor.
- **Small losses buy trust.** At level 8 each order delivered on time raises the prices its dealer accepts from us by
  1%, so a dealer whose trust can still grow may take an order at a small loss.
- **Driver fees** are one flat fee per gig, priced by the distance, the place and the probability that no driver
  comes there. The fee does not rise while the car can still be on time, so drivers do not learn to wait for raises.
- **Every car moves.** Once a car is late, its fee rises every daytime hour until a driver takes it.

Its three strategies are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)), each of the root
strategy it builds on, with the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.
`dispatch.py` builds them in place of the root desk's admission, pricing and fees and puts them in `Desk.strategies`,
so the desk feeds them every event like the others. It also replaces the desk's quote, the fee of a bundle, and its
answers to a deadline warning and a drop. Everything else (the loop, posting, bundling, notes, retries, direct
offers, the final) is the root system's, so improvements there reach this system too. The root `dispatch.py` and the
other folders of `strategies/` stay as they are.

| File           | Class            | Builds on              | What it decides                                              |
| -------------- | ---------------- | ---------------------- | ------------------------------------------------------------ |
| `pricing.py`   | `RatchetPricing` | `PricingModel`         | The price ratchet per dealer, with the parent's dealer trust |
| `admission.py` | `TrustAdmission` | `Admission`            | Capacity, time and option as the parent; the floor and trust |
| `fees.py`      | `RiskFees`       | `FeePlanner`           | The flat fee, its late raises, and the risk of no driver     |
| `risk.py`      | `Risk`           | (a helper of the fees) | The probability that a gig finds no driver, place by place   |
| `dispatch.py`  | `Desk`           | the root `Desk`        | The system: the root desk with the three strategies above    |

## Run it

From the repository root, like the root `dispatch.py`, with the same options (`--level`, `--seed`, `--board`,
`--final`):

```sh
uv run strategies/ratchet/dispatch.py --level 8 --seed spread-1                         # a practice week
uv run python -m strategies.bench strategies/ratchet/dispatch.py dispatch.py --jobs 3   # against the root system
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `ratchet` instead of `dispatch`, so
they form their own group in `out/spread.sqlite`.

## Quotes: a ratchet per dealer

- Each dealer has its own multiplier on the list price. The price of an option is `list price × multiplier`, times
  `1 + trust / 100` at level 8 (trust below).
- The multiplier starts at the maximum, `1 + max_markup` (1.39). The competitor quotes 26% to 54% above the list
  price at level 8.
- It falls only after we lose a quote to that dealer, by `cut` (4%). Nothing else lowers it.
- After each win it moves `recover` (30%) of the way back to the maximum.
- Each new day moves every multiplier `daily_recover` (30%) of the way back to the maximum: the competitor's day
  factor is new every day, and a price that the price war cut comes back.
- A dealer we have not quoted yet starts from the world's multiplier, which learns from every dealer's outcomes the
  same way. At the start of the week that is the maximum.

There is no price war or outage logic: the ratchet follows the war down with its losses, and the next day's recovery
brings the price back. In an outage region the maximum still caps the price.

## The floor and the trust losses

Admission (`strategies/admission`) still decides capacity, time and the option to quote. Instead of its profit check
it gives a floor: the least price at which the cars are worth moving, `cost / (1 − margin)`. The cost is admission's
expected driver cost, never under the opening fee that `fees.py` would post. The margin is `min_margin` (0): the
floor is the cost.

When the dealer's price is under the floor, we quote the floor instead of declining: it may still win where the
competitor is dearer, and a quote that loses costs nothing. A loss at the floor says nothing about the dealer's price,
so it does not lower it; a win moves it up as usual.

At level 8, while a dealer counts fewer than 25 orders on time (`trust_cap`) and has sent us at least 5 requests
(`trust_requests`), its margin is `−trust_loss`: we take its requests at a loss of up to 10% of the price. Each order
delivered on time adds 1% to the prices that dealer accepts from us on its later orders. A dealer that sends few
requests has little later business to repay the loss.

Trust is counted from the ledger as in `strategies/pricing`: a revenue line with no late refund is an order on time,
and a late refund or an undelivered penalty halves the count.

## Driver fees: flat, then raised once late

### The opening fee

The typical fee, times a multiple for the distance, the place and the hour, times the risk premium:

1. **Distance.** The typical fee already grows with the distance: it is the drive, the trip to the pickup and the
   trip home of a driver who lives in the pickup town. After a change of plan the typical fee is that of the trip the
   car makes now (`FeePlanner.typical` of `strategies/fees`), not the request's. On top: 10% for each hour of road from the homes of the
   pickup's 10 nearest drivers (up to 4 hours), their trip to the car, and 5% for a drive of 3 hours or more.
2. **Place and hour.** Up to 15% at a delivery with no drivers within reach (a long trip home), 10% when the drive
   ends after 18:00, and 15% for Saturday work.
3. **Risk of no driver.** Times `1 + RISK_WEIGHT × risk`, where `risk` is the probability that no driver books a gig
   at the pickup before its deadline warning. With `RISK_WEIGHT` 0.5, a fee where half of our gigs find nobody in
   time opens 25% higher.

The opening fee is set at the order's first post and kept for every later post, repost and retry of the order, so
the fee never rises before the car is late. A car that the dealer sends to another place is a new trip with a new
opening fee. The opening fee is at most 1.5 times the order's price for the gig's cars, or the typical fee of the trip
when that is higher.

A bundle of several orders' cars (`strategies/bundling`) gets the same flat fee, from the typical fee and price that
bundling sums for it, its first pickup and its last delivery.

### The risk of no driver

`risk.py` keeps, for each pickup place, the orders whose gig a driver booked before the deadline warning and the
orders that reached the warning with no driver. Each order counts once, at whichever came first. The risk is the share
that found no driver, with a prior that counts as 5 orders: 0.15 at a place with as many drivers within reach as the
world's median place, rising to 1 at a place with none (from the driver list and the map). So the fee opens higher
where drivers are scarce from the start, and our own gigs correct it during the week.

### Late: raise until a driver comes

From `lastPickupAt` (moved by `LATE_FROM` minutes), every daytime hour adds 25% of the opening fee (`LATE_RAISE`), up
to twice the order's price for the gig's cars (`LATE_CEILING`, the penalty for a car never delivered) or three times
the typical fee of the trip (`LATE_TYPICAL`), whichever is higher: a car that the dealer sent far must move too.
There is no raise from 23:00 to 07:00 or on Sunday, when no driver books. A gig posted again after `gig_expired`
starts at the fee that its lateness has reached and keeps rising.

At the deadline warning the fee stays as it is: the schedule already holds the late raises, and the desk sends direct
offers to drivers near the pickup instead. As in the root system, an order still waiting for a bundle goes alone
then, and a bundle that no driver holds is split into one gig for each order, at its own flat fee. After a drop the
schedule in the app stays.

## Variables

| Variable          | File           | Default | What it does                                                         |
| ----------------- | -------------- | ------- | -------------------------------------------------------------------- |
| `max_markup`      | `pricing.py`   | 0.39    | The highest price is the list price plus this share, before trust    |
| `cut`             | `pricing.py`   | 0.04    | A lost quote lowers its dealer's multiplier by this share            |
| `recover`         | `pricing.py`   | 0.3     | A won quote moves it this share of the way back to the maximum       |
| `daily_recover`   | `pricing.py`   | 0.3     | Each new day moves every multiplier this share back; 0 turns it off  |
| `trust_loss`      | `admission.py` | 0.10    | Level 8: the loss, as a share of the price, that trust may buy       |
| `trust_requests`  | `admission.py` | 5       | The requests a dealer must have sent before it gets the trust loss   |
| `min_margin`      | `admission.py` | 0.0     | The margin the floor asks otherwise                                  |
| `RISK_WEIGHT`     | `fees.py`      | 0.5     | The opening fee rises by this times the probability of no driver     |
| `RISK_BASE`       | `risk.py`      | 0.15    | The prior risk at a place with as many drivers near as the median    |
| `RISK_PRIOR`      | `risk.py`      | 5       | The prior counts as this many orders                                 |
| `OPEN_TRAVEL`     | `fees.py`      | 0.10    | Per hour of road from the nearest drivers' homes to the pickup       |
| `OPEN_SCARCE_END` | `fees.py`      | 0.15    | At a delivery with no drivers within reach                           |
| `OPEN_CEILING`    | `fees.py`      | 1.5     | The opening fee is at most this times the price, or the typical fee  |
| `LATE_FROM`       | `fees.py`      | 0       | Minutes after `lastPickupAt` when the raises start; negative: before |
| `LATE_RAISE`      | `fees.py`      | 0.25    | Each daytime hour late adds this times the opening fee               |
| `LATE_CEILING`    | `fees.py`      | 2.0     | The late fee may reach this times the price for the gig's cars       |
| `LATE_TYPICAL`    | `fees.py`      | 3.0     | ... or this times the typical fee of the trip, whichever is higher   |

`max_markup`, `cut`, `recover` and `daily_recover` are fields of `RatchetParams`, and `trust_loss`, `trust_requests`
and `min_margin` of `TrustParams`; the fee and risk constants are at the top of their files.

A smaller `cut` or a larger `recover` gives higher prices and fewer wins. On a synthetic competitor with a lane spread
of 10%, the defaults win about 57% of the quotes at 98% of the best profit per request of the settings tried.

## Bench

Level 8, seeds `spread-1` to `spread-5`, the defaults above against the root `dispatch.py` of 13 November (main at
`6b4f7ce`). Every week is saved in `data/scrape/runs/L8/`.

| Seed      | Ratchet margin | Orders | On time |    Root margin | Orders | On time |
| --------- | -------------: | -----: | ------: | -------------: | -----: | ------: |
| spread-1  |      €4,454.88 |    425 |   88.5% |      €7,738.40 |    379 |   97.9% |
| spread-2  |      €4,226.69 |    351 |   94.6% |      €4,577.46 |    360 |   98.1% |
| spread-3  |       −€514.51 |    255 |   92.5% |      €2,760.04 |    300 |   99.0% |
| spread-4  |      €1,199.75 |    312 |   90.7% |      €6,707.48 |    360 |   95.6% |
| spread-5  |      €2,210.29 |    353 |   91.5% |      €4,745.99 |    326 |   96.3% |
| **Total** | **€11,577.10** |  1,696 |   91.4% | **€26,529.37** |  1,725 |   97.3% |

With these defaults the ratchet system makes less than the root system on every seed, and `spread-1` is not ranked
(under 90% on time). What the weeks show:

- **Flat fees overpay the easy gigs and underpay the hard ones.** Our opening fee is 1.06 to 1.36 times the typical
  fee (median 1.12), and 97% of our gigs book at it. The root system opens at the typical fee, books 66% of its gigs
  there, and raises the rest to 1.2 to 1.7 times before `lastPickupAt`. Driver fees per delivered car are €78 to €103
  against €64 to €84.
- **Waiting until the car is late makes more cars late.** 6.9% of our gigs were booked only after `lastPickupAt`
  (root 1.5%), 6% to 12% of our orders got a deadline warning (root 2% to 4%), and late refunds were €613 to €1,766 a
  week (root €32 to €572). Late orders also halve the dealers' trust.
- **The maximum is low for the dearer worlds.** The root system won at 1.51 times the list price on `spread-1` and
  1.42 on `spread-4`; capped at 1.39, we won at 1.41 and 1.37.
- **A change of destination keeps the fee of the old trip.** On `spread-4`, order `R00081` (Turku to Raisio, 8 road
  minutes) was sent to Vaasa. Its fee stayed priced from the request's typical fee of €12.03 and reached only twice the
  price (€59.08), so no driver took it and it was never delivered. The root system has the same gap (#94).

Since then the system plans fees from the trip after a change of destination, plays with bundling, and its parts are
`Strategy` subclasses. On main of 13 November evening, `spread-1` played to its end at €5,173.02, 422 orders, 90.5% on
time and none undelivered (ranked). Next: bench the variables that the weeks point at: a higher `max_markup` (0.55),
raises from the deadline warning (`LATE_FROM` −180) and a cheaper opening fee.
