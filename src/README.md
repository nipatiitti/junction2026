# The TypeScript system

`src/dispatch.ts` plays a Spread week with one strategy on a harness. The strategy that plays by default is
[`lean`](strategies/lean/README.md): one online win model, one worth of capacity and one slow fee climb, built from the
measured level 8 facts. [`BRIEF.md`](BRIEF.md) is the brief of the system before it, kept for its measurements.

`vendor/spread-typescript/` holds the organisers' TypeScript kit of 13 November, unchanged: the client (`spread.ts`),
its types, the starter and `reveal-csv.ts`. Lint and format skip `vendor/`. The `starter` strategy decides exactly as
the organisers' starter, so it gives the starter's [baseline](../strategies/baseline/README.md); the harness also posts
its gig when a strategy fails.

```sh
pnpm dispatch --level 8 --seed spread-1   # a whole practice week with the lean strategy
pnpm dispatch --set target=0.26 --seed spread-1   # other params
pnpm dispatch --strategy starter --seed spread-1   # another strategy
pnpm starter --level 8 --seed spread-1    # the same week with the organisers' unchanged starter
pnpm reveal-csv <world id>                # write an ended week and its reveal to CSV files
pnpm dispatch --final                     # play our copy of a test final or of the final
```

`--strategy <name>` picks the strategy (`lean` by default). `--params <file>` overrides its params with the values
of a JSON file, and `--set key=value` overrides one; both can be given more than once, and a key that the strategy
does not have is an error. `--board` plays a ranking run and `--final` the final, as before.

**The harness** (`harness/`) does everything that is not a decision, so a strategy does not know whether a
practice week (`advance`) or a final (the event stream) runs:

- `desk.ts` keeps the books (requests, orders, gigs, booked gigs, deadline warnings) and rebuilds them from the
  snapshot and the event log after a restart, so no quote or gig goes twice. It does the order mechanics: it posts a
  won order, posts again after a failed visit, withdraws and posts again after a change, reposts after `gig_expired`,
  reprices after the deadline warning, and posts each car alone when a gig of several is refused. A refused post of one
  car with windows of its own goes once more without them. A sweep (on the strategy's tick, on each idle second of a
  final and after a rebuild) posts every undelivered car of a live order that no gig carries and no post waits for,
  as after a cancel in a combined gig; a car goes again at most once an hour.
- `guard.ts` runs every strategy call within a time budget (1.5 s for a quote), and checks every action before it goes
  out: whole, finite numbers, prices and fees of at least 1 cent, a schedule of 1 to 48 steps in time order that never
  falls, stops and audience present, prices only for the options offered. On an error, a late or an invalid answer the
  desk declines the request (10 times the list price, or no quote up to level 3), posts the starter's gig or drops the
  tick action, counts it, and goes on. A refused action is counted, never thrown; a batch that the server refuses as
  a whole goes again in halves, so only the bad action is refused. The end of a week prints both counts.
- `journal.ts` keeps our half of the week: every action sent, with the world's answer, the minute and the last event
  seen, in `out/journal/<world id>.jsonl` (`SPREAD_JOURNAL_DIR` changes the folder). On a rebuild the new strategy gets
  the event log and the journal merged in order, so it ends in the state of the one that played. Without the file, as
  on another machine, it gets the events only.
- `loops.ts` holds the practice and the live loop, `week.ts` plays one week and saves it. The practice loop sends
  one request a step: the `advance` carries the actions of the step before. While dealers ask for prices (weekdays,
  08:00 to 18:15) a step is 10 minutes, so every request is quoted inside its 15 minutes; outside those hours the
  world runs to the next event that needs an answer, an hour at most. Forty level 8 weeks, eight at once, take about
  11 minutes. There is one way into a week, for the first start, our own restart, a server that went away and a
  broken stream alike: rebuild the books and a new strategy from the snapshot, the event log and the journal, then
  run the loop. An unreachable server is retried every second for as long as it takes; both loops skip an event they
  have handled. The client sends at most 50 actions a request and waits for the tokens that the `RateLimit-*`
  headers name.

**What the harness guarantees in the final** (`--final`): it never exits on an error. Any error is printed and the
week is rebuilt a second later. The live loop keeps one request in flight while the outbox collects: quotes go
first, with at most 10 other actions in a request, so a burst of 31 requests is quoted in about two round trips and
a tick of 150 reprices never holds a quote back. A stream that closes before the end of the week, or that holds back
an event the server had a second earlier (a half-open socket), causes a rebuild. A strategy that does not build stops
`--final` and `--board` before the start; a practice week declines everything and says so at the end.

**Write a strategy** in its own folder, `strategies/<name>/`, and add one line to `strategies/index.ts`. A
strategy extends `Strategy` from `strategy.ts`: it is built from the driver list, the map, the level and its
params (defaults in its `StrategyKind`), and answers these calls, each with a read-only view of the books and the clock:

- `quote(request, books)`: a price for each option offered, or null to decline.
- `gig(need, books)`: the stops, audience and fee schedule for some legs of an order, or several such gigs that share
  them. `need.why` says why (a won order, a change, a split trade-in, a retry after `need.failed`, a repost or an
  urgent reprice of `need.previous`, or `lost`: a car that no gig carries). The desk posts every plan, and posts any
  leg of `need.legs` that no plan carries with the starter's gig; an empty answer counts as a fault.
- `hold(need, books)`, optional: true to wait with the gig for these legs, as when the cars may join a gig with cars
  still to come. The desk asks again on every sweep.
- `observe(event, books)`: every event of the week, before the desk acts on it.
- `sent(action, result, books)`, optional: every action the desk sent for the strategy (quote, post, reprice,
  withdraw, offer), as it went out (also the safe one that replaced an invalid answer), with the world's answer: `ok`
  with the gig id, or the refusal. It tells which plans became gigs and which quotes went out.
- After a restart the harness builds a new strategy and feeds it the event log through `observe` and the journal
  through `sent`, merged in order, with `books.now` at each line's minute and `books.posts` holding every gig of the
  snapshot, finished ones too. Keep the state rebuildable from these two calls.
- `tick(books)` every `every` minutes, optional: any actions (reprice, withdraw, direct offer, combined gig).
- `summary()`: one line printed at the end of the week.

**Compare strategies** with `pnpm bench`. It plays each strategy on each seed at one level, one week after another,
saves every week, and prints a table of margin, revenue, orders won, on-time share and ranked for each strategy and
seed, with each strategy's mean; it writes the same as a CSV to `out/bench-ts-<date>-<time>.csv` (`--csv` names
another file). A strategy can carry params: `<name>:key=value,key=value`, or a JSON file in place of a pair.
`--jobs <n>` plays up to n weeks at once on the one key (1 by default; leave practice slots for teammates, the team
holds eight), and their daily lines then mix in the output. `--key-env <NAME>` takes the Spread key from another variable, so two benches can run on two keys. Ctrl-C deletes
the world in play. A week that throws still prints the table of the weeks before it, then the error. It never plays a
ranking run or a final.

```sh
pnpm bench lean lean:target=0.26 --level 8 --seeds spread-1..spread-5
```

**Tune a strategy's params** with `pnpm tune`, a search by successive halving on practice weeks. A space file names
each param to search with a list of values or a range; the other params keep their defaults:

```json
{ "target": [0.24, 0.27, 0.3, 0.33], "capacity": { "min": 0.2, "max": 0.8 } }
```

A range is drawn evenly, or on a log scale with `"log": true` (its min above 0); a drawn number keeps three
significant digits, or is whole with `"int": true`. The candidates are drawn with a fixed seed, so the same space gives
the same candidates, and candidate `#0` is always the defaults.

```sh
pnpm tune lean --space space.json --holdout spread-6..spread-10 --dry   # the candidates and the rounds, no world
pnpm tune lean --space space.json --holdout spread-6..spread-10 --keys SPREAD_KEY,SPREAD_KEY_2
pnpm tune --resume out/tune-<date>-<time>.json --keys SPREAD_KEY,SPREAD_KEY_2   # go on with a stopped search
```

Every candidate (`--candidates`, 24) plays the first seed of `--seeds` (`spread-1..spread-5`); each round the best
share (`--keep`, 0.34) plays the next seed, until `--finalists` (3) are left, who play every seed that is left. With
24 candidates on 5 seeds that is 24 + 9 + 4 + 3 × 2 = 43 weeks. A candidate's score is its mean margin on the seeds
it played, minus €100M for each week under `--min-on-time` (0.93) or not ranked, so such a candidate never wins; the candidates of a
round have all played the same seeds. Each key of `--keys` (names of variables, `SPREAD_KEY` by default) plays one
world at a time, so two keys play two weeks side by side. The weeks are played and saved as in `pnpm bench`. A week
that throws puts its candidate out (`out` in the table); a refused key, full practice slots or the rate limit stops the
search. Ctrl-C deletes the worlds in play.

The state goes to `out/tune-<date>-<time>.json` after every week, and `--resume <file>` goes on from it without
replaying a week, with the settings of the file. After each round a table lists the candidates still in it, best first:
`Seeds` played, mean `Margin`, mean `On time`, `Under` (weeks under the minimum or not ranked) and the params that differ from the
defaults. At the end the best params go to `out/tune-<date>-<time>-best.json`, a `--params` file for `pnpm dispatch`,
with its mean margin and on-time share on the tuning seeds; with `--holdout`, the best and the defaults then play the
holdout seeds, and a last table shows both. Judge the params by the holdout, not by the tuning seeds they were picked on.

`pnpm dispatch`, `pnpm bench` and `pnpm tune` save every week they finish to `data/scrape/runs/`, with policy `ts-<strategy>` and
the strategy's params in `meta.json`, like `dispatch.py`
([`tools/README.md`](../tools/README.md)); `uv run python -m tools.db` adds the saved weeks to the database. The
scripts read `.env` when it exists, and otherwise the variables already set. To take a new kit version, download
`$SPREAD_URL/kit/spread-typescript.tar.gz` and replace the files in `vendor/spread-typescript/`.

The three scripts set `NODE_USE_ENV_PROXY=1`, so on Node 22.21+ `fetch` goes through `HTTPS_PROXY` when it is set, as in a
Claude Code cloud session, where the proxy swaps the placeholder `SPREAD_KEY` for the real key; `NODE_EXTRA_CA_CERTS`
must name the proxy's CA (cloud sessions set it). Without `HTTPS_PROXY` they connect straight to the server. `.npmrc`
turns on pnpm's `shell-emulator`, so the variable works on Windows too. The `--final` WebSocket stream does not go
through the proxy yet.

`dispatch.py`'s order handling (note reader, gig shape, admission's time rules, retries) is in `ops/` as pure
functions: see [its README](ops/README.md). The `lean` strategy uses it for every gig and for which options it quotes.
