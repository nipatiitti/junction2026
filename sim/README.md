# Offline Spread simulator (level 8)

A local stand-in for the organisers' server: same routes, same JSON, a week in about 1 second.
It is statistically similar to the server, not a copy. Use it to prune and tune; confirm finalists on the real server.

## Run

```sh
uv run python sim/build_data.py               # once, and after new recordings: builds the data packs in sim/data/
pnpm sim --port 8787                          # the server; then point any system at it:
SPREAD_URL=http://localhost:8787 SPREAD_KEY=anything <your system>

pnpm oracle spread-1 nov-3                    # what perfect information would have made of a week
pnpm replay data/scrape/runs/L8/spread-1/<world id>   # a saved week's orders and gigs, server vs simulator
sim/run.sh out/sim --mode play --seeds spread-1      # the prober's desk against a fresh simulator
```

- Data: `sim/data/` is not committed. `sim/build_data.py` (standard library only) builds one pack per recorded level-8 seed from the saved weeks in `data/scrape/runs/`, `data/scrape/passive/`, `data/scrape/starter/` and `data/scrape/probe2/`, plus `out/scrape/explore-*` when you have the team's data release; `sim/market.json` adds the server's price level per weekday for the seeds it covers. The simulator does not start without the packs.
- Seeds: each recorded seed replays the server's own requests, driver list, car facts and cancellations. Any other seed name maps to one of them.
- Any key works. No rate limit and no 8-world cap. There is no WebSocket stream, no ranking round and no final clock: use `advance`.
- `fork` works. By default a fork's first `advance` returns only new events (the server returns the whole history); `--full-fork-history` restores the server's behaviour, slower.
- The same seed and actions give the same week. Dealer limits and driver costs do not depend on the order of your actions, so two policies on one seed face the same hidden values.

## What is exact, what is fitted

| Part                                                                      | Source                                                                                                                                                    |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clock, windows, deadlines, gig rules, refunds, fines, release fees, score | The rules, as written                                                                                                                                     |
| Requests, driver list, car facts, cancellations, changes of plan          | Replayed from recordings. Car facts are known for about half of the requests (those some recorded run won); the rest are taken as the request states them |
| Dealer limit per request and option                                       | Fitted on 1,291 quote probes: base, day, lane, option, trust, lateness, competitor reaction                                                               |
| Who works, what a gig costs a driver, views, waiting, drops               | A driver-by-driver model tuned to 1,720 fee probes and to weekly event counts                                                                             |

All tunable numbers are in `PRM` at the top of `world.ts`; `params.json` overrides them (`SIM_PARAMS=<file>` for another set).

## How close it is (14 Nov, same seeds, same desk, server vs simulator)

- Dealer limit over list price: median 1.35 vs 1.32, spread (sd of log) 0.26 vs 0.25, same-day premium +9% vs +9%.
- Lowest booking fee over typical fee, 10th/50th/90th percentile: 0.43/0.84/1.45 vs 0.43/0.72/1.47. Pickup today 0.97 vs 0.81, pickup tomorrow 0.66 vs 0.70.
- No booking within 3 hours at up to 1.8x typical: 18% vs 13%.
- Quotes 10% lower from mid-week (12 forks): +84 orders, -€5,700 vs +74 orders, -€4,300. Quotes 10% higher: -70 orders, +€2,900 vs -73, +€4,300.

## Known gaps

- **Overload is too gentle.** When a policy wins more, on-time share falls about 5 points on the server and under 1 point here. A policy that wins too many orders looks better here than it is. Check the 90% rule on the server.
- **Each world's price level is drawn, not recovered.** A recorded seed has the server's requests but this simulator's own competitor level, day factors, price-war day and outage. Order counts for one seed can differ a lot (334 on the server vs 584 here on one seed); averages over seeds are what to compare.
- **Fee timing is weak.** The effect of opening lower or higher was within noise on the server and is not reliable here. Do not tune fee schedule shapes on the simulator alone.
- Views per gig run about 1.7 times the server's, and bookings take about 20 minutes longer.
- Notes are not parsed: for cars whose facts were never revealed, the request is taken at its word.
- Not modelled: snow moving deadlines, extra pay after a change of plan, drivers dropping for a better gig.

## Oracle

`oracle.ts` walks the week with everything visible: it prices each request at the dealer's limit, gives it to the cheapest driver who can deliver on time at exactly that driver's cost, and declines the rest. It prints two tiers: any driver, and only drivers who live near the pickup or finish a gig there.
It is a reference, not an attainable score: about €45,000–85,000 a week, against about €9,000 for the best recorded policies. Read it for where the money is (which days, how much from price versus fees versus volume), and remember the overload gap above inflates its volume.

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
