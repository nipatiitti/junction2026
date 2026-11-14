# Lean, in Python

A port of the TypeScript [`lean`](../../src/strategies/lean/README.md) strategy and of the harness it plays in
([`src/harness/`](../../src/README.md)), so the Python tools can play it: `strategies.bench`,
`tools.roster_tournament` and the Python side of the leaderboard pick up `strategies/lean/dispatch.py` on their own.
Issue #323.

**Keep the two in step.** A change to either version gets an entry in [`LEAN_CHANGELOG.md`](../../LEAN_CHANGELOG.md)
in the same PR, which also says how to check that both still play the same week.

It decides exactly as the TypeScript `lean`. On the offline simulator, seven seeds (`spread-1`, `spread-2`,
`spread-3` with `--set`, `spread-7`, `nov-3`, `nov-8` and two `sweep-*` packs) gave the same week action for action:
every quote, post, withdrawal and reprice at the same minute with the same prices and fees, about 10,500 actions in
all. A week takes about 4 seconds there, as the TypeScript one does.

On the server it played the six roster tournament seeds (`tour-r1-*`, `tour-r2-*`) as the TypeScript `lean` did, to
the cent: the same orders won at the same prices and the same bookings at the same fees, all six weeks ranked.

| Seed               | TypeScript `lean` | Python `lean` | Orders | On time | `all_in`   |
| ------------------ | ----------------: | ------------: | -----: | ------: | ---------: |
| `tour-r1-ff2bb5ca` |        €12,770.36 |    €12,770.36 |    352 |   98.3% | €11,122.95 |
| `tour-r1-d0cceb91` |        €13,361.56 |    €13,361.56 |    367 |   97.3% | €10,428.12 |
| `tour-r2-8e605453` |        €17,049.26 |    €17,049.26 |    385 |   97.1% | €12,972.30 |
| `tour-r2-cb24a8ee` |        €22,645.05 |    €22,645.05 |    421 |   97.1% | €19,633.53 |
| `tour-r2-32a6c4eb` |        €12,465.03 |    €12,465.03 |    356 |   97.5% |  €8,874.16 |
| `tour-r2-3dcdedfe` |        €12,266.89 |    €12,266.89 |    332 |   98.5% | €10,980.48 |
| **Mean**           |       **€15,093** |   **€15,093** |    369 |   97.6% | **€12,335** |

Against `all_in` on the same seeds: +€2,758 a week (standard error €445), ahead on all six.

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
