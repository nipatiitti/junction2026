# junction2026

Our entry for **Spread** by Bahn at Junction 2026: a system that does a car transport dispatcher's job for one
simulated week in Finland. It quotes prices to dealers and posts gigs to freelance drivers through the Spread API.
Everything about the challenge is linked from <https://spread.bahnexpress.com/llms.txt>.

## Challenge docs

Short versions of the Spread challenge documents (rules, handbook, API, judging) are in [`docs/`](docs/README.md).

## Stack

The dispatch system is Python 3.15, run with uv: `dispatch.py`. See [Spread challenge](#spread-challenge) for its
commands.

The repository is also a plain TypeScript project on Node 22.18+ (no build step: Node runs `.ts` files directly), with
pnpm and Biome. Our TypeScript dispatch system is `src/dispatch.ts`; see
[Play a practice week in TypeScript](#play-a-practice-week-in-typescript).

```sh
pnpm install
pnpm check   # type check
pnpm lint    # lint and format check, no writes
pnpm format  # format, organise imports and apply safe lint fixes
```

We do not write or run tests (see [`AGENTS.md`](AGENTS.md)): check changes by reading them, with lint, format and type
check, and by comparing versions on practice weeks.

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

At the end of a practice week, `dispatch.py` prints two more lines. `Requests` counts the week's requests by route
(`advance`, `actions`, `score`, …). `Stops` gives the reason for each `advance`: the kind of event that stopped the
clock, `poll`, `midnight` or `end`. The request count sets how long a week takes: each request waits for the
network's round trip, about 175 ms through a Claude Code cloud proxy. To keep the count low, the loop does not stop
for every price request. The dealer decides at the request's `respondBy`, 15 minutes after the request, on our last
quote. So while requests keep coming, the loop looks for new ones at least every 14 minutes (`poll`) and quotes them
together with its answers to the other events. A quote sent anywhere before `respondBy` gets the same answer, so the
week stays the same. On the level 8 starter week in `data/` (`smoke-1`), this cuts the stops of the clock from 1,725 to
about 1,390.

- `dispatch.py` is our system. It starts as a copy of the organisers' starter, formatted with ruff.
- `strategies/` holds the parts of the system, each with its notes. `strategies/admission/` decides
  which price requests to take and which option to quote, and `strategies/pricing/` the price of each quote, learned
  during the week.
- `vendor/` holds the organisers' Python kit of 13 November as a wheel. uv installs it as the package `spread`: the
  API client, its types and the unchanged starter. To take a new kit version, replace the wheel and run `uv lock`.
- `tests/` holds older tests, kept as they are but no longer run: we do not write or run tests.

### Play a practice week in TypeScript

The same kit exists for TypeScript, so half of the team can work there. `vendor/spread-typescript/` holds the
organisers' TypeScript kit of 13 November, unchanged: the client (`spread.ts`), its types, the starter and
`reveal-csv.ts`. Lint and format skip `vendor/`. `src/dispatch.ts` is our TypeScript system. It starts as a copy of the
starter that imports the vendored client, and it gives the same baseline as `dispatch.py`.

```sh
pnpm dispatch --level 8 --seed spread-1   # a whole practice week with our TypeScript system
pnpm starter --level 8 --seed spread-1    # the same week with the organisers' unchanged starter
pnpm reveal-csv <world id>                # write an ended week and its reveal to CSV files
pnpm dispatch --final                     # play our copy of a test final or of the final
```

The scripts read `.env` when it exists, and otherwise the variables already set. To take a new kit version, download
`$SPREAD_URL/kit/spread-typescript.tar.gz` and replace the files in `vendor/spread-typescript/`.

### Offline data and scraping more weeks

The data for an offline model of the server is committed in `data/`, so by default the analysis needs no server and
no key. `stats.py` turns saved weeks into distributions and `db.py` loads them into SQLite. Without folders, both read
the team's committed weeks in `data/scrape`:

```sh
uv run stats.py   # reads data/scrape, writes out/summary.json, prints the main numbers
uv run db.py      # loads data/scrape into out/spread.sqlite
```

`data/spread.sqlite` is the same weeks already loaded, ready to query. Only to add weeks, play them on the server with
`scrape.py`, which saves each week's raw data under `out/scrape`, and then pass those folders to the two scripts:

```sh
uv run --env-file .env scrape.py --policy passive --levels 4,5,6,7,8 --seeds 20   # requests only: 10 requests a week
uv run --env-file .env scrape.py --policy explore --levels 8 --seeds 10            # random prices: dealer and driver answers
uv run stats.py out/scrape/passive out/scrape/explore                               # writes summary.json into out/scrape/passive
uv run db.py out/scrape                                                             # loads saved weeks into out/spread.sqlite
```

`scrape.py` also adds each week to the SQLite database `out/spread.sqlite` as it finishes (`--db` to choose another
file, `--no-db` to skip it). `db.py` loads weeks that were saved without it; weeks already in the database are skipped.
Query it with any SQLite tool, for example `sqlite3 out/spread.sqlite "select kind, count(*) from events group by kind"`.
Tables, keyed by `week_id` (a row of `weeks`):

| Table                            | One row for each                                                                                                                        |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `weeks`                          | week: seed, level, policy, explore ranges, score, events, requests, seconds                                                             |
| `events`                         | event, with `data` the event's JSON (read fields with `json_extract`); `gig_viewed` keeps only its columns                              |
| `requests`, `legs`, `options`    | price request; car of a request, with the reveal's truth for won orders; delivery option, with our quote and whether the dealer took it |
| `orders`, `gigs`, `views`        | won order at the end of the week; gig we posted; view of our gigs with the fee the driver saw                                           |
| `drivers`, `ledger`, `forecasts` | driver at the start of the week; account line; snow forecast                                                                            |
| `places`, `roads`                | the map                                                                                                                                 |

A passive week takes about 1.7 MB in the database, and a played week about 20 MB, most of it gig views. The week
folders hold the same data gzipped (about 0.1 MB and 2 MB), so the database can always be rebuilt from them.

`data/` holds the team's committed scrape: the week folders in `data/scrape/<policy>/L<level>/<seed>/`, and
`data/spread.sqlite` built from them (`select level, policy, seed from weeks` lists the weeks). Open the database
directly, or rebuild it and the summary from the folders without the server with `uv run db.py` and `uv run stats.py`.
The default outputs go to `out/`, so the committed files stay as they are.

GitHub refuses files over 100 MB, so once the database outgrows that, commit only the week folders and rebuild it.

Policies:

- `passive` sends nothing and advances to the end at once. The week shows its price requests, forecasts and drivers.
- `starter` plays with the `Desk` of `dispatch.py`.
- `explore` plays like `starter`, but quotes every option at a random multiple of its list price (`--quote-range`,
  default 0.7 to 1.8) and pays each order's gigs a random multiple of the starter's fees (`--fee-range`, default 0.6
  to 1.6). The same seed draws the same multiples.

Seeds are `<--seed-prefix>-<n>`, default `scrape-1` and up. Each week goes to `out/scrape/<policy>/L<level>/<seed>/`
(`out/` is not committed): `events.jsonl.gz` (every event), `reveal.json.gz`, `snapshot.json.gz` (orders and gigs at
the end), `drivers.json.gz` (the driver list at the start), `score.json` and `meta.json`. A saved week is skipped, so
running the same command again resumes. Ctrl-C, and a kill such as `timeout` or a stopped session (SIGTERM, SIGHUP),
deletes the worlds in play, so they free the team's practice slots. A week's folder holds `world.json` while its world
is in play: after a harder kill, the next run deletes that world and plays the week again, or saves it if it ended. `--workers` weeks run at once (default 4), and the scraper always leaves
`--keep-free` practice slots (default 2) for teammates. A week with a policy that acts takes about 2,000 requests: a
few minutes at 175 ms a request through a Claude Code cloud proxy. The scraper's client goes through `HTTPS_PROXY`
when one is set (see [Claude Code cloud environments](#claude-code-cloud-environments)).

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

They match the handbook to the cent. `dispatch.py`, still unchanged from the starter, gives the same level 8 result.
We measured levels 6 and 7 with the organisers' TypeScript starter, before we chose Python; the handbook says that
both starters play alike.

### Claude Code cloud environments

Variables belong to one cloud environment. Every session that starts in that environment gets them. Each environment
that works on this repository needs both variables in its settings:

- `SPREAD_URL=https://spread.bahnexpress.com`
- `SPREAD_KEY`, the team key, or a placeholder when the environment has the key as a network secret for
  `spread.bahnexpress.com`.

How the key reaches the server: `dispatch.py`, `scrape.py` and the bench create their client with `ProxyClient` from
`spread_proxy.py`. When `HTTPS_PROXY` is set, as in a cloud session, it tunnels each request through that proxy and
trusts the CA in `SSL_CERT_FILE`; the proxy swaps the placeholder for the real key. Without `HTTPS_PROXY`, or for a host
in `NO_PROXY`, it connects straight to the server, as the kit's client does. The vendored kit is unchanged. The live
event stream of `dispatch.py --final` still connects straight to the server, so play a final where `SPREAD_KEY` holds
the real key.

## Working in parallel

Four of us work at once, each with our own agent. Every change goes issue → branch (or worktree) → PR, as described
in `AGENTS.md`.
