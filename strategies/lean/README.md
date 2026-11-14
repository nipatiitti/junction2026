# Lean, in Python

A port of the TypeScript [`lean`](../../src/strategies/lean/README.md) strategy and of the harness it plays in
([`src/harness/`](../../src/README.md)), so the Python tools can play it: `strategies.bench`,
`tools.roster_tournament` and the Python side of the leaderboard pick up `strategies/lean/dispatch.py` on their own.
Issue #323.

It decides exactly as the TypeScript `lean`. On the offline simulator, seven seeds (`spread-1`, `spread-2`,
`spread-3` with `--set`, `spread-7`, `nov-3`, `nov-8` and two `sweep-*` packs) gave the same week action for action:
every quote, post, withdrawal and reprice at the same minute with the same prices and fees, about 10,500 actions in
all. A week takes about 4 seconds there, as the TypeScript one does.

## Run it

From the repository root:

```sh
uv run strategies/lean/dispatch.py --level 8 --seed spread-1
uv run strategies/lean/dispatch.py --seed spread-1 --set target=0.4 --set chainBid=true
uv run python -m strategies.bench strategies/lean/dispatch.py strategies/all_in/dispatch.py --seeds spread-1..5
```

`--set key=value` overrides one param, with the names and types of `index.ts`; `--board` and `--final` play a
ranking run and the final, as the root `dispatch.py` does. Weeks save with the policy `lean` (the TypeScript weeks are
`ts-lean`), with the strategy and every param under `settings` in `meta.json`.

Offline, against the simulator, with nothing saved:

```sh
pnpm sim --port 8787
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim SPREAD_RECORD=0 uv run strategies/lean/dispatch.py --seed spread-1
```

## Files

| File          | Port of                                        | What it holds                                                          |
| ------------- | ---------------------------------------------- | ---------------------------------------------------------------------- |
| `dispatch.py` | `src/dispatch.ts`, `src/harness/week.ts`       | The command line, the recorder, the final's wait                       |
| `harness.py`  | `src/harness/{desk,guard,journal,loops}.ts`    | The books, the order mechanics, the guard, the journal, the two loops  |
| `strategy.py` | `src/strategies/lean/index.ts`                 | `Lean` and its `Params`: the price, the cost, the gig, the books       |
| `demand.py`   | `demand.ts`                                    | The win model learned during the week                                  |
| `supply.py`   | `supply.ts`                                    | The booking cost learned by place                                      |
| `outlook.py`  | `outlook.ts`, with `order.json` copied         | The order model: an order's cost and its chance to be late             |
| `fees.py`     | `fees.ts`                                      | The stepped, slow and fast fee schedules                               |
| `chains.py`   | `chains.ts`                                    | The chain search                                                       |
| `planner.py`  | `planner.ts`                                   | The chain book                                                         |
| `offers.py`   | `offers.ts`                                    | Direct offers (off)                                                    |
| `ops.py`      | `src/ops/{calendar,map,windows,features,gig,serve}.ts` | Hours, roads, stop windows, gig shapes, whether an option can arrive |
| `note.py`     | `src/ops/note.ts`                              | The note reader                                                        |
| `js.py`       |                                                | JavaScript's rounding, 32-bit arithmetic and overflowing `exp`         |

The strategy subclasses [`strategies/strategy.py`](../strategy.py)'s `Strategy`, with the constructor
`(roster, world_map, level=8, params=None)`; the desk gives it the books as `strategy.books`.

## What differs from the TypeScript

- **Rounding and draws.** `js.py` rounds half up as `Math.round` does, and the per-gig raise jitter uses the same
  seeded generator (mulberry32 in 32-bit arithmetic), so the fee schedules match to the cent.
- **The chain search** judges a path without the search for its last start, and finds that start for the chains it
  chooses only. The choice never reads it, so the chains are the same, in much less time.
- **The harness is synchronous.** It sends when the TypeScript one waits for an answer; live it sends the quotes
  first, as the TypeScript one does.
- **Time budgets** hold in the final only. In a practice week a slow call counts as `late` and its answer is kept.
- **The safe gig**, when the strategy fails, is the ops' gig shape with the starter's fees.
- **`order.json`** is a copy: change both when the order model is refitted.

The rebuild after a restart (snapshot, event log and journal in `out/journal/`) is ported but has not been played:
practice weeks start fresh, and the simulator has no final.
