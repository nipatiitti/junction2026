# The TypeScript system

[`BRIEF.md`](BRIEF.md) is the design that this system is being built to.

The same kit exists for TypeScript, so half of the team can work there. `vendor/spread-typescript/` holds the
organisers' TypeScript kit of 13 November, unchanged: the client (`spread.ts`), its types, the starter and
`reveal-csv.ts`. Lint and format skip `vendor/`. `src/dispatch.ts` is our TypeScript system. It is still a copy of the
starter that imports the vendored client and saves its weeks, so it gives the starter's
[baseline](../strategies/baseline/README.md).

```sh
pnpm dispatch --level 8 --seed spread-1   # a whole practice week with our TypeScript system
pnpm starter --level 8 --seed spread-1    # the same week with the organisers' unchanged starter
pnpm reveal-csv <world id>                # write an ended week and its reveal to CSV files
pnpm dispatch --final                     # play our copy of a test final or of the final
```

`pnpm dispatch` saves every week it finishes to `data/scrape/runs/`, like `dispatch.py`
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
