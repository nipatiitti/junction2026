# Leaderboard

Plays every strategy in the repository, Python and TypeScript, as a live practice week on the server, on one seed
(`spread-1` at level 8 by default), and draws one bar chart of the margins. Every number comes from online play: the
tool never reads the saved weeks of `out/spread.sqlite`.

When you add a strategy or change one, run it again: it plays only the strategies that are new or whose code changed
since their last online week, and keeps the others' results.

It plays practice weeks only, never a ranking run (`--board`) or a final. A leaderboard run is **one online run**, like
the bench: see [`AGENTS.md`](../../AGENTS.md) before you start one.

## Before the first run

Run every command from the repository root. The online commands read `SPREAD_URL` and `SPREAD_KEY` from `.env`:

```sh
cp .env.example .env    # then put the team key after SPREAD_KEY=
uv sync                 # the Python packages
```

The TypeScript strategies run with `node` (22.18 or later); they need no `pnpm install`.

## Examples

See what a run would play, without playing anything (no key needed):

```sh
uv run python -m strategies.leaderboard --plan
```

Play every new or changed strategy, Python and TypeScript, then draw the chart:

```sh
uv run --env-file .env python -m strategies.leaderboard
```

Play only the TypeScript strategies that are new or changed:

```sh
uv run --env-file .env python -m strategies.leaderboard --language typescript
```

Play only the Python strategies that are new or changed:

```sh
uv run --env-file .env python -m strategies.leaderboard --language python
```

Play some strategies again, also when their code is unchanged (Python by folder name, TypeScript as `ts:<name>`):

```sh
uv run --env-file .env python -m strategies.leaderboard --only all_in,ts:lean
```

Play every strategy again from scratch:

```sh
uv run --env-file .env python -m strategies.leaderboard --fresh
```

Redraw the chart from the saved online results, without playing (no key needed):

```sh
uv run python -m strategies.leaderboard --no-play
```

Play another seed or level; each keeps its own results:

```sh
uv run --env-file .env python -m strategies.leaderboard --seed spread-2 --level 8
```

Then open `out/leaderboard.html` in a browser. The same table is printed at the end of every run.

## Options

| Option       | Default                | What it does                                                                     |
| ------------ | ---------------------- | -------------------------------------------------------------------------------- |
| `--seed`     | `spread-1`             | The practice seed. Each seed and level keeps results of its own.                 |
| `--level`    | `8`                    | The practice level, 1 to 8.                                                      |
| `--jobs`     | `4`                    | Weeks played at once. Four leaves half of the team's eight slots free.           |
| `--language` | `all`                  | `python` or `typescript`: play only those. The chart still shows every strategy. |
| `--only`     | none                   | Play only these strategies, comma-separated, also when their code is as before.  |
| `--fresh`    | off                    | Play every strategy again.                                                       |
| `--plan`     | off                    | Print the new and changed strategies, and play nothing.                          |
| `--no-play`  | off                    | Redraw the chart from the results, and play nothing.                             |
| `--html`     | `out/leaderboard.html` | Where to write the chart.                                                        |

## The strategies

- **Python**: the root `dispatch.py`, every `strategies/<folder>/dispatch.py`, and the few systems with another entry
  file (`OTHER_ENTRIES` in `leaderboard.py`: the starter `baseline`, `baseline_ladder`, `baseline_tiers` and the three
  `admission_scenarios`). A week is `python <file> --level 8 --seed spread-1`. A new folder with a `dispatch.py` is
  picked up on its own.
- **TypeScript**: every strategy in the registry `src/strategies/index.ts`, labelled `ts:<name>`. A week is
  `node src/dispatch.ts --strategy <name> --level 8 --seed spread-1`, as `pnpm dispatch` plays it. A new strategy is
  picked up once it has its line in the registry.

Both save their weeks to `data/scrape/runs`, as every online run does.

## What counts as changed

Each result keeps a fingerprint of the strategy's code: a hash of its entry file and of every file of this repository
that it imports, directly or through other modules, plus the data files (such as `priors.json`) in the
folders of the strategy modules it reaches. READMEs and the vendored kits in `vendor/` do not count.

- Python: a change to the root `dispatch.py` or to a shared module such as `strategies/fees` replays every strategy
  built on it; a change inside one strategy's folder replays that strategy and those that import it.
- TypeScript: the harness (`src/dispatch.ts` and what it imports, such as `src/harness/` and `src/models/`) counts
  for every TypeScript strategy; a strategy's own folder, and what it imports, counts for that strategy. The registry
  imports every strategy, but that does not tie them together: a change in `src/strategies/lean/` replays `ts:lean`
  only. A JSON file read with `new URL('…', import.meta.url)` counts too, such as `src/params/quote.json`. A strategy
  defined in the registry itself, as a variant of another one's params, also counts the registry file.

## The results and the chart

The online results are in `results/L<level>-<seed>.json`, one entry per strategy with the command it played, its world
id, when it was played, its fingerprint and the server's score. Commit this file, and the weeks under
`data/scrape/runs`, with your PR, so the next run on any machine replays only what changed. Each week is written to the
file as soon as it ends, so a run that stops halfway keeps what it played; run it again for the rest. A strategy that
fails is reported at the end and played again on the next run; it does not stop the others.

The chart has one bar per strategy, best margin first. Blue bars are ranked weeks (90%+ on time); hatched grey bars are
unranked, so their margin does not count; the orange bar is the root `dispatch.py`, the reference. A dashed outline
marks a strategy whose code changed after its week. The axis spans the ranked weeks: a deeper loss is cut at the left
edge and labelled with its full value. Hover a bar for its orders, on-time share and world id. The table under the
chart has the same numbers.

**One seed proves little.** Read the order as a guide; compare the leaders on more seeds with
[`strategies.bench`](../bench/README.md) or `pnpm bench`.
