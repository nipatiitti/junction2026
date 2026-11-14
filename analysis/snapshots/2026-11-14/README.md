# Analysis snapshot of 2026-11-14

The results of one run of the analysis on every saved week under `data/scrape`, committed so that they can be read
without building the database. The files that a checkout generates itself still go to `out/`, which is not committed.

Built at commit `1d79316` from 478 weeks: 472 saved runs in `data/scrape/runs` (462 at level 8 from 61 policies, 10 at
level 1), 5 passive weeks and 1 starter week. The build had no probe rows (`out/probe` was empty), so the probe
sections are empty and the oracle's quote side uses brackets only. Nothing was played online.

| File          | What it is                                                             | Built by                                      |
| ------------- | ---------------------------------------------------------------------- | --------------------------------------------- |
| `report.html` | The overview report: experiments, dealers, drivers and economics       | `uv run python -m analysis.report --no-serve` |
| `replay.html` | Every strategy of that commit replayed on the saved weeks, with charts | `uv run python -m analysis.replay --no-serve` |
| `replay.csv`  | The replay's numbers: one row per week, strategy and metric            | the same command                              |
| `oracle.json` | The hindsight oracle: each week's account and the bounds on its margin | `uv run python -m analysis.oracle`            |

The two pages are single files that need no network: open them in a browser from a checkout.
[`analysis/README.md`](../../README.md) says how to read each of the four.

## Build it again

```sh
uv run python -m tools.db                     # every committed week into out/spread.sqlite
uv run python -m analysis.facts               # the derived tables
uv run python -m analysis.oracle              # out/oracle.json
uv run python -m analysis.report --no-serve   # out/report.html
uv run python -m analysis.replay --no-serve   # out/replay.html and out/replay.csv
```

Then copy the four files from `out/` into a new folder here, named by the date, with a copy of this file. The whole
build takes about five minutes, most of it the replay.
