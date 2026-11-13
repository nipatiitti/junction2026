# junction2026

Our entry for **Spread** by Bahn at Junction 2026: a system that does a car transport dispatcher's job for one
simulated week in Finland. It quotes prices to dealers and posts gigs to freelance drivers through the Spread API.
Everything about the challenge is linked from <https://spread.bahnexpress.com/llms.txt>.

## Challenge docs

Short versions of the Spread challenge documents (rules, handbook, API, judging) are in [`docs/`](docs/README.md).

## Stack

The dispatch system is Python 3.15, run with uv: `dispatch.py`, with tests in `tests/`. See
[Spread challenge](#spread-challenge) for its commands.

The repository is also a plain TypeScript project on Node 22.18+ (no build step: Node runs `.ts` files directly), with
pnpm, Biome, and `node --test`. TypeScript code lives in `src/`, which has no code yet; tests sit next to the code as
`*.test.ts`.

```sh
pnpm install
pnpm check   # type check
pnpm lint    # lint and format check, no writes
pnpm format  # format, organise imports and apply safe lint fixes
pnpm test    # all tests
node --test src/path/to/file.test.ts   # one test file
```

In VS Code, install the recommended Biome extension to format on save.

## Spread challenge

The score is the gross margin in game euros. A system is ranked only when at least 90% of its orders arrive on time.

- Test finals: Saturday 14 November at 14:00 and at 20:00, Helsinki time. Each takes about 19 minutes.
- The final: Sunday 15 November at 08:00, Helsinki time. It takes about 34 minutes and is level 8.
- Read `docs/spread/HANDBOOK.md` first. `RULES.md` and `API.md` are next to it.
- Our team's weeks, rankings and key: https://spread.bahnexpress.com/team

### Setup

The system is Python, run with [uv](https://docs.astral.sh/uv/) on Python 3.15. `uv sync` installs Python and the
packages. If it cannot find Python 3.15, update uv first (`uv self update`).

The kit reads two variables. Copy `.env.example` to `.env` and put the team key in `SPREAD_KEY`. `.env` is not
committed.

```sh
SPREAD_URL=https://spread.bahnexpress.com
SPREAD_KEY=<the team key>
```

### Play a practice week

```sh
uv run --env-file .env dispatch.py --level 8 --seed spread-1   # a whole practice week with our system
uv run --env-file .env spread-starter --level 8 --seed spread-1 # the same week with the organisers' unchanged starter
uv run --env-file .env spread-reveal-csv <world id>             # write an ended week and its reveal to CSV files
uv run --env-file .env dispatch.py --final                      # play our copy of a test final or of the final
```

To compare two versions on the same seeds, use the seed bench: `uv run --env-file .env python -m strategies.bench
dispatch.py origin/main` plays `spread-1` to `spread-5` at level 8 with both and prints one table. See
[`strategies/bench/README.md`](strategies/bench/README.md).

Leave out `--env-file .env` where the two variables are already set, as in a Claude Code cloud session.

`--level` is 1 to 8 (the final is level 8). The same seed gives the same week, so compare two versions of the system
on the same seeds. `--board` plays a ranking run: each ranking world can be played once and its score stays on the
public rankings, so agree on it in the team first.

- `dispatch.py` is our system. It starts as a copy of the organisers' starter, formatted with ruff.
- `vendor/` holds the organisers' Python kit of 13 November as a wheel. uv installs it as the package `spread`: the
  API client, its types and the unchanged starter. To take a new kit version, replace the wheel and run `uv lock`.
- `tests/` holds fast tests that need no network: `uv run pytest`.

### The baseline to beat

The unchanged starter on the seed `spread-1`. It quotes the list price, wins most cars and cannot find drivers for
them in time.

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

They match the handbook to the cent. `dispatch.py`, still unchanged from the starter, gives the same level 8 result.
We measured levels 6 and 7 with the organisers' TypeScript starter, before we chose Python; the handbook says that
both starters play alike.

### Claude Code cloud environments

Variables belong to one cloud environment. Every session that starts in that environment gets them. Each environment
that works on this repository needs both variables in its settings:

- `SPREAD_URL=https://spread.bahnexpress.com`
- `SPREAD_KEY`, the real team key. The Python client connects straight to the server, so a placeholder with a network
  secret does not work.

## Working in parallel

Four of us work at once, each with our own agent. Every change goes issue → branch (or worktree) → PR, as described
in `AGENTS.md`.
