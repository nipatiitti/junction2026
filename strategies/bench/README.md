# Seed bench

Plays the same practice weeks with one or two versions of the system and prints one table, so you can tell whether a
change is better. One seed proves little: a change to the system changes the rest of the week. Compare on several
seeds, the same seeds for both versions.

The bench plays practice weeks only. It never plays a ranking run (`--board`) or a final (`--final`).

## Run it

From the repository root, with `SPREAD_URL` and `SPREAD_KEY` set (add `--env-file .env` after `uv run` to read them
from `.env`):

```sh
uv run python -m strategies.bench                        # dispatch.py on spread-1 to spread-5 at level 8
uv run python -m strategies.bench dispatch.py origin/main # this branch against main, on the same seeds
uv run python -m strategies.bench --level 7 --seeds spread-1..spread-10,study-3
uv run python -m strategies.bench my_copy.py dispatch.py --jobs 4 --csv out/my-copy.csv
```

| Option    | Default                | What it does                                                                     |
| --------- | ---------------------- | -------------------------------------------------------------------------------- |
| `VERSION` | `dispatch.py`          | One or more versions to play (see below). The first is compared with the others. |
| `--level` | `8`                    | The practice level, 1 to 8. The final is level 8.                                |
| `--seeds` | `spread-1..spread-5`   | Seeds, comma-separated. `spread-1..spread-5` and `spread-1..5` are ranges.       |
| `--jobs`  | `8`                    | Weeks played at once, 1 to 8. Lower it when teammates are playing too.           |
| `--csv`   | `out/bench-<time>.csv` | Where to write the results as CSV.                                               |

## Versions

A version is either:

- a Python file, such as `dispatch.py` or a copy of it: the bench runs `python <file> --level <level> --seed <seed>`;
- a git ref, such as `origin/main`, a branch or a commit: the bench checks it out into a temporary worktree and plays
  its `dispatch.py`. `<ref>:<file>` plays another file of that ref, such as `origin/main:strategies/x.py`.

Run `git fetch origin` first so that `origin/main` is current. A version runs with this checkout's Python packages.

A version must print `Practice world <id>, level <level>.` on its first line, as `dispatch.py` and the organisers'
starter do. The bench reads the world id from it, and reads the score from the server when the week ends.

## The table

One line for each seed and version, then the totals of each version, then how the first version compares with each
other one:

| Column        | Meaning                                                                                        |
| ------------- | ---------------------------------------------------------------------------------------------- |
| Margin        | The gross margin at the end of the week: the score.                                            |
| Orders        | The orders won.                                                                                |
| On time       | The share of the orders delivered on time. The total is over all orders of all weeks.          |
| Not delivered | The share of the orders never delivered. The total is over all orders of all weeks.            |
| Ranked        | Whether the week counts for the rankings: at least 90% on time. The total counts ranked weeks. |

The last line reads, for example, `dispatch.py against origin/main: margin +€12,345.67 in total, higher on 4 of 5
seeds; ranked on 5 against 3.`

The CSV has the same rows, plus the level, the world id of each week and the revenue. Shares are fractions (0.9550).
Paste it into a PR to show a change's effect.

## Practice slots

A team holds at most 8 practice worlds that have not ended, so the bench plays at most 8 weeks at once. When all slots
are taken, for example by a teammate, a week waits 15 seconds and tries again, for up to 10 minutes.

When a week stops on an error, the bench stops the other weeks and prints the last lines of the one that failed. On an
error or Ctrl-C, each week that has not ended has its world deleted, so no slot is left held. Ended weeks stay in the
team's list: you can still reveal them with `uv run spread-reveal-csv <world id>`.

## Tests

```sh
uv run pytest strategies/bench
```

They build the table and the CSV from fake scores and parse seed lists. They do not play against the server.
