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
                   ├─► fee learner (hazard scale, extras, lambda, mu)
                   └─► at a price_request: decide once, store the answer
                         for each option canServe passes (level ≤ 3: the first only):
                           c = planFees(the option as a gig: typical fee, list price, deadline − drive).costCents
                         bestQuote(c by option) ──► prices, recordQuote │ decline ──► null
quote()  ──► the stored answer (the harness quotes 10 × list for null above level 3)
gig()    ──► gigShape (note facts, the legs' Retry, snow, tightening) ──► one gig, or one per car of a long trade-in
               each with planFees(the order's cars).schedule; from the deadline warning on, at least the urgent ramp
accepted ──► gig_posted / gig_repriced / gig_withdrawn for the fee learner, with the FeeGig rebuilt from the order
```

Every answer comes from the events alone: a strategy rebuilt from the event log, with the snapshot's gigs told again
as accepted posts, holds the same quotes, pending answers and fee state. `tightening` for `canServe` is 1 while the
projected late share (as `mu` counts it) is at its target, and falls to 0.25 as it nears 10%. A gig that cannot be
read, or an order without its request, gets the starter's gig from the harness.

## Params

Flat, so `--set key=value` sets each one. The flags default to the brief's design.

| Param           | Default  | What it does                                                                          |
| --------------- | -------- | ------------------------------------------------------------------------------------- |
| `pricing`       | `profit` | `profit`: the price that maximises (p − c) × W(p); `median`: the price that wins half |
| `trust`         | `true`   | Count each dealer's trust in W, and value the trust a win adds                        |
| `ladder`        | `true`   | Price each option on its own rung of the option ladder                                |
| `lane`          | `true`   | Learn a level for lanes by the drivers near the delivery place                        |
| `war`           | `follow` | On a price war day: `follow` the level down, or `decline` until 18:00                 |
| `feeSolver`     | `true`   | Plan fees with the solver; `false`: the starter's fixed ramp                          |
| `feeExtras`     | `true`   | Scale fees by the learned multiplier of each gig feature                              |
| `capacity`      | `true`   | Scale `c` by the learned capacity multiplier `lambda`                                 |
| `onTime`        | `true`   | Scale the lateness cost by the learned on-time multiplier `mu`                        |
| `cold`          | `false`  | Every prior neutral, quote and fee side                                               |
| `minValueCents` | 200      | Decline a request whose best expected profit, trust included, is under this           |
| `trustValue`    | 1        | Scales the value of the trust a win adds; 0 turns it off                              |
| `etaLambda`     | 0.1      | Learning rate of `lambda`                                                             |
| `etaMu`         | 0.02     | Learning rate of `mu`                                                                 |
| `lateTarget`    | 0.05     | The late share that `mu` aims at                                                      |
| `feeFloor`      | 1        | The solver's lowest fee over the expected fee: in practice the opening fee            |
| `topRatio`      | 1.5      | The fee over the expected fee due `topLeadHours` before the last pickup               |
| `topLeadHours`  | 8        | When that top fee is due (22:00 the evening before when it falls at night)            |
| `urgentTop`     | 2.5      | After the deadline warning: `topRatio` × typical at once, rising to this in two hours |

The fee side is set to the safe side: the fee model expects 95–99% of flat low fees to book where 77–89% did, and a
late order costs about €60. The solver opens at its floor on nearly every gig, so `feeFloor` is the opening fee; its
model alone would open at 0.75. Bench lower floors and a later top on the same seeds before taking them.

Not built: bundling, direct offers and `postAt` (holding a car that is ready days later), so their flags are absent.

## Offline run

`node analysis/replay_bidprice.ts [weeks per seed] [key=value ...]` feeds the first saved `dispatch.py` weeks of
each level 8 seed through the strategy: every event to `observe`, every request to `quote`, and a gig for each order
the saved week won, each deadline warning, failed visit and expired gig. The saved week's gigs are told as accepted
posts. The answers in a saved week are to its own quotes, so the run records those as the pending quotes. It prints
the share quoted, quote and `c` over list and typical, the fees planned, timings, and whether a strategy rebuilt at
mid-week holds the same state. It is not a test; it plays nothing online.
