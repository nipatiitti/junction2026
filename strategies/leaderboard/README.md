# Leaderboard

Plays every strategy in the repository as a live practice week on the server, on one seed (`spread-1` at level 8 by
default), and draws one bar chart of the margins. Every number comes from online play: the tool never reads the saved
weeks of `out/spread.sqlite`.

When you add a strategy or change one, run it again: it plays only the strategies that are new or whose code changed
since their last online week, and keeps the others' results.

It plays practice weeks only, never a ranking run (`--board`) or a final. A leaderboard run is **one online run**, like
the bench: see [`AGENTS.md`](../../AGENTS.md) before you start one.

## Run it

From the repository root, with `SPREAD_URL` and `SPREAD_KEY` in `.env`:

```sh
uv run --env-file .env python -m strategies.leaderboard            # play what is new or changed, then draw
uv run python -m strategies.leaderboard --plan                     # what would be played: plays nothing
uv run python -m strategies.leaderboard --no-play                  # only redraw the chart
uv run --env-file .env python -m strategies.leaderboard --only all_in,soft_top   # replay these two
```

Then open `out/leaderboard.html`.

| Option      | Default                | What it does                                                                    |
| ----------- | ---------------------- | ------------------------------------------------------------------------------- |
| `--seed`    | `spread-1`             | The practice seed. Each seed and level keeps results of its own.                |
| `--level`   | `8`                    | The practice level, 1 to 8.                                                     |
| `--jobs`    | `4`                    | Weeks played at once. Four leaves half of the team's eight slots free.          |
| `--only`    | none                   | Play only these strategies, comma-separated, also when their code is as before. |
| `--fresh`   | off                    | Play every strategy again.                                                      |
| `--plan`    | off                    | Print the new and changed strategies, and play nothing.                         |
| `--no-play` | off                    | Redraw the chart from the results, and play nothing.                            |
| `--html`    | `out/leaderboard.html` | Where to write the chart.                                                       |

## The strategies

The root `dispatch.py`, every `strategies/<folder>/dispatch.py`, and the few systems with another entry file
(`OTHER_ENTRIES` in `leaderboard.py`: the starter `baseline`, `baseline_ladder`, `baseline_tiers` and the three
`admission_scenarios`). A new folder with a `dispatch.py` is picked up on its own.

## What counts as changed

Each result keeps a fingerprint of the strategy's code: a hash of its entry file and of every file of this repository
that it imports, directly or through other modules (the root `dispatch.py`, `strategies/…`, `tools/…`), plus the data
files (such as `priors.json`) in the folders of those modules. READMEs do not count. So a change to the root
`dispatch.py` or to a shared module such as `strategies/fees` replays every strategy built on it, and a change inside
one strategy's folder replays that strategy and those that import it.

## The results and the chart

The online results are in `results/L<level>-<seed>.json`, one entry per strategy with its world id, when it was played,
its fingerprint and the server's score. Commit this file, and the weeks under `data/scrape/runs`, with your PR, so the
next run on any machine replays only what changed. Each week is written to the file as soon as it ends, so a run that
stops halfway keeps what it played; run it again for the rest. A strategy that fails is reported at the end and played
again on the next run; it does not stop the others.

The chart has one bar per strategy, best margin first. Blue bars are ranked weeks (90%+ on time); hatched grey bars are
unranked, so their margin does not count; the orange bar is the root `dispatch.py`, the reference. A dashed outline marks
a strategy whose code changed after its week. Hover a bar for its orders, on-time share and world id. The table under
the chart has the same numbers.

**One seed proves little.** Read the order as a guide; compare the leaders on more seeds with
[`strategies.bench`](../bench/README.md).
