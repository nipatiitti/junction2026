# Spread (Junction 2026) — brief for the dispatcher core

This brief gives the design of our dispatcher and the measurements behind it.
The goal is a strategy that is generic (no constants tied to one world), robust
(ranked on every world) and learning (it fits the world during the week).

- **Rules.** `docs/spread/RULES.md`, `HANDBOOK.md` and `API.md` are the live
  documents, word for word (checked 14 November). `RULES.md` wins over this
  brief.
- **Data.** Every number below comes from `out/spread.sqlite` on 14 November:
  181 saved weeks, 1,730 quote probes and 289 fee probes. Rebuild it with
  `uv run python -m tools.db && uv run python -m analysis.facts`. `analysis/README.md` lists
  the tables. Level 8 unless a line says otherwise.
- **Code.** Build this design in TypeScript, in `src/`, on the kit in
  `vendor/spread-typescript/`. `src/dispatch.ts` is still a copy of the
  starter that saves its weeks; play it with `pnpm dispatch --level 8 --seed
  spread-1` and check it with `pnpm check` and `pnpm lint`. Keep the solvers
  free of packages. The Python system `dispatch.py`, with its parts in
  `strategies/`, is the reference: its weeks are the `runs` rows below. The
  data tools stay in Python: `tools/probe.py` forks a world to find where a price or
  a fee flips, and `analysis.oracle` reports the gap to hindsight.

## Where we are

| System (level 8)       | Weeks | Margin a week          | Orders won | On time | Ranked   |
| ---------------------- | ----- | ---------------------- | ---------- | ------- | -------- |
| Starter                | 11    | −€68,684               | 914        | 48.4%   | 0 of 11  |
| `dispatch.py` (`runs`) | 35    | +€5,660 (2,760–10,477) | 342        | 97.3%   | 35 of 35 |

A `dispatch.py` week: €31,600 revenue, €25,500 driver fees (81%), €376 refunds
and penalties, about €17 margin an order. It wins 342 of 1,034 requests and
leaves 24 late orders of its allowance unused (13 at least).

## The game in short

- Dealers send about 1,035 requests from Monday 08:00 to Friday 18:00 (228 on
  Monday, 179 on Friday). Each has one to three options (`same_day`,
  `next_day`, `within_3_days`), a list price for each, a typical driver fee,
  and 15 minutes to answer. The requests do not depend on what we do.
- We quote one price for each option we offer. A quote cannot be taken back; to
  decline, quote far above list. A request with no quote costs goodwill.
- The competitor's level is 26–54% above list. On one day it is 20% lower
  everywhere (price war). On another it is down in one region, where a backup
  costs 30% more than it. Each morning it cuts its prices for dealers whose
  requests we mostly won.
- Each won order needs a gig: stops, an audience, and a fee schedule of 1 to 48
  steps that never fall. A gig names its orders, so it cannot exist before the
  order is won. Releasing a booked driver costs 25% of the fee more than 24
  hours before pickup, 50% inside 24 hours and 100% inside 2 hours.
- Score is the account: prices in; fees, refunds (10% up to 2 hours late, 25%
  up to 24 hours, 50% up to two business days, then 100%), fines and penalties
  out. A car undelivered at the end costs twice its price.
- Under 90% of won orders on time, the team is not ranked.
- Trust: each on-time order raises what that dealer accepts by 1%, up to 25
  orders. A late order halves the count.
- The final is one secret level 8 world, live: 18 real seconds per weekday
  hour, so 4.5 seconds per quote; 20 actions and 50 reads a second; `advance`,
  `fork` and `delete` are closed.

## What the data says

Each finding closes a question of the earlier brief.

1. **Drivers are new in every world; dealers are not.** No driver id appears
   in two seeds (41,080 ids in 52 passive weeks), and a town's driver count
   swings widely (Helsinki 39 to 375). So there are no per-driver priors: read
   supply from `GET /drivers` at the start. The 40 dealers `D01`–`D40` are in
   every world with stable volumes: `D01` sends 30% of the requests (25–40%),
   `D02` 12%, the top five 61%.
2. **Both sides answer with thresholds.** Every probe flipped exactly once
   (1,730 quote probes, 289 fee probes). A request has one price under which it
   wins, and a gig one fee over which it books. The threshold differs from
   request to request, so for us the win model is the distribution of flips.
3. **Quote flips, trust 0, Monday and Tuesday** (817 flips, as price / list):
   10% of flips are under 0.98, 25% under 1.15, half under 1.29, 75% under
   1.46, 90% under 1.62. No floor at 1.26 exists, so "quote just under the
   competitor's floor" is not a rule.
   - The world's level: the mean flip of a seed runs from 1.12 to 1.43.
   - The day: a seed's mean can move from 1.17 to 1.61 overnight, or from 1.25
     to 1.00 (a price war).
   - The request: around its world-day mean, a flip scatters by ±16%.
   - The delivery place: cars going to Vantaa, Hyvinkää, Helsinki and Espoo
     flip at 1.13–1.19, to other towns at 1.32–1.42. The rules say this part
     holds in every world.
4. **Options are a ladder, and the dealer pays for speed.** In one request,
   `same_day` flips at 1.21 times the `next_day` price (244 pairs) and
   `next_day` at 1.13 times `within_3_days` (120 pairs), never lower. With
   several options priced, the dealer takes the fastest in 99.5% of wins when
   it costs no more than the cheapest, in 74% at +10%, 49% at +20% and 12% at
   +50% (6,694 wins).
5. **Trust is the largest price lever.** With random prices (explore weeks, one
   option, no war day), a quote at 1.4 × list wins 46% at trust 0 and 95% at
   trust 15 or more; at 1.6 it is 18% and 69%; at 1.8 it is 3% and 50%.
   `dispatch.py` has `D01` at trust 23 by Wednesday, and on Friday 47% of the
   requests come from dealers at 15 or more.
6. **Nothing wins far above the competitor.** At level 6, 13 of 5,315 quotes
   at 1.5 × list or more won, the highest at 1.92. The outage is worth at most
   the backup's 30%, in one region on one day.
7. **A fresh gig books far under the typical fee.** In an untouched world, the
   lowest flat fee that books within 3 hours is 0.76 × typical at the median
   (0.59 at the 10% point, 1.02 at the 90% point); 87% book at or under
   typical, and 5 of 289 never book. It does not depend on the option, the
   size of the fee, or the hours to the pickup (0.73–0.84 from 3 to 48 hours).
8. **The opening fee decides; a raise does little.** `dispatch.py` pays 1.21 ×
   typical. Bookings per open daytime hour, with 24 hours or more to the last
   pickup: 0.04 at 0.5 × typical, 0.19 at 0.75, 0.40 at 1.0, 0.60 at 1.25,
   0.78 at 1.5. With under 3 hours left it stays under 0.19 at any fee. An
   order that drivers have viewed and left books at 0.13 an hour at 1.0 ×
   typical against 0.69 for a fresh one, and at 0.09 against 2.98 at 1.5.
   Opening at 0.65 and rising slowly ended at 1.30 paid; a flat fee near 1.0
   paid 1.14 but was 85% on time. The fee bands are not an experiment: a gig
   still open at a high fee is a hard one.
9. **Drivers care where a gig ends.** On lanes of 100 km or more, bookers who
   live at the delivery place took 1.25 × typical (3,743 gigs), at the pickup
   place 1.30 (6,072), at neither 1.43 (11,982). A gig of two orders paid 1.11
   × its cars' typical fees against 1.22 for one car, but only 3% of gigs
   combine, so bundling moved the margin by −€267 over ten seeds.
10. **Some work costs more.** Paid over typical: plain 1.34, private delivery
    1.48, private pickup 1.53, trade-in 1.77, premium 1.58 (and 776 minutes to
    book against 303; 8% of drivers are experienced). Gigs posted on Friday pay
    1.36 and take 349 minutes to book, against 1.14–1.21 and under 100 minutes
    from Monday to Thursday.
11. **No capacity limit shows yet.** Over 80 weeks that won 186 to 362 orders,
    the booked fee stays at 1.22 × typical. The starter's 914 orders pay 1.67
    and are 48% on time, so the limit lies between. A quarter of the drivers
    book one of our gigs in a week, 1.7 gigs each. 14% of bookings are dropped,
    0.2% are no-shows, and 0.9% of orders are cancelled.
12. **Lateness is not a fine dial.** Of 11,879 counted `dispatch.py` orders, 30 were
    up to 2 hours late, 197 up to 24 hours and 84 up to two business days; 15
    were never delivered. A late order ends about €60 below an on-time one.
13. **Driver cost sets the best price.** On 453 probed requests at trust 0,
    the best single multiplier on list is 1.42 when a car costs 1.21 × typical
    (wins 27%, €6 a request), 1.26 at 1.0 × (53%, €13.50) and 1.18 at 0.8 ×
    (65%, €23). Knowing the world-day level adds €1–2 a request. Pricing every
    request at its flip would double each figure.

Hindsight on `dispatch.py` weeks (`analysis.oracle`, upper bounds, euros a
week): perfect accept or decline +1,035, every order on time +66, the lowest
comparable fee +1,576, every quote at its flip +28,795. The last ignores
capacity and is an estimate.

## Design

One link joins the two sides: the expected cost of moving a car, which includes
a learned price for driver capacity. This is bid-price control, as airlines use
for scarce seats.

1. **Quote.** For each option, take the price `p` on a grid that maximises
   `(p − c) × W(p)`, and decline when the best value is under a minimum.
   `W(p)` is the share of flips at or above `p` (finding 3), scaled by a level
   that the week's wins and losses update, by `1 + trust / 100`, and by the
   option ladder (finding 4). This replaces the present rule, which holds the
   win share at 50% whatever a car costs. Price the fastest option we can serve
   at its own flip and slower ones no lower than it, since the dealer takes
   the fastest at equal price. On a war day `W` shifts down 20%, and the same
   rule then declines what no longer pays.
2. **Fee.** `c` is the expected fee plus the expected lateness cost, from one
   function that also returns the schedule. Open at the fee that maximises the
   expected saving against the top fee, using the hazard of finding 8, and keep
   raises few: a viewed gig rarely books at a higher fee. Scale the fee by one
   learned multiplier for each feature of the gig (private pickup, private
   delivery, trade-in, premium, weekend delivery, drivers living near the
   delivery place). Each starts at 1 and moves with the fees at which such
   gigs book; findings 9 and 10 say which features to track, not what to
   charge. The fee probe's 0.76 is the floor to learn towards, not a value to
   post: it is the cheapest driver of an idle market.
3. **Capacity.** One multiplier for each pickup region and day, and one for
   experienced drivers, updated from what happens, as in dual mirror descent
   (Balseiro, Lu and Mirrokni): `lambda = lambda × exp(eta × (g − rho))`, where
   `g` is the fee paid over the fee expected, or 1 plus a penalty when the gig
   reaches its deadline warning, and `rho` is 1. `lambda` scales `c`. We drop
   the utilisation formula: it needs the hours drivers are free, which the
   world never shows, and no limit shows at our volumes (finding 11).
4. **On time.** A multiplier `mu` on the lateness cost, updated the same way
   from the projected late share against a 5% target. `dispatch.py` sits at
   2.7% late, so `mu` should fall and let the quote side win more orders at
   about €17 each; that is the use for the unused allowance. Spending the
   allowance on planned late deliveries is dropped (finding 12).

## Model interfaces

Each is one function with its start values in `params.json`. Every value is a
prior with an update rule, and none is keyed to a dealer id, a driver id or a
place name: the system must work when all of them are set to neutral.

| Function                         | Returns                       | Starts at                                                 | Learns from                                                    |
| -------------------------------- | ----------------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| `win_prob(price, option, state)` | chance the dealer accepts     | flip quantiles of finding 3 × level 1.30 × trust × ladder | each win (flip above our price) and loss (below)               |
| `lane_offset(drivers_near)`      | the lane's part of the level  | 0, falling with the drivers who live near the delivery    | wins and losses, pooled by the driver count, not by town       |
| `accept_hazard(fee, lead, seen)` | bookings per open hour        | the table of finding 8; a fifth of it once viewed         | each hour a gig stays open or books                            |
| `fee_extra(features)`            | multiplier on the typical fee | 1 for every feature                                       | booked fee over expected fee of gigs with the feature          |
| `dealer_weight(dealer)`          | share of the week's requests  | equal for every dealer                                    | the dealer's share of the requests so far; clear within Monday |
| `supply(region)`                 | drivers who live within 30 km | `GET /drivers`                                            | nothing: it only starts `lambda`, which learns                 |

`dealer_weight` says where trust pays most: one dealer sends about 30% of a
week's requests, and it shows in the first hour. `lane_offset` uses the cause
the handbook gives (few drivers near the delivery place make a lane dear), so
it follows the shortage to wherever a new world puts it.

## Still open

1. Round trips and combined gigs: `probe.py shape` has no rows yet. Run it
   before investing more in bundling.
2. Where capacity runs out between 360 and 900 orders a week. `lambda` finds it
   during a week; a bench with a lower `mu` shows it offline.
3. Quote flips after Tuesday and at trust above 0 (the probes cover neither),
   and how far the competitor cuts for a dealer whose requests we mostly win.
4. Direct offers: no saved week has enough of them to give a per-driver answer.

## Flags

Each idea sits behind a flag, so the bench can show it with and without on the
same seeds: expected-profit pricing or the 50% learner; trust-aware pricing;
option ladder; lane offsets; fee solver or the fixed ramp; fee extras; capacity
multiplier; on-time multiplier; war handling (follow or decline); bundling;
direct offers; priors or a cold start (`--cold`).

## Robustness

The final is one live run, so these count as much as margin.

- Rebuild all state from the snapshot and the event log; a restart resumes from
  `after=seq` without a second quote or gig for the same thing.
- Obey the `RateLimit-*` headers and batch up to 50 actions.
- Give a quote decision a hard time budget well under 4.5 seconds.
- When a model or solver fails, take the safe action: decline, or post a
  conservative schedule. Never stop the loop.
- A refused action comes back as `{ok: false, reason}` inside a 200.
- Nothing may depend on a seed, a dealer id, a driver id, a place name or a
  fixed competitor level. A `--cold` flag sets every prior to neutral; bench
  it against the priors on the same seeds, and show the jury both.

## Next steps

0. A seed comparison for `pnpm dispatch`: `strategies.bench` plays only Python
   versions. Then bring `src/dispatch.ts` to the level of `dispatch.py` (notes,
   handling rules, declining what it cannot serve).
1. Expected-profit pricing with the flip distribution, trust and the ladder.
2. One fee function that returns the schedule and its expected cost.
3. The `lambda` and `mu` multipliers.
4. Tune 5 to 15 constants by random search on `spread-1` to `spread-5`, with a
   hard penalty under 93% on time, and report on `spread-6` to `spread-10`.
5. `probe.py shape`, then bundling or round trips if it shows a saving.

After each step, play the same seeds at level 8 and record margin and on-time
share.

## Not in scope

An offline simulator, a general routing solver, per-driver priors, booking
drivers before an order is won, and anything that needs `advance`, `fork` or
`delete` during a run.

## References

- Dual mirror descent for online allocation: https://arxiv.org/pdf/2002.10421v1
- Pricing against competitor quotes with one-sided feedback: https://web3.arxiv.org/pdf/2410.14839
- Optimal pay for linear and logistic acceptance: https://arxiv.org/html/2305.01317v5
- Trading Agent Competition, supply chain game (closest precedent): https://www.cs.utexas.edu/~TacTex/dpardoe/papers/TacTexChapter.pdf
