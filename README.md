# Lean — a Spread dispatcher

Lean is our TypeScript entry for **Spread** by Bahn at Junction 2026.[^legacy] It autonomously dispatches car transport
for one simulated week in Finland: it quotes prices to dealers, hires freelance drivers, and manages every order until delivery.
The goal is gross margin in game euros, with at least 90% of orders delivered on time.

## What it does

- **Prices each request** with online demand and cost models that learn from the week's quotes and bookings, while
  accounting for delivery risk and the capacity consumed by another order.
- **Schedules driver fees** around drivers' planning time and each order's deadlines, then adjusts them when work
  becomes urgent or a gig expires.
- **Bundles compatible cars into chains** so one driver can complete several deliveries with less driving and lower
  fees.
- **Runs the whole operation** through a resilient harness that handles vehicle notes, serviceability, order changes,
  retries, and recovery from a saved event log and action journal.

The strategy lives in [`src/strategies/lean/`](src/strategies/lean/README.md). The detailed README there explains the
models, parameters, and measured results.

## Setup

You need **Node.js 22.18+** and **pnpm**. There is no build step: Node runs the TypeScript files directly.

```sh
pnpm install
cp .env.example .env
```

Put your Spread team key in `SPREAD_KEY` in `.env`. The default `SPREAD_URL` points to the Spread server.

## Run

```sh
# Play a repeatable level-8 practice week with lean (the default strategy)
pnpm dispatch --level 8 --seed spread-1

# Override a strategy parameter
pnpm dispatch --level 8 --seed spread-1 --set noise=0.26

# Compare parameter variants on the same seeds
pnpm bench lean lean:noise=0.26 --level 8 --seeds spread-1..spread-5
```

These commands play weeks on the Spread server and save completed weeks under `data/scrape/runs/`. See
[`src/README.md`](src/README.md) for all dispatch, benchmark, tuning, and recovery options. Ranking runs and finals
have their own flags; do not start one without the team's approval.

### Offline development

Run the local simulator instead of contacting the Spread server:

```sh
pnpm sim --port 8787
```

Then, in another terminal:

```sh
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim pnpm dispatch --level 8 --seed spread-1
```

The simulator is intended for rapid iteration and comparisons across several seeds, not for predicting server scores.
See [`sim/README.md`](sim/README.md) for its limitations and replay tools.

## Project map

| Path | Purpose |
| --- | --- |
| [`src/strategies/lean/`](src/strategies/lean/README.md) | The current pricing, fee, cost, and chaining strategy |
| [`src/harness/`](src/README.md) | Spread API loop, bookkeeping, validation, persistence, and recovery |
| [`src/ops/`](src/ops/README.md) | Note parsing, serviceability, timing, and gig construction |
| [`sim/`](sim/README.md) | Offline simulator, replay, and hindsight analysis |
| [`docs/spread/`](docs/spread/HANDBOOK.md) | Spread handbook, rules, and API reference |
| `data/scrape/runs/` | Recorded weeks used for analysis and model fitting |

## Contributing

Use `pnpm format`, `pnpm lint`, and `pnpm check` for formatting, linting, and type checking. The development workflow
and the full command list are in [`AGENTS.md`](AGENTS.md).

[^legacy]: The root `dispatch.py`, most of `strategies/`, and parts of `analysis/` and `tools/` are older Python code
    used to experiment with many dispatch strategies, including a Python port of lean. They are not the current
    product, although some analysis and recording tools still use them.
