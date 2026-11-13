# Spread (Junction 2026) — build brief for the dispatcher core

You are building the decision core of our entry for the Spread challenge: a
system that acts as a car transport dispatcher in Finland for one simulated
week. This brief gives you the design we have settled on. A teammate is running
a separate study of revealed practice worlds; their fitted numbers plug into
the interfaces below, so build against the interfaces and use the placeholder
defaults until real numbers arrive.

## Read these first

The facts in this brief come from a summarised reading of the challenge pages,
not the exact text. Before writing code, read the sources and trust them over
this brief wherever they differ. `RULES.md` is the authoritative one.

- https://spread.bahnexpress.com/llms.txt
- https://spread.bahnexpress.com/kit/RULES.md
- https://spread.bahnexpress.com/kit/HANDBOOK.md
- https://spread.bahnexpress.com/kit/API.md
- https://spread.bahnexpress.com/openapi.json
- The TypeScript starter kit (`/kit/spread-typescript.tar.gz`). Read
  `starter.ts` and the kit's types: they show the real field names and event
  shapes.

Setup needs `SPREAD_URL=https://spread.bahnexpress.com` and `SPREAD_KEY` in the
environment. Never write the key into a file or a commit.

Use TypeScript with the TypeScript kit (`spread-typescript.tar.gz`), run with
Bun (or Node 22.18+). Keep the solvers dependency-free where practical; the
price grid, the schedule solver and random search need no numeric library.

## The game in short

- Dealers send transport requests (Monday 08:00 to Friday 18:00). Each has up
  to three delivery options (`same_day`, `next_day`, `within_3_days`), a
  reference driver fee, and a response deadline 15 simulated minutes later.
- We answer with one price per option. A quote cannot be withdrawn. Declining
  means quoting far above list. A competitor also quotes; at level 8 it sits
  roughly 26–54% above list, with one unannounced day at 20% under.
- For each won order we post a gig: ordered stops, an audience, and a fee
  schedule of 1–48 non-decreasing steps. Freelance drivers accept or not.
- Score is gross margin: quotes paid, minus driver fees, fines, refunds and
  penalties. An order undelivered at the end costs twice its price.
- At least 90% of won orders must arrive on time, or the team is not ranked.
  In ranking rounds all five worlds must pass.
- Level 8 (the final's level) adds town-level driver shortages and dealer
  trust: each on-time order raises that dealer's accepted prices by 1%, up to
  25 orders; a late order halves the count.
- The final is one secret level 8 world, run live once: about 18 real seconds
  per simulated weekday hour, about 34 minutes in total, 20 actions/s.

## Core idea

The whole week is one large decision problem that we cannot solve exactly. We
split it into two small problems that we can solve, and join them with one
number: the shadow price of driver capacity. This is the bid-price control
method airlines use to decide which fare requests to accept when seats are
scarce. Here the scarce resource is drivers in a town on a day.

A second way to read the same design, useful when choosing between options:
we are a market maker. We quote an ask to dealers and a bid to drivers, and we
hold an inventory of won orders that have no driver yet. Market-making models
shift both quotes as inventory grows: ask higher, bid higher. The shadow price
below is that shift.

The nearest precedent is the Trading Agent Competition supply chain game
(2003–2006): bid on customer requests, win on price, pay late penalties, buy
supply. Its strong agents estimated win probability against price and
maximised expected profit, as in section 1. In the 2006 finals the top agents
were separated by their procurement, not their bidding. Expect the driver side
(sections 2 and 3) to matter more than the quote side here too.

### 1. Quote side: price each option

For each option `o` of a request, choose the price `p` that maximises

    expected profit(p) = (p - c_o) * W(p)

- `W(p)` is the probability that the dealer accepts price `p`. It comes from
  the win model (interface below).
- `c_o` is the full expected cost of serving option `o`:

      c_o = expected driver fee
          + expected lateness and failure cost
          + expected fines
          + shadow price of the capacity this order uses
Maximise by evaluating a grid of candidate prices, not by a closed form, so
that any shape of `W` works. Keep this special case as a unit test: if the
competitor's price is uniform between `a*L` and `b*L` (L = list price) and the
dealer takes the cheaper offer, the best price is `(b*L + c) / 2`, clipped to
just under `a*L` at the low end. With a = 1.26 and b = 1.54, any cost below
about `0.98 * L` gives "quote just under the competitor's floor".

Decline an option when its best expected profit is below a minimum threshold,
or when no feasible gig exists for it. We do not yet know how a dealer chooses
between the options we price; check the rules and the reveal data, and until
then price each option independently.

### 2. Supply side: build the fee schedule

A fee schedule is an optimal stopping problem. Let `h(fee, lead time, town,
audience)` be the chance that some driver accepts during one step. Working
backwards from the last step:

    V[k][prev] = min over fee >= prev of
                 h * fee + (1 - h) * V[k+1][fee]

`V` after the last step is the cost of the gig going unfilled (rescue cost, or
the lateness refund, or the undelivered penalty). Solve it over a small grid of
fee levels. The result gives two things: the schedule to post, and its expected
fee and fill probability, which feed `c_o` above. Check in the API how step
timing is specified before fixing the step grid.

### 3. The link: shadow price of capacity

If we price well we win most requests, and then drivers run out. The shadow
price `lambda(region, day)` is what one more unit of committed driver time
costs us in orders we can no longer serve well. Start with a simple form:

    u      = committed driver hours / expected available driver hours
    lambda = kappa * max(0, u - u0) / max(eps, 1 - u)

`kappa` and `u0` are tuned parameters. Expected available hours come from the
supply model. Raise `lambda` for the experienced-driver pool separately, since
premium cars need those drivers.

Then add the self-tuning version, which is the one we expect to keep. It
follows dual mirror descent for online allocation (Balseiro, Lu and Mirrokni):
hold one multiplier per scarce resource and update it from what actually
happens, with no hand-shaped curve.

    after each commitment that uses g units of resource r,
    where rho_r is the planned use per commitment (budget / expected orders):

    lambda_r = lambda_r * exp(eta * (g - rho_r))

`eta` is the only tuned constant. Because the multipliers adapt during the
week, this version should cope better with a secret world than constants
tuned offline. Keep the utilisation formula behind a flag as the fallback and
as the comparison for the ablation.

### 4. On-time controller

Treat the 90% rule as a budget with a buffer. Track the projected on-time share
of won orders. Target 95%. When the projection falls toward the target, raise
the lateness cost used in `c_o` and in the schedule solver, which makes the
system quote higher, decline more, and pay drivers sooner. When there is slack,
spend it on the orders that are most expensive to rescue.

In the self-tuning version the on-time rule is one more multiplier, `mu`,
updated the same way as `lambda`: it rises when the projected late share is
above 5% and falls toward zero when below. `mu` is the lateness cost.

Also keep an exact count. With N won orders, at most `floor(0.1 * N)` may be
late, and a delivery under 2 hours late costs only a 10% refund. Once requests
stop on Friday, N is fixed and the remaining late allowance is a known whole
number. Spend what is left of it (minus a safety reserve) on the open orders
where a cheaper, slower fee schedule saves more than the refund costs. Put
this behind its own flag.

## Interfaces to the reveal study

Keep each of these behind one function with a placeholder implementation, and
load fitted values from a single parameters file (`params.json`).

| Function                                              | Returns                                        | Placeholder until fitted                                     |
| ----------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| `win_prob(price, request, dealer_state, world_state)` | chance the dealer accepts                      | uniform competitor on 1.26–1.54 × list at level 8            |
| `accept_hazard(fee, lead_time, town, audience)`       | chance per step a driver accepts               | logistic in `fee / referenceFee`, centred at 1.0             |
| `supply(region, day)`                                 | expected available driver hours                | driver counts from `GET /drivers` × a fixed hours figure     |
| `dealer_ceiling(dealer_state)`                        | highest price a dealer accepts                 | list × (1 + 0.01 × trust count), unverified                  |
| `price_war(world_state)`                              | whether the competitor is undercutting today   | off; later, a loss-streak detector                           |
| `driver_prior(driver_id)`                             | a known driver's reservation fee and home area | none; only usable if driver identities persist across worlds |
| `dealer_prior(dealer_id)`                             | a known dealer's expected request volume       | none; only usable if dealer identities persist across worlds |

Notes on the win model. Our only signal about the competitor is one-sided: a
win says its price was above ours, a loss says it was below. Fit the model
from that censored signal (the bond-dealer quoting paper in the references
treats this case), and update it during the live week as well as offline. A
Bayesian logistic model updated after each win or loss is enough.

## Questions to settle before building the advanced parts

Each answer changes the design. Check the rules and API, then test on a
practice world. Share the answers with the teammate running the reveal study.

1. **Is the roster fixed across seeds?** Compare driver and dealer identities,
   homes and ratings between two seeds at the same level. If they persist,
   `driver_prior` and `dealer_prior` become real: we can learn each driver's
   reservation fee in practice and aim direct offers at the right drivers in
   the final, and build trust first with the dealers that send most requests.
2. **Are acceptance rules thresholds or probabilities?** Fork one practice
   world many times at the same moment and vary only one fee or one price. If
   the outcome flips at a sharp value, bisect to find it exactly; we can then
   recover the simulator's rules instead of fitting curves to them.
3. **Can a gig be posted before its order is certain?** If so, a driver booked
   early in a shortage town is an option: releasing more than 24 hours before
   pickup costs 25% of the fee. If not, drop the capacity options idea below.
4. **Do drivers care where a gig ends?** Real driveaway firms' main cost is
   the driver's trip home. Test whether gigs that end near where they start,
   or near the driver's home, fill at lower fees.
5. **How does a dealer choose between our priced options?** Cheapest, fastest,
   or something else. This decides whether options are priced independently.
6. **How high will a dealer go with no competitor?** Level 6 has a competitor
   outage in one region for a day. Find the dealer's ceiling there.
7. **How low will a driver go?** Test schedules that start far below the
   reference fee when pickup is days away.

## Structure

- `client`: API calls, stream handling, rate limiting.
- `state`: world state rebuilt only from the event log.
- `models`: the five functions above plus `params.json`.
- `quote`: section 1.
- `schedule`: section 2.
- `capacity`: sections 3 and 4.
- `gigs`: turning won orders into gigs, including handling rules.
- `run`: the live loop.
- `tune`: the parameter tuner.
- `eval`: run a policy on a list of seeds and report margin and on-time share.

Graphs are a supporting structure only. Use the map (`GET /v1/map`) for travel
times, regional supply, and the order of stops when cars are combined. Do not
build a general vehicle-routing solver; drivers are not ours to route.

## Handling rules the gig builder must enforce

Verify each against `RULES.md`.

- Premium car: experienced audience only (fine otherwise).
- Electric car under 30% charge on a route over 200 km: add a charging stop.
- Multi-car gig: at most 12 hours of driving.
- Dealer sites: deliver only within opening hours.
- Private delivery: deadline is the end of the booked hour plus 30 minutes.
- `same_day`: only if requested by 15:00 and arrival can be 2 hours early.
- Notes (Finnish, Swedish or English) bind the world whether we read them or
  not. Parse them with rules first; a small language model may be added only
  if it answers well inside the quote time budget below.

## Robustness requirements

The final is a single live run, so these matter as much as margin.

- All state is rebuilt from the event log. A restart mid-week must resume
  correctly using `after=seq`, without duplicate quotes or gigs.
- Respect the rate limits (20 actions/s and 50 reads/s in the final); batch up
  to 50 actions per call and obey the `RateLimit-*` headers.
- A quote decision has about 4.5 real seconds in the final. Give it a hard
  time budget well under that.
- If any model or solver throws or times out, fall back to a safe action:
  decline the request, or post a conservative schedule. Never crash the loop.
- Failed actions come back as `{ok: false, reason}` inside a 200; handle them.

## Ablation flags

The jury wants each idea shown with and without it on the same weeks. Put each
of these behind a flag from the start, and make `eval` able to compare runs:

- shadow price on/off
- schedule solver vs. a fixed linear ramp
- on-time controller on/off
- trust-aware pricing on/off
- price-war detector on/off
- car combining on/off
- self-tuning multipliers vs. the utilisation formula
- end-of-week lateness spending on/off
- per-driver and per-dealer priors on/off
- capacity options on/off
- round-trip gig preference on/off

## Tuning

Tune against the practice server, not a rebuilt offline world.

- Parameters: about 5–15 constants (`kappa`, `u0`, on-time target, minimum
  profit threshold, fee grid bounds, lateness cost multiplier, and similar).
- Method: random search first, CMA-ES if time allows.
- Objective: mean margin over the training seeds, with a hard penalty when any
  seed falls below 93% on time.
- Keep a separate set of seeds that the tuner never sees, and report on those.
- Practice rate limits shrink as more teams join, so make `eval` frugal with
  requests and able to run several worlds in parallel (at most 8 open).

## Experimental directions

These are bets, not requirements. Build each behind a flag, measure it with
`eval` on the shared seed list, and keep it only if it helps on the held-out
seeds. The first two are tools and are worth building early.

- **Probe tool.** A script that forks a practice world at a chosen moment,
  applies one varied action per fork, advances, and reports the outcomes. It
  answers questions 2, 4, 6 and 7 above by experiment.
- **Hindsight oracle.** For a revealed week, compute the best result
  achievable with full knowledge of requests and driver behaviour (a greedy or
  integer-programming bound is fine). Report the gap between our run and the
  oracle, split into quoting, driver fees and car combining. This tells us
  where the remaining margin is, and the jury will want to see it. Two 2026
  preprints on truckload bid acceptance use the same device.
- **Simple-strategy baselines.** Three one-rule policies to run as reference
  points and as a search for a rule that the world rewards unduly: decline
  almost everything and win only safe orders; always quote just under the
  competitor's floor; win many short, easy orders at thin margin to enlarge
  the late allowance for profitable hard ones.
- **Capacity options.** Depends on question 3. Book drivers early in towns
  with forecast shortages and release the unused ones more than 24 hours out.
- **Round-trip gigs.** Depends on question 4. Prefer gig shapes that return
  the driver toward the start, including trade-in pairs.
- **Monopoly pricing.** Depends on question 6. When the competitor is
  detected as absent in a region, price at the dealer's ceiling.
- **Probing quotes.** Early in a live week, spread quotes across the
  competitor's likely range to locate it quickly. Weigh this against dealer
  trust, which rewards winning early.
- **Evolved policies.** A loop in which coding agents propose variants of the
  pricing and fee functions, `eval` scores them on training seeds, and the
  best survive, with held-out seeds as the gate. Highest risk; limited by the
  practice rate limits. Attempt only after the core is stable.

## Build order

1. `client`, `state` and `eval`, reproducing the starter's score on level 8,
   seed `spread-1` (about -€72,600 margin, 45.5% on time per the handbook).
2. The roster check (question 1) and the probe tool. Report the answers
   before going further.
3. A baseline that declines everything it cannot clearly serve. Confirm it is
   ranked (at least 90% on time) with positive margin. Run the other two
   simple-strategy baselines alongside it.
4. `quote` with the placeholder win model and a fixed fee ramp.
5. `schedule` solver.
6. `capacity`: utilisation shadow price, the on-time controller, then the
   self-tuning multipliers.
7. Hindsight oracle, and the gap report on the current policy.
8. `tune`, then swap in fitted models as they arrive.
9. Car combining and trade-in pairing, then the remaining experimental
   directions in order of the gap the oracle shows.

After each step, run `eval` on the same seed list at levels 6, 7 and 8 and
record margin and on-time share, so the effect of each step is on file.

## Not in scope

- Rebuilding the simulator offline.
- A general routing solver.
- Anything that depends on `advance`, `fork` or `delete` at run time; they are
  closed in the final. Use them only in `eval`, `tune` and the probe tool.

## References

These were found in a quick search and read only as summaries. Open a paper
before relying on any detail of it.

Closest precedent (Trading Agent Competition, supply chain game):

- Analysis of the 2004 competition: https://www.cs.utep.edu/kiekintveld/papers/2006/kwv-tac04-analysis.htm
- TacTex bidding (win probability against price): https://www.cs.utexas.edu/~dpardoe/papers/SIGecom04.pdf
- TacTex chapter: https://www.cs.utexas.edu/~TacTex/dpardoe/papers/TacTexChapter.pdf
- Andrews et al., study of game logs (procurement decided 2006): https://jmvidal.cse.sc.edu/lib/andrews09a.html

Driver pay and acceptance (section 2):

- Çınar et al., closed-form optimal pay for linear and logistic acceptance: https://arxiv.org/html/2305.01317v5
- Schur and Winheller, pay over time as a dynamic program: https://www.pl.msm.uni-due.de/en/research/publications/optimizing-last-mile-delivery-a-dynamic-compensation-strategy-for-occasional-drivers-6902/
- Pricing, bundling and driver behaviour (combining tasks with pay): https://arxiv.org/pdf/2507.03634

Shadow prices and long-run constraints (sections 3 and 4):

- Balseiro, Lu and Mirrokni, dual mirror descent for online allocation: https://arxiv.org/pdf/2002.10421v1
- Online allocation with long-term constraints: https://arxiv.org/pdf/2507.09473v1

Accepting loads with moving, time-limited resources, and hindsight bounds:

- Dual-price policies for truckload bid acceptance: https://arxiv.org/pdf/2607.16891
- Bid acceptance benchmark with hindsight ceilings: https://arxiv.org/pdf/2607.07343
- Reinforcement learning for bidding in truckload markets: https://arxiv.org/pdf/1802.08976
- Posted price versus auction in freight marketplaces: https://arxiv.org/html/2106.00923v3
- Uber Freight on its carrier pricing: https://www.uberfreight.com/en-US/blog/reimagining-uber-freights-carrier-pricing-algorithm-to-drive-better-outcomes

Learning the win model from wins and losses (section 1):

- Pricing against competitor quotes with one-sided feedback: https://web3.arxiv.org/pdf/2410.14839
- Learning logistic demand curves in business-to-business pricing: https://informs-sim.org/wsc13papers/includes/files/003.pdf
- Dynamic pricing with censored feedback: https://cs.gmu.edu/%7esanmay/papers/ijcai18-dynamic-pricing.pdf

Real-world driveaway (round-trip idea):

- DRAIVER return-ride case study: https://www.uber.com/us/en/blog/draiver-teams-with-uber-and-uses-api-to-save-30/
