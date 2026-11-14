# Offline Spread simulator (level 8)

A local stand-in for the organisers' server: same routes, same JSON, a week in about 1 second.

> **This simulator has no seed parity with the server.** A recorded seed replays the server's requests, driver list and
> price level, but every dealer's limit for a request and every driver's cost for a gig are the simulator's own draws.
> One simulated week tells you little about the same week on the server.
>
> **Use it for big parameter swings and for direction, averaged over several seeds.** Measured on 37 of our strategies,
> each played on spread-1, spread-2 and spread-3 here and on the server (14 Nov):
>
> | Real gap between two strategies (mean weekly margin) | Simulator picks the same winner |
> | ---------------------------------------------------- | ------------------------------- |
> | under €500                                           | 59% (a coin flip)               |
> | €500–1,500                                           | 90%                             |
> | over €1,500                                          | 100% (339 of 339 pairs)         |
>
> Over all pairs: 88%. Rank correlation of mean margins: 0.92 over three seeds, 0.77–0.87 on one seed. The simulator
> runs about €2,500 a week high (sd €860) and wins about 29 more orders, fairly evenly across strategies, so compare
> strategies with each other here, never a simulated margin with a server margin. On-time share does not rank at all
> (correlation 0.03): every strategy is ranked on both sides, so **check the 90% rule on the server**.
> Confirm any finalist on the real server.

## Run

```sh
pnpm sim --port 8787                          # the server; then point any system at it:
SPREAD_URL=http://localhost:8787 SPREAD_KEY=anything <your system>

pnpm oracle spread-1 nov-1                    # what perfect information would have made of a week, in tiers
pnpm oracle spread-1 --week data/scrape/runs/L8/spread-1/<world id>   # a saved week's result next to the tiers
pnpm replay data/scrape/runs/L8/spread-1/<world id>   # a saved week's orders and gigs, server vs simulator
sim/run.sh out/sim --mode play --seeds spread-1      # the prober's desk against a fresh simulator
```

- Data: `sim/data/` holds one pack per recorded level-8 seed (398 seeds, 26 MB), committed because most of their weeks are not on main. `sim/build_data.py` (standard library only) rebuilds the packs from the saved weeks under `data/scrape/` (and `out/scrape/explore-*` when present); run it only when you have more weeks than the committed packs cover, since it writes packs only for the seeds it finds. `sim/market.json` holds the server's price level per weekday for 348 seeds, recovered from recorded quotes, and `sim/lanes.json` the town effects that hold in every week.
- Seeds: each recorded seed replays the server's own requests, driver list, car facts and cancellations. Any other seed name maps to one of them.
- Any key works. No rate limit and no 8-world cap. There is no WebSocket stream, no ranking round and no final clock: use `advance`.
- `fork` works. By default a fork's first `advance` returns only new events (the server returns the whole history); `--full-fork-history` restores the server's behaviour, slower.
- The same seed and actions give the same week. Dealer limits and driver costs do not depend on the order of your actions, so two policies on one seed face the same hidden values.

## What is exact, what is fitted

| Part                                                                      | Source                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clock, windows, deadlines, gig rules, refunds, fines, release fees, score | The rules, as written                                                                                                                                                                                                                                    |
| Requests, driver list, car facts, cancellations, changes of plan          | Replayed from recordings. Car facts are known for about half of the requests (those some recorded run won); the rest are taken as the request states them                                                                                                |
| The week's price level per weekday                                        | For 348 recorded seeds, recovered from that seed's recorded quotes (`market.json`); it holds that week's price war. Other seeds draw a level                                                                                                             |
| Dealer limit per request and option                                       | Fitted on 2.58M recorded quotes and 1,291 quote probes: town effects (`lanes.json`), option, hour, trust (the rule's 1% per on-time order), 2.1% per late order, the competitor's daily steps per dealer, and noise per dealer, lane, request and option |
| Who works, what a gig costs a driver, views, waiting, drops               | A driver-by-driver model tuned to 1,720 fee probes and to 222,000 first postings of recorded weeks replayed here (`pnpm replay`)                                                                                                                         |

All tunable numbers are in `PRM` at the top of `world.ts`; `params.json` overrides them (`SIM_PARAMS=<file>` for another set).

## How close it is (14 Nov, server vs simulator)

Recorded weeks replayed (240 weeks, the server's orders and gig postings injected):

- First postings booked within 30 minutes: 61% vs 65%; within 3 hours: 79% vs 80%; fee over typical: 0.94 vs 0.93; dropped: 14% vs 14%.
- Pickup tomorrow, booked within 30 minutes: 74% vs 82%. Pickup today, within 3 hours: 63% vs 62%.
- Per week: drops 48 vs 50, expired gigs 9 vs 11, views 8,300 vs 8,200, on time 97.1% vs 96.4%, margin €9,900 vs €8,400 (correlation 0.80).
- Overloaded weeks (the starter's): on time 50% vs 70%; gigs per driver-day 1/2/3+ are 77/22/1% vs 76/22/2.5%.

Fee probes (same seeds, same desk):

- Lowest booking fee over typical fee, 10th/50th/90th percentile: 0.43/0.84/1.45 vs 0.36/0.68/1.49. Pickup today 0.97 vs 0.79, pickup tomorrow 0.66 vs 0.61.
- No booking within 3 hours at up to 1.8x typical: 18% vs 12%.

Policy forks from mid-week (12 forks each, on seeds without a recovered price level):

- Quotes 10% lower: +84 orders, -€5,700, -4.8 on-time points vs +67 orders, -€6,500, -3.1 points.
- Quotes 10% higher: -70 orders, +€2,900, +3.5 points vs -51 orders, +€4,400, +2.2 points.
- Over all 83 forks the margin changes correlate at 0.79. Direction agrees 45% of the time for effects under €500, 70% for €500–1,500 and about 83% above that.

Dealers: against 400,000 recorded quotes the model's win probability is within 1.5 points in every probability bucket after the last fit.

## Known gaps

- **No seed parity**, as said at the top.
- **Overload is still too gentle.** The daily gig limit now binds, but an overloaded week ends about 18 points more on time here than on the server: gigs rarely run late once started, and drops do not rise with load. A policy that wins too many orders looks better here than it is.
- **Fee timing is not reliable.** Opening fees 0.15x typical lower or higher made no clear difference on the server, and the simulator disagrees with it in sign. The lowest fee that books is also about 20% cheaper here. Do not tune fee schedule shapes or fee levels on the simulator alone.
- **Fridays are too slow** (median wait for a Friday posting 188 minutes vs 92), and today's pickups are dropped less often than on the server (9% vs 12%).
- **The competitor's daily steps are the least verified dealer term.** They come from a fit within each dealer; a check quote by quote cannot confirm them, because the dealers we win from are the ones that accept more.
- Margin swings from price changes are 15–50% larger here than on the server.
- The outage region is not modelled for recovered seeds: the day's level holds its average, not its geography.
- Notes are not parsed: for cars whose facts were never revealed, the request is taken at its word.
- Not modelled: snow moving deadlines, extra pay after a change of plan, drivers dropping for a better gig.

## Oracle

`pnpm oracle <seed>` prints what a dispatcher with more and more knowledge would have made of the week, in the simulator's hidden values:

- **a blind**: one markup on the list price and one fee rule for the whole week, the best in hindsight; drivers are paid a premium over the cheapest driver's cost (`--premium`, default 1.5, which is what the best recorded policies paid).
- **b limits**: every dealer's limit known, the same market fees.
- **c costs**: every driver's cost known and paid exactly, one markup.
- **d both**, also capped at 2 gigs per driver-day (`--per-driver`) and at 65 orders a day (`--cap`), and at several daily caps to show the value of volume.

With `--week <folder>` it adds a recorded week of that seed: the policy's account, tier d on the policy's own orders, and the gap to tier d split into price, fee, selection, volume and losses. `--json` prints the numbers; `--local` counts only drivers near the pickup.

Tier d assigns drivers in five passes over the week: a driver-day that blocked a later, more profitable order gets a reservation price for the next pass. It is a heuristic, not a proven optimum, and every tier is an upper bound under the assumptions at the top of `oracle.ts`: nothing drops or fails, and every note is read. On spread-1 the tiers are about €16,000 / €34,000 / €37,000 / €66,000 against €19,300 for the best recorded week; most of that gap is which requests to win, then fees. Read it for where the money is, not as a score to reach.

## Prober

`sim/prober.ts` plays weeks with a small randomised desk and measures hidden values by forking. It reads the server from `SPREAD_URL` (default: the Spread server) and keys from `SPREAD_KEY`, `SPREAD_KEY1`, `SPREAD_KEY2`, ...; it writes `<out>/<mode>/L<level>/<seed>/` with `probes.jsonl`, `events.jsonl.gz`, `reveal.json.gz`, `drivers.json` and `meta.json`.

- `--mode play`: just play and record the week.
- `--mode fee`: for each won order (a `--share` of them), the lowest flat fee that books within `--window` minutes.
- `--mode quote`: for each request (a `--share` of them), the highest price the dealer accepts, per option.
- `--mode branch --at 1920,3360`: from each minute, seven policy variants played to the end of the week on forks.

**Against the Spread server the prober is an online run** (`pnpm prober ...`): run it only when the user explicitly asks, one run at a time, as `AGENTS.md` says. Against the simulator it is offline: use `sim/run.sh`, or `SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim node sim/prober.ts --mode fee --share 0.05 --seeds spread-1 --out out/sim`. `data/scrape/probe2/` holds the server's results from 14 Nov.

## Recalibrate

The scripts marked `--with numpy` need numpy, which is not a project dependency: `uv run --with numpy` fetches it for that run.

```sh
uv run python sim/build_data.py                                    # rebuild data packs after new recordings
sim/cal.sh out/cal && uv run --with numpy python sim/cal_cmp.py data/scrape/probe2 out/cal pr-1 pr-3 pr-5 pr-8   # fee probes, server vs simulator
uv run --with numpy python sim/cal_fee.py data/scrape/probe2       # summary of one prober output folder
uv run python sim/cal_branch.py data/scrape/probe2 <sim branch out> pr-5 pr-6 pr-7 pr-8              # policy sensitivities
REPLAY_OUT=out/replay.jsonl pnpm replay <week folders...> && uv run --with numpy python sim/cal_replay.py out/replay.jsonl   # drivers on saved weeks
```

`sim/` is type-checked with the rest (`pnpm check`). Biome turns off the rules that only object to its compact style (`any`, non-null assertions, parameter reassignment, comma operators, string concatenation); see the `sim/**` override in `biome.json`.
