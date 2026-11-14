# junction2026

Our entry for **Spread** by Bahn at Junction 2026: a system that does a car transport dispatcher's job for one
simulated week in Finland. It quotes prices to dealers and posts gigs to freelance drivers through the Spread API.
The score is the gross margin in game euros, and a system is ranked only when at least 90% of its orders arrive on
time.

- Test finals: Saturday 14 November at 14:00 and at 20:00, Helsinki time. Each takes about 19 minutes.
- The final: Sunday 15 November at 08:00, Helsinki time. It takes about 34 minutes and is level 8.
- Our team's weeks, rankings and key: <https://spread.bahnexpress.com/team>

## Setup

Python 3.15 with [uv](https://docs.astral.sh/uv/), and Node 22.18+ with pnpm (no build step: Node runs `.ts` files).

```sh
uv sync        # Python and the organisers' kit; if it cannot find Python 3.15, run `uv self update` first
pnpm install   # Biome and TypeScript
cp .env.example .env   # then put the team key in SPREAD_KEY; .env is not committed
```

Add `--env-file .env` after `uv run` to read the key from `.env`. Leave it out where `SPREAD_URL` and `SPREAD_KEY`
are already set, as in a Claude Code cloud session ([`tools/README.md`](tools/README.md#claude-code-cloud-environments)).

## The systems

Several of us build dispatch systems in parallel; the team picks one for the final. Each plays a practice week with
`--level 1` to `8` and `--seed <text>`: the same seed gives the same week, so compare systems on the same seeds.

| System                                                             | Play a week                                                               |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `dispatch.py`, built from [`strategies/`](strategies/README.md)    | `uv run dispatch.py --level 8 --seed spread-1`                            |
| [Price ladder](strategies/price_ladder/README.md)                  | `uv run strategies/price_ladder/dispatch.py --level 8 --seed spread-1`    |
| [Ratchet](strategies/ratchet/README.md)                            | `uv run strategies/ratchet/dispatch.py --level 8 --seed spread-1`         |
| [Ceiling pricing](strategies/ceiling/README.md)                    | `uv run strategies/ceiling/dispatch.py --level 8 --seed spread-1`         |
| [Baseline](strategies/baseline/README.md), the organisers' starter | `uv run python strategies/baseline/baseline.py --level 8 --seed spread-1` |
| [TypeScript](src/README.md): a harness that plays one strategy     | `pnpm dispatch --strategy starter --level 8 --seed spread-1`              |

- `--final` plays our copy of a test final or of the final. `--board` plays a ranking run: each ranking world can be
  played once and its score stays on the public rankings, so agree on it in the team first.
- Compare two versions on the same seeds with the [seed bench](strategies/bench/README.md):
  `uv run python -m strategies.bench dispatch.py origin/main`.
- Play several of the changes built on `ceiling` in one system, and find the best mix, with the
  [tournament](strategies/tournament/README.md): `uv run python -m strategies.tournament --plan` shows what it
  would play.
- Every week played online is saved under `data/scrape/runs/`; commit the new folders with your PR.

## Where things are

| Folder                            | What it holds                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------- |
| [`docs/`](docs/README.md)         | The organisers' rules, handbook and API reference. Read the handbook first.     |
| [`tools/`](tools/README.md)       | Saving, loading, scraping and probing weeks; the SQLite database and its tables |
| [`analysis/`](analysis/README.md) | Derived tables, the hindsight oracle, the report and the offline replay         |
| `data/`                           | The saved weeks. The larger scrape is a release tarball (`tools/README.md`).    |
| `vendor/`                         | The organisers' kits of 13 November, unchanged: the Python wheel and TypeScript |

## Working on it

Four of us work at once, each with our own agent. Every change goes issue → branch → PR, as [`AGENTS.md`](AGENTS.md)
describes; its Commands list has every command. We do not write or run tests: check changes by reading them, with
`pnpm lint`, `pnpm check` and `uv run ruff check .`, and by comparing versions on practice weeks.
