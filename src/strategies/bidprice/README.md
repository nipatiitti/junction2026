# bidprice

The design of [`BRIEF.md`](../../BRIEF.md) on the harness, wired from the quote models
([`models/quote/`](../../models/quote/README.md)), the fee models ([`models/fees/`](../../models/fees/README.md)) and
the order handling ([`ops/`](../../ops/README.md)). One number joins the two sides of the desk: the expected cost `c`
of moving a car, from the fee function that also gives the gig's schedule.

```sh
pnpm dispatch --strategy bidprice --level 8 --seed spread-1
pnpm dispatch --strategy bidprice --set feeFloor=0.9 --set war=decline --seed spread-1
node analysis/replay_bidprice.ts 1 feeFloor=0.9   # offline: saved weeks through the strategy, see below
```

## Data flow

```
event ──► observe ─┬─► WeekLog: requests, note facts, orders, one Retry per leg, our gigs, snow
                   ├─► quote learner (level, day, lane, ladder, trust)
                   └─► fee learner (hazard scale, extras, lambda, mu)
quote()  ──► admission: the options canServe passes with comfortHours to spare, else only the slowest it passes
               (level ≤ 3: the first only); for each, c = the expected cost of its schedule (fee, lateness, lambda)
               for the option as a gig: typical fee, list price, deadline − drive, late weight
             bestQuote(c by option) ──► prices │ decline ──► null (the harness quotes 10 × list above level 3)
gig()    ──► gigShape (note facts, the legs' Retry, snow, tightening) ──► one gig, or one per car of a long trade-in
               each with the ramp (or the solver) for the order's cars; after the deadline warning, at least the
               urgent ramp
tick     ──► every 30 minutes: reprice our gigs that no driver holds: a dropped one at once (the ramp from now, at
               least dropStep above the dropped fee), one whose schedule ended staleHours ago climbing to climbTop;
               at most repriceMax, the nearest last pickup first; never after the deadline warning
sent     ──► a quote as sent: recordQuote, so its answer teaches (a decline at 10 × list teaches nothing)
             a post, reprice or withdraw the world accepted: gig_posted / gig_repriced / gig_withdrawn for the fee
               learner, with the FeeGig rebuilt from the log (order, cars, audience, minute, posted before or not)
```

All state is a function of the `observe` and `sent` calls, so a strategy rebuilt from the event log and the desk's
journal of sent actions holds the same pending quotes and fee state. `tightening` for `canServe` is 1 while the
projected late share (as `mu` counts it) is at its target, and falls to 0.25 as it nears 10%. The late weight is
`(1 + lateTrust × dealer's share of the requests) / (1 + lateTrust / 40)`: a late order halves the dealer's trust, so
lateness costs more for the dealers who send most. A gig that cannot be read, or an order without its request, gets
the starter's gig from the harness.

## Params

Flat, so `--set key=value` sets each one. The flags default to the brief's design.

| Param           | Default  | What it does                                                                          |
| --------------- | -------- | ------------------------------------------------------------------------------------- |
| `pricing`       | `profit` | `profit`: the price that maximises (p − c) × W(p); `median`: the price that wins half |
| `trust`         | `true`   | Count each dealer's trust in W, and value the trust a win adds                        |
| `ladder`        | `true`   | Price each option on its own rung of the option ladder                                |
| `lane`          | `true`   | Learn a level for lanes by the drivers near the delivery place                        |
| `war`           | `follow` | On a price war day: `follow` the level down, or `decline` until 18:00                 |
| `feeSolver`     | `false`  | Plan fees with the fee model's solver; `false`: the ramp below                        |
| `feeExtras`     | `true`   | Scale fees by the learned multiplier of each gig feature                              |
| `capacity`      | `true`   | Scale `c` by the learned capacity multiplier `lambda`                                 |
| `onTime`        | `true`   | Scale the lateness cost by the learned on-time multiplier `mu`                        |
| `cold`          | `false`  | Every prior neutral, quote and fee side                                               |
| `minValueCents` | 200      | Decline a request whose best expected profit, trust included, is under this           |
| `trustValue`    | 1        | Scales the value of the trust a win adds; 0 turns it off                              |
| `lateTrust`     | 5        | Weighs a late car by the dealer's share of the requests; 0 turns it off               |
| `etaLambda`     | 0.1      | Learning rate of `lambda`                                                             |
| `etaMu`         | 0.02     | Learning rate of `mu`                                                                 |
| `lateTarget`    | 0.05     | The late share that `mu` aims at                                                      |
| `comfortHours`  | 9        | Admission: hours to spare an option needs, more as the late share rises               |
| `openFee`       | 0.9      | The ramp's opening fee over typical; it raises to about 1.06 at 1 h and 1.38 at 3 h   |
| `topFee`        | 2.5      | The ramp's top over typical, under the price plus a late car's cost                   |
| `topLeadHours`  | 8        | When the top fee is due (22:00 the evening before when it falls at night)             |
| `feeFloor`      | 1        | The solver's lowest fee over the expected fee: in practice its opening fee            |
| `topRatio`      | 1.5      | The solver's fee over the expected fee due `topLeadHours` before the last pickup      |
| `urgentTop`     | 2.5      | After the deadline warning: `topRatio` × typical at once, rising to this in two hours |
| `staleHours`    | 2        | The tick reprices a gig whose schedule ended this long ago                            |
| `dropStep`      | 0.15     | A dropped gig reprices at least this × typical above the dropped fee                  |
| `climbStep`     | 0.1      | A stale gig climbs this × typical an hour                                             |
| `climbTop`      | 3        | up to this × typical, never above twice the price                                     |
| `repriceMax`    | 10       | Reprices a tick at most                                                               |

The default schedule is the ramp of `dispatch.py` (`strategies/fees/schedule.py`), which paid 1.27 × typical at 98%
on time: open at 0.9, raise a tenth and three tenths of the way to the top after one and three hours, and reach 2.5
eight hours before the last pickup; with under eight hours to the top it opens closer to it. The fee model's solver
stays behind `feeSolver`: it opened every gig at its floor and raised nothing for about 21 hours, and the first
online weeks were 80–84% on time. `c` is the fee model's expected cost of whichever schedule is posted.

Not built: bundling, direct offers and `postAt` (holding a car that is ready days later), so their flags are absent.

## Offline run

`node analysis/replay_bidprice.ts [weeks per seed] [key=value ...]` feeds the first saved `dispatch.py` weeks of
each level 8 seed through the strategy: every event to `observe`, every request to `quote`, and a gig for each order
the saved week won, each deadline warning, failed visit and expired gig. The saved week's own quotes and gigs go to
`sent`, as the desk's journal would: the answers in a saved week are to its own quotes. A third copy runs `tick` every 30 minutes and hears its own reprices back. It prints the share quoted, the
options offered (and those offered under 9 hours of slack), quote and `c` over list and typical, the fees planned, timings, and whether a strategy rebuilt at
mid-week holds the same state. It is not a test; it plays nothing online.

## Decline log

The summary line ends with `declines`: for each request the reason it got no quote (`quoted` when one went out):
`serve-slack`, `serve-deadline`, `serve-note`, `serve-unread` (no option passes `canServe`), `lateRisk` (every
served option over `lateRiskMax`), `war` (the war-day rule), `minValue` (best value under `minValueCents`) and
`underCost` (no price on the grid covers the cost); `opt-<rule>` counts the options each rule left out of a quote.
Set `BIDPRICE_DECLINE_LOG=<file>` to append one JSON line per request (id, minute, reason, options left out, costs,
value, win chance, prices).

- `onTimeOps` (default off, `ontime.ts`): most late orders are gigs that sat open with few views until past their last pickup
  (`analysis/late_causes.py`). From `onTimeLeadHours` (14) before the last pickup an open, unheld gig goes at once to
  `onTimeFee` (2) x typical, at most three prices, and climbs from there.

- `unseenRule` (default off, `unseen.ts`): leaves out a request whose leg is `unseenLegKm` (400) km or more in a straight line and whose pickup has fewer than `unseenMin` (10) roster drivers within `unseenKm` (30) km, the gigs no driver is notified of.
- `analysis/unseen.py` found these are where cause-c late orders (no booking until close to pickup) gather, but the good orders sharing the features earn more than the late ones lose, so on the saved weeks every decline threshold nets negative.
- The summary line reports `unseen removed N options of M requests` (counted per admission call).
`pairs` (default off, `pairs.ts`): the tick joins two one-car orders that no driver holds into one round-trip gig (B's pickup within `pairKm` of A's delivery, B's delivery within `pairKm` of A's pickup; any delivery with `pairChains`) when one driver makes both deadlines with `pairSlackHours` to spare.
It withdraws the two single gigs and posts the pair at `pairOpen` × the sum of their schedules; the pair is withdrawn when an order turns urgent or nobody books it `pairGiveUpHours` before its first pickup must start, and the desk's sweep posts the cars alone again.
A pair is also withdrawn when dropped or stale; the learners see its fee split across its two cars by typical fee, and an urgent pair is repriced at the sum of both orders' schedules.
`pairCostCut` (default 0; 0.08 lost EUR 700 on spread-7) cuts `c` of a request that would pair with an open order of ours.
The summary counts pairs found, posted, booked (fee over the two typical fees), split back, and quotes cut, won and paired.

## Flags for the volume gap (#222)

Three ideas for winning more orders at the same margin. Each is off by default, so the strategy decides as before.

- `trustGuard` (default 0, `trust.ts`): a late order halves the dealer's trust count, and the top dealer sends 25–33% of a week's requests. With `trustGuard` over 0 a late order costs its refund plus the trust the halving loses: the points lost, summed over the orders we still expect to win from that dealer (each on-time win counts one back), times what a point adds to a price, times `trustGuard`.
  It acts in two places. The quote adds the loss times the request's predicted late share (the table of `late.ts`) to `c`, so a risky request of a dealer with trust to lose is priced up or declined. Each gig of that dealer gets a late weight of 1 + loss / refunds (at most `trustGuardMax`, 4) in the fee solver, so its fees rise sooner. The summary reports the gigs it weighed and the mean and top weight.
- `trustMinShare`, `trustUntil`, `trustLagHours` (defaults 0, 25, 0) focus the trust bonus of `trustValue`: only a dealer with at least `trustMinShare` of the requests so far, only while its count is under `trustUntil`, and counting only the requests that arrive `trustLagHours` after the win. An order counts when it is delivered, a median 24–28 hours after the win for every option. With the defaults `trustValue` works as before. The summary reports the quotes that carried a bonus.
- `pairChains` (default off) lets `pairs` join a chain: B's pickup within `pairKm` of A's delivery, with B's delivery anywhere. A chain that is no round trip opens at `pairChainOpen` (0.92) × the two schedules, a round trip at `pairOpen`. The tick now takes the round trips first and then the pair with the shortest empty drive, and `pairCostCut` reaches chains when `pairChains` is on. The summary counts the chains among the pairs found.

Params files for the bench, each `board.json` plus one idea: `trust-guard.json` (`trustGuard` 1), `trust-focus.json` (`trustValue` 1, `trustMinShare` 0.04, `trustUntil` 12, `trustLagHours` 24), `chains.json` (`pairs`, `pairChains`), `trust-both.json` (the two trust ideas) and `volume-all.json` (all three).

```sh
pnpm bench bidprice:src/strategies/bidprice/board.json bidprice:src/strategies/bidprice/trust-guard.json bidprice:src/strategies/bidprice/trust-focus.json bidprice:src/strategies/bidprice/chains.json bidprice:src/strategies/bidprice/trust-both.json bidprice:src/strategies/bidprice/volume-all.json --level 8 --seeds spread-6,spread-7,spread-8,spread-10
```
