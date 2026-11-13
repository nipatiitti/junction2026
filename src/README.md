# The TypeScript system

[`BRIEF.md`](BRIEF.md) is the design that this system is being built to.

The same kit exists for TypeScript, so half of the team can work there. `vendor/spread-typescript/` holds the
organisers' TypeScript kit of 13 November, unchanged: the client (`spread.ts`), its types, the starter and
`reveal-csv.ts`. Lint and format skip `vendor/`. `src/dispatch.ts` is our TypeScript system: a harness
that plays a week with one strategy. The `starter` strategy decides exactly as the organisers' starter, so it gives the starter's
[baseline](../strategies/baseline/README.md).

```sh
pnpm dispatch --level 8 --seed spread-1   # a whole practice week with the starter strategy
pnpm dispatch --strategy starter --set markup=1.3 --seed spread-1   # another strategy or other params
pnpm starter --level 8 --seed spread-1    # the same week with the organisers' unchanged starter
pnpm reveal-csv <world id>                # write an ended week and its reveal to CSV files
pnpm dispatch --final                     # play our copy of a test final or of the final
```

`--strategy <name>` picks the strategy (`starter` by default). `--params <file>` overrides its params with the values
of a JSON file, and `--set key=value` overrides one; both can be given more than once, and a key that the strategy
does not have is an error. `--board` plays a ranking run and `--final` the final, as before.

**The harness** (`harness/`) does everything that is not a decision, so a strategy does not know whether a
practice week (`advance`) or a final (the event stream) runs:

- `desk.ts` keeps the books (requests, orders, gigs, booked gigs, deadline warnings) and rebuilds them from the
  snapshot and the event log after a restart, so no quote or gig goes twice. It does the order mechanics: it posts a
  won order, posts again after a failed visit, withdraws and posts again after a change, reposts after `gig_expired`,
  reprices after the deadline warning, and splits a trade-in that is refused as one gig.
- `guard.ts` runs every strategy call within a time budget (1.5 s for a quote). On an error or a late answer the desk
  declines the request (10 times the list price, or no quote up to level 3) or posts the starter's gig, counts it, and
  goes on. A refused action is counted, never thrown. The end of a week prints both counts.
- `loops.ts` holds the practice and the live loop, `week.ts` plays one week and saves it. There is one way into a
  week, for the first start, our own restart and a server that went away alike: rebuild the books and a new strategy
  from the snapshot and the event log, then run the loop. An unreachable server is retried every second for as long
  as it takes. The client sends at most 50
  actions a request and waits for the tokens that the `RateLimit-*` headers name.

**Write a strategy** in its own folder, `strategies/<name>/`, and add one line to `strategies/index.ts`. A
strategy extends `Strategy` from `strategy.ts`: it is built from the driver list, the map, the level and its
params (defaults in its `StrategyKind`), and answers these calls, each with a read-only view of the books and the clock:

- `quote(request, books)`: a price for each option offered, or null to decline.
- `gig(need, books)`: the stops, audience and fee schedule for some legs of an order. `need.why` says why (a won
  order, a change, a split trade-in, a retry after `need.failed`, a repost or an urgent reprice of `need.previous`).
- `observe(event, books)`: every event of the week, before the desk acts on it. After a restart the harness builds a
  new strategy and feeds it the whole event log, so keep the state rebuildable from the events.
- `tick(books)` every `every` minutes, optional: any actions (reprice, withdraw, direct offer, combined gig).
- `summary()`: one line printed at the end of the week.

**Compare strategies** with `pnpm bench`. It plays each strategy on each seed at one level, one week after another,
saves every week, and prints a table of margin, revenue, orders won, on-time share and ranked for each strategy and
seed, with each strategy's mean; it writes the same as a CSV to `out/bench-ts-<date>-<time>.csv` (`--csv` names
another file). A strategy can carry params: `<name>:key=value,key=value`, or a JSON file in place of a pair.
`--key-env <NAME>` takes the Spread key from another variable, so two benches can run on two keys. Ctrl-C deletes
the world in play. It never plays a ranking run or a final.

```sh
pnpm bench starter starter:markup=1.3 --level 8 --seeds spread-1..spread-5
```

`pnpm dispatch` and `pnpm bench` save every week they finish to `data/scrape/runs/`, with policy `ts-<strategy>` and
the strategy's params in `meta.json`, like `dispatch.py`
([`tools/README.md`](../tools/README.md)); `uv run python -m tools.db` adds the saved weeks to the database. The
scripts read `.env` when it exists, and otherwise the variables already set. To take a new kit version, download
`$SPREAD_URL/kit/spread-typescript.tar.gz` and replace the files in `vendor/spread-typescript/`.

The three scripts set `NODE_USE_ENV_PROXY=1`, so on Node 22.21+ `fetch` goes through `HTTPS_PROXY` when it is set, as in a
Claude Code cloud session, where the proxy swaps the placeholder `SPREAD_KEY` for the real key; `NODE_EXTRA_CA_CERTS`
must name the proxy's CA (cloud sessions set it). Without `HTTPS_PROXY` they connect straight to the server. `.npmrc`
turns on pnpm's `shell-emulator`, so the variable works on Windows too. The `--final` WebSocket stream does not go
through the proxy yet.

The quote side of the brief's design (win probability, level learning, expected-profit pricing) is in
`models/quote/`, with its priors in `params/quote.json`: see [its README](models/quote/README.md).

The fee and capacity side (booking hazard, fee schedule solver, fee extras, `lambda` and `mu`) is in `models/fees/`,
with its priors in `params/fees.json`: see [its README](models/fees/README.md).

`dispatch.py`'s order handling (note reader, gig shape, admission's time rules, retries) is in `ops/` as pure
functions: see [its README](ops/README.md).

The `bidprice` strategy (`strategies/bidprice/`) joins the three: it quotes at the expected cost of moving the car and
posts each gig with the fee schedule from the same function. See [its README](strategies/bidprice/README.md).
