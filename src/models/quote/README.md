# Quote models

The quote side of [`BRIEF.md`](../../BRIEF.md) (design 1, findings 2–6 and 13): what chance a price has, how the week
teaches it, and which price to send. Pure functions over plain data, no network, no packages; a request takes about
0.03 ms. A strategy feeds every event to `observe` and asks `bestQuote` at each `price_request`.

```ts
import { bestQuote, createQuoteState, driversNear, observe, quoteParams, recordQuote } from './models/quote/index.ts'

const params = quoteParams() // or quoteParams({ cold: true, flags: { war: 'decline' } })
const state = createQuoteState(driversNear(roster, worldMap))
// for every event, in order:
observe(state, event, params)
// at a price_request, with the expected cost of each option we can serve (fee and lateness, in cents):
const decision = bestQuote(event.request, { next_day: 21000, within_3_days: 18000 }, state, params, now)
recordQuote(state, event.request, decision.prices, params) // after sending { type: 'quote', prices: decision.prices }
```

## The model

A request's flip (the highest price that wins it) over its list price is a level times the request's own scatter.
The log level is a sum of parts, each a Gaussian belief (mean and variance) in `state.belief`:

| Part              | Prior (from `src/params/quote.json`)                                      | Learns from                             |
| ----------------- | ------------------------------------------------------------------------- | --------------------------------------- |
| `world`           | `startLevel` 1.243, sd `worldSd` 0.049                                    | every answer of the week                |
| `day`             | 0, sd `daySd` 0.097; reset each day, with `dayDrift` added at each answer | the day's answers: moves within tens    |
| `lane:<k>`        | `laneSlope` × (k − `laneCenter`), k = log2(1 + drivers near delivery)     | answers on lanes with that many drivers |
| `option:<kind>`   | log of `ladder` (same day 1.096, next day 1, within 3 days 0.968)         | answers for that option                 |
| `trust` (× count) | `trustPerOrder` 0.0082 per order on time, sd `trustSd`                    | answers from dealers with trust         |

The scatter is `flipResidual`: quantiles of flip over its world-day level, ladder and lane on a 2.5% grid, about
±16%. No part is keyed to a seed, a dealer, a driver or a place name: lanes pool by their driver count.

**Learning.** An answered quote is a censored observation: a win says the flip was at or above our price, a loss
that it was below. `learn` (`belief.ts`) is an extended Kalman filter with a logistic observation: each part moves
by its variance times the surprise (1 for a win, 0 for a loss, minus the chance the quote had), and the variances
shrink. So a win moves every part up and a loss down, the parts we know least move most, and the step is bounded.
Each mean stays within four prior deviations of its prior and each variance above a fifth of its prior's. A loss of
a quote with several options teaches at the option likeliest to have won; a win at the option taken.

**Events.** `price_request` counts the dealer's requests; `order_won` and `order_lost` answer the quotes that
`recordQuote` remembered (a quote whose `respondBy` has passed without a win counts as lost); `ledger` counts trust
as `RULES.md` says (a revenue line with no late refund by the next minute is +1, up to 25; a late refund or an
undelivered penalty halves the count); every event's `at` starts a new day. The state is plain data, so
`JSON.stringify(state)` saves it, and `observe` over the event log rebuilds it. Losses need the prices we sent:
replay `bestQuote` and `recordQuote` at each `price_request` (they are deterministic) or restore the saved JSON.

## The functions

- `winProb(price, option, request, state, params)`: the share of flips at or above `price / list`, shifted by the
  level of the request's parts, averaged over what we do not know of the level (three-point Gauss–Hermite), so a
  level we are unsure of spreads the flips wider.
- `dealerWeight(state, dealer, params)`: the dealer's share of the week's requests so far, (n + 1) / (N + 40), so
  equal for every dealer at the start.
- `bestQuote(request, costByOption, state, params, now)`: for each option we can serve, the price on a grid
  (0.8 to 2.2 × list, 1% steps) that maximises `W(p) × (p − c + bonus)`, never under cost. It also tries a slower
  option as the lead with a faster one at a premium of 1% to 60%: the dealer takes one when either price is under
  its flip, and the faster with the share of the choice curve (finding 4: 100% at no premium, 73% at +10%, 51% at
  +20%, 12% at +50%). A faster option is never priced under a slower one, since the dealer takes the fastest at
  equal price. It returns `prices` ready for a quote action, `valueCents`, `winProb` and `decline`; a decline, when
  the best value is under `minValueCents` (€2), quotes 10 × list.
- `trustBonus`: the value of the trust a win adds. One more order on time lifts the price the dealer accepts by
  `trustPerOrder` on its later requests, worth that share of their expected revenue (envelope theorem), until the
  dealer would have reached 25 anyway: `trustValue × perOrder × revenue × min(dealerWeight × requestsLeft,
  (25 − trust) / our win share)`. `trustValue` scales it; 0 turns it off.
- `driversNear(roster, worldMap)`: drivers who live within 30 km of each place, for `createQuoteState`.

## Flags and knobs

`quoteParams({ flags: { ... }, ...knobs })`. Each flag defaults to the brief's design.

| Flag      | Default  | Off                                                                                                                |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------ |
| `pricing` | `profit` | `median`: each option at the price that wins half the time (the rule of `strategies/pricing/model.py`)             |
| `trust`   | `true`   | no trust part and no trust bonus                                                                                   |
| `ladder`  | `true`   | every option at one level                                                                                          |
| `lane`    | `true`   | no lane part                                                                                                       |
| `war`     | `follow` | `decline`: when today's level is `warDrop` (0.15) or more under the world's, after 10 answers, decline until 18:00 |

`cold: true` sets every prior to neutral: level 1 with a wide logistic scatter (sd 0.36 in log), wide world and
day priors, no ladder, lane or trust effect, and a dealer who pays nothing for speed. Every part still learns.

## The priors and the replay

`uv run python -m analysis.priors_quote` writes `src/params/quote.json` from `out/spread.sqlite` (run
`analysis.facts` first): the level 8 quote probes (817 flips in 10 worlds, Monday and Tuesday, trust 0) give the
quantiles, start level, ladder, world and day spreads and lane slope; the played weeks give the choice curve and the
trust effect (a logistic fit of the win on the price, the trust count and the weekday). `node
analysis/replay_quote.ts` replays the models on the probed requests (first option, in arrival order per world,
learning from each answer) against fixed multipliers, at car costs of 0.8, 1.0 and 1.21 × the typical fee:

| Euros a request (share won)         | 0.8 × typical | 1.0 × typical | 1.21 × typical |
| ----------------------------------- | ------------- | ------------- | -------------- |
| fixed 1.26 × list                   | €28.05 (65%)  | €18.00 (65%)  | €7.44 (65%)    |
| best fixed multiplier, in hindsight | €29.17 (77%)  | €18.00 (65%)  | €9.66 (37%)    |
| `bestQuote`, trust value off        | €30.35 (74%)  | €20.14 (62%)  | €11.32 (43%)   |
| `bestQuote`, default                | €30.04 (81%)  | €20.13 (72%)  | €11.17 (53%)   |
| `bestQuote`, cold start             | €24.52 (50%)  | €14.42 (34%)  | €7.34 (18%)    |
| 50% learner (`pricing: 'median'`)   | €25.23 (51%)  | €17.86 (48%)  | €10.57 (40%)   |
| every quote at its flip             | €50.47        | €36.14        | €22.71         |

The priors come from these same probes, so the warm rows are in-sample; the cold row is not, and it sees only
about 45 answers a world here against about 1,000 in a week. The default gives up €0.3 a request at trust 0 to
win more of the dealers whose trust pays later, which the probes cannot show.
