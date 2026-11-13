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

Leave out `--env-file .env` where the two variables are already set, as in a Claude Code cloud session.

`--level` is 1 to 8 (the final is level 8). The same seed gives the same week, so compare two versions of the system
on the same seeds. `--board` plays a ranking run: each ranking world can be played once and its score stays on the
public rankings, so agree on it in the team first.

- `dispatch.py` is our system. It starts as a copy of the organisers' starter, formatted with ruff.
- `vendor/` holds the organisers' Python kit of 13 November as a wheel. uv installs it as the package `spread`: the
  API client, its types and the unchanged starter. To take a new kit version, replace the wheel and run `uv lock`.
- `tests/` holds fast tests that need no network: `uv run pytest`.

### Scrape weeks for an offline model

`scrape.py` plays practice weeks on many seeds at once and saves each week's raw data. `stats.py` turns saved weeks
into distributions, offline. Together they give the data for an offline model of the server.

```sh
uv run --env-file .env scrape.py --policy passive --levels 4,5,6,7,8 --seeds 20   # requests only: 10 requests a week
uv run --env-file .env scrape.py --policy explore --levels 8 --seeds 10            # random prices: dealer and driver answers
uv run stats.py out/scrape/passive out/scrape/explore                               # writes summary.json, prints the main numbers
uv run db.py out/scrape                                                             # loads saved weeks into out/spread.sqlite
```

`scrape.py` also adds each week to the SQLite database `out/spread.sqlite` as it finishes (`--db` to choose another
file, `--no-db` to skip it). `db.py` loads weeks that were saved without it; weeks already in the database are skipped.
Query it with any SQLite tool, for example `sqlite3 out/spread.sqlite "select kind, count(*) from events group by kind"`.
Tables, keyed by `week_id` (a row of `weeks`):

| Table | One row for each |
| --- | --- |
| `weeks` | week: seed, level, policy, explore ranges, score, events, requests, seconds |
| `events` | event, with `data` the event's JSON (read fields with `json_extract`); `gig_viewed` keeps only its columns |
| `requests`, `legs`, `options` | price request; car of a request, with the reveal's truth for won orders; delivery option, with our quote and whether the dealer took it |
| `orders`, `gigs`, `views` | won order at the end of the week; gig we posted; view of our gigs with the fee the driver saw |
| `drivers`, `ledger`, `forecasts` | driver at the start of the week; account line; snow forecast |
| `places`, `roads` | the map |

A passive week takes about 1.7 MB in the database, and a played week about 20 MB, most of it gig views. The week
folders hold the same data gzipped (about 0.1 MB and 2 MB), so the database can always be rebuilt from them.

`data/scrape/` holds the team's committed scrape as week folders: passive weeks on the seeds `scrape-1` to `scrape-30`
at levels 1 to 8, and explore weeks on `scrape-1` to `scrape-10` at level 8. Build the database and the summary from
it without the server:

```sh
uv run db.py data/scrape --db out/spread.sqlite
uv run stats.py data/scrape/passive data/scrape/explore --out out/summary.json
```

Policies:

- `passive` sends nothing and advances to the end at once. The week shows its price requests, forecasts and drivers.
- `starter` plays with the `Desk` of `dispatch.py`.
- `explore` plays like `starter`, but quotes every option at a random multiple of its list price (`--quote-range`,
  default 0.7 to 1.8) and pays each order's gigs a random multiple of the starter's fees (`--fee-range`, default 0.6
  to 1.6). The same seed draws the same multiples.

Seeds are `<--seed-prefix>-<n>`, default `scrape-1` and up. Each week goes to `out/scrape/<policy>/L<level>/<seed>/`
(`out/` is not committed): `events.jsonl.gz` (every event), `reveal.json.gz`, `snapshot.json.gz` (orders and gigs at
the end), `drivers.json.gz` (the driver list at the start), `score.json` and `meta.json`. A saved week is skipped, so
running the same command again resumes. `--workers` weeks run at once (default 4), and the scraper always leaves
`--keep-free` practice slots (default 2) for teammates. A week with a policy that acts takes about 2,000 requests: a
few minutes at 175 ms a request through a Claude Code cloud proxy. The scraper's client goes through `HTTPS_PROXY`
when one is set, so there the proxy adds the team key and `SPREAD_KEY` can be a placeholder.

`summary.json` has one entry per level and policy (`L8/explore`) and a catalogue of every event kind:

- `eventCatalogue`: for each kind, its count, its fields with their types and number ranges, the values of each
  enumeration (for example `visit_failed.reason`), and one example.
- `arrivalsPerHourOfWeek`: requests per hour from Monday 00:00, per week.
- `numbers`: quantiles of counts per week, request timing and distance, fees over list prices, gig views, minutes to
  booking, booked fee over the typical fee, drops, no-shows and late drivers per booking, lateness, and driver ratings.
- `counts`: shares of legs, option sets, note languages, private addresses, car types, failed-visit reasons, order
  status, and the truth of won cars from the reveal.
- `fits`: straight lines for list price against km, typical fee against drive minutes, and booked fee against the
  typical fee.
- `quoteResponse`: for bins of quote / list price, how often the dealer took the option and won the request.
- `driverHomeShare` and `ledger`: where drivers live, and money per week by account line.

### The baseline to beat

The unchanged starter on the seed `spread-1`. It quotes the list price, wins most cars and cannot find drivers for
them in time.

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

We measured these with the organisers' TypeScript starter, before we chose Python. They match the handbook to the
cent, and the handbook says that both starters play alike. The Python starter has not been run against the server
yet.

### Claude Code cloud environments

Variables belong to one cloud environment. Every session that starts in that environment gets them. Each environment
that works on this repository needs both variables in its settings:

- `SPREAD_URL=https://spread.bahnexpress.com`
- `SPREAD_KEY`, the real team key. The Python client connects straight to the server, so a placeholder with a network
  secret does not work.

## Working in parallel

Four of us work at once, each with our own agent. Every change goes issue → branch (or worktree) → PR, as described
in `AGENTS.md`.
