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

- `dispatch.py` is our system. It started as a copy of the organisers' starter, formatted with ruff.
- `strategies/` holds the parts of the system, each with its notes, and each a subclass of one abstract base class,
  `Strategy` ([`strategies/README.md`](strategies/README.md)). `strategies/admission/` decides which price requests
  to take and which option to quote, and `strategies/pricing/` the price of each quote, learned during the week.
  [`strategies/notes/`](strategies/notes/README.md) reads dealer notes into facts (ready time, real hours, deadline,
  gearbox, plates, tyres) that set the gigs' windows, audience and plates. `strategies/offers/` sends gigs straight
  to drivers near their pickup. [`strategies/bundling/`](strategies/bundling/README.md) puts several orders' cars in
  one gig when that saves a driver's trips, and holds batch orders briefly to find them. Two folders are whole
  systems of their own: `strategies/baseline/`, the organisers' starter's decisions as strategies, our fixed
  baseline, and `strategies/price_ladder/`, a clamped price ladder with a shadow price on driver capacity.
- `vendor/` holds the organisers' Python kit of 13 November as a wheel. uv installs it as the package `spread`: the
  API client, its types and the unchanged starter. To take a new kit version, replace the wheel and run `uv lock`.

### Every online run is saved

Each week that `dispatch.py` or the TypeScript system `src/dispatch.ts` plays on the server is saved like a scraped
week, so every online run adds to the data that we analyse offline. This covers practice weeks, the bench's weeks,
ranking runs (`--board`) and finals (`--final`). When a week of `dispatch.py` ends, `record.py` saves it:

- its folder `data/scrape/runs/L<level>/<seed>/<world id>/`, in the format of `scrape.py` (below), with policy
  `dispatch`. `meta.json` also says `kind` (`practice`, `board` or `final`), `version` (the git commit, `-dirty` with
  changes) and `revealed` (ranking runs have no reveal, so their requests come from the events). The seed is `random`
  without `--seed`, and `board` or `final` for those runs. A played week takes about 0.4 MB.
- its rows in the SQLite database `out/spread.sqlite` (see the tables below).

The run prints `Saved the week to ...` at the end. A week stopped with Ctrl-C or an error is not saved, and a failure
while saving prints a warning and leaves the score as it is. Commit the new folders under `data/scrape/runs` with your
PR: each world has its own folder, so they never conflict. In a new checkout, `uv run db.py` builds `out/spread.sqlite`
from every committed week, these runs included. `SPREAD_RUNS_DIR` and `SPREAD_DB` change where the week goes, and
`SPREAD_RECORD=0` saves nothing. The bench sets the first two, so a git version that it plays in a temporary worktree
saves into this checkout.

`pnpm dispatch` saves its weeks with `src/record.ts`, in the same folder format and with the same `SPREAD_RUNS_DIR`
and `SPREAD_RECORD=0`. It writes only the folder: run `uv run db.py` to add it to `out/spread.sqlite`.

### The ride ladder: a second system

[`ladder/`](ladder/README.md) is a second dispatch system, built from scratch and independent of `dispatch.py`. It
takes only the rides that are easy to move on time first (one plain car between dealer sites, ready on a later day,
a drive of up to 4 hours), and unlocks harder kinds of rides one rung at a time: notes, special cars, cars ready
today, long and remote rides, trade-ins. It plays rung 4 by default: on level 8, `spread-1` to `spread-5`, it made
€34,131 to €35,749 in the five weeks, 98.4% to 98.6% on time, all ranked; the rungs above it add little and cost
on-time share. It saves its weeks like `dispatch.py`, under the policy `ladder`.

```sh
uv run ladder/play.py --level 8 --seed spread-1             # a practice week at the default rung
uv run ladder/play.py --level 8 --seed spread-1 --rung 1    # easy rides only
uv run ladder/rehearse.py --seed spread-1                   # play the final's code path on a practice world
uv run ladder/play.py --final                               # our copy of a test final or of the final
```

### Play a practice week in TypeScript

The same kit exists for TypeScript, so half of the team can work there. `vendor/spread-typescript/` holds the
organisers' TypeScript kit of 13 November, unchanged: the client (`spread.ts`), its types, the starter and
`reveal-csv.ts`. Lint and format skip `vendor/`. `src/dispatch.ts` is our TypeScript system. It is still a copy of the
starter that imports the vendored client and saves its weeks, so it gives the starter's
[baseline](#the-baseline-to-beat).

```sh
pnpm dispatch --level 8 --seed spread-1   # a whole practice week with our TypeScript system
pnpm starter --level 8 --seed spread-1    # the same week with the organisers' unchanged starter
pnpm reveal-csv <world id>                # write an ended week and its reveal to CSV files
pnpm dispatch --final                     # play our copy of a test final or of the final
```

`pnpm dispatch` saves every week it finishes to `data/scrape/runs/`, like `dispatch.py`
([Every online run is saved](#every-online-run-is-saved)); `uv run db.py` adds the saved weeks to the database. The
scripts read `.env` when it exists, and otherwise the variables already set. To take a new kit version, download
`$SPREAD_URL/kit/spread-typescript.tar.gz` and replace the files in `vendor/spread-typescript/`.

The three scripts set `NODE_USE_ENV_PROXY=1`, so on Node 22.21+ `fetch` goes through `HTTPS_PROXY` when it is set, as in a
Claude Code cloud session, where the proxy swaps the placeholder `SPREAD_KEY` for the real key; `NODE_EXTRA_CA_CERTS`
must name the proxy's CA (cloud sessions set it). Without `HTTPS_PROXY` they connect straight to the server. `.npmrc`
turns on pnpm's `shell-emulator`, so the variable works on Windows too. The `--final` WebSocket stream does not go
through the proxy yet.

### Get the team's scraped data

The team's scraped weeks (`out/scrape`) and probe rows (`out/probe`) are too big for git, so each batch goes up as
one tarball on a GitHub release of this repository (`data-<date>`). Every release holds all the data, not only the
new weeks, so the latest one is all you need. Get it, and build your own SQLite database from it (about 10 times the
size of the folders, so it is not shared):

```sh
mkdir -p out && gh release download --pattern 'spread-data-*.tar.gz' --output - | tar -xz -C out
uv run db.py out/scrape out/probe    # builds out/spread.sqlite; weeks already in it are skipped, changed probe files are reloaded
uv run python -m analysis.facts   # adds the derived tables (analysis/README.md)
```

To publish a new batch, from the checkout that holds the most data (check `find out/scrape -name meta.json | wc -l`
first, so a release never holds fewer weeks than the last one):

```sh
stamp=$(date +%Y%m%d-%H%M) && tar -czf out/spread-data-$stamp.tar.gz -C out scrape probe \
  && gh release create data-$stamp out/spread-data-$stamp.tar.gz --title "Scraped data $stamp" \
     --notes "$(find out/scrape -name meta.json | wc -l) weeks, $(cat out/probe/*.jsonl 2>/dev/null | wc -l) probe rows"
```

A downloaded tarball overwrites the week folders of the same name, which are the same weeks: a seed, level and
experiment always play the same week.

### Offline data and scraping more weeks

The data for an offline model of the server is committed in `data/`, so by default the analysis needs no server and
no key. `stats.py` turns saved weeks into distributions and `db.py` loads them into SQLite. Without folders, both read
the team's committed weeks in `data/scrape`:

```sh
uv run stats.py   # reads data/scrape, writes out/summary.json, prints the main numbers
uv run db.py      # loads data/scrape into out/spread.sqlite
```

The database is not committed: `uv run db.py` builds it from the committed week folders in a few seconds, the saved
online runs included. Only to add scraped weeks, play them on the server with `scrape.py`, which saves each week's raw
data under `out/scrape`, and then pass those folders to the two scripts:

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

| Table                            | One row for each                                                                                                                                                                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `weeks`                          | week: seed, level, policy, explore ranges, score, events, requests, seconds; `settings` holds the other options and the git commit                                                                                                          |
| `events`                         | event, with `data` the event's JSON (read fields with `json_extract`); `gig_viewed` keeps only its columns                                                                                                                                  |
| `requests`, `legs`, `options`    | price request; car of a request, with the reveal's truth for won orders; delivery option, with our quote and whether the dealer took it                                                                                                     |
| `orders`, `gigs`, `views`        | won order at the end of the week; gig we posted; view of our gigs with the fee the driver saw                                                                                                                                               |
| `drivers`, `ledger`, `forecasts` | driver at the start of the week; account line; snow forecast                                                                                                                                                                                |
| `places`, `roads`                | the map                                                                                                                                                                                                                                     |
| `actions`                        | action the scrape sent (quote, post, reprice, offer, withdraw), with its minute, its world answer and its JSON in `data`                                                                                                                    |
| `rosters`                        | driver at each midnight and at the end of the week: rating, completed gigs and drops (they count only our gigs)                                                                                                                             |
| `positions`                      | sample of where one of our drivers was, with `--sample-every`                                                                                                                                                                               |
| `probes`                         | delivery option that `probe.py quote` bisected: level, seed, request, list price, the flip (`flip_cents`, `flip_ratio`, `bracket_low_cents` = highest price known to win), `ends`, `monotone`, `error`, and every trial as JSON in `trials` |
| `fee_probes`, `probe_files`      | order that `probe.py fee` bisected, with the same flip columns for the flat fee and who booked at the flip; probe file that was loaded, with its size and mtime                                                                             |
| `shape_probes`                   | pair of requests that `probe.py shape` probed: kind, order ids, lanes, each car's single flip and the combined flip, `saving_ratio`, `same_driver`, who booked and their home, and the trials                                               |

Derived analysis tables (win model, booking hazard, order economics, supply) are built by
`uv run python -m analysis.facts`; see `analysis/README.md`.
The hindsight oracle (where a week's margin went, and what a perfect dispatcher could have kept):
`uv run python -m analysis.oracle`.
One page with the whole picture: `uv run python -m analysis.report` writes `out/report.html` and serves it on
localhost until Ctrl-C (`--no-serve` only writes the file).
Every strategy of `strategies/` replayed on the saved weeks, offline, with charts: `uv run python -m analysis.replay`
writes `out/replay.html` and `out/replay.csv` and serves the page on localhost (see "Offline replay" in
`analysis/README.md`).

A passive week takes about 1.7 MB in the database, and a played week about 20 MB, most of it gig views. The week
folders hold the same data gzipped (about 0.1 MB and 2 MB), so the database can always be rebuilt from them.

`data/` holds the team's committed scrape: the week folders in `data/scrape/<policy>/L<level>/<seed>/` and the saved
online runs in `data/scrape/runs/` ([Every online run is saved](#every-online-run-is-saved)). Build the database and
the summary from them, without the server, with `uv run db.py` and `uv run stats.py` (`select level, policy, seed from
weeks` lists the weeks). Both write to `out/`, which is not committed.

Policies:

- `passive` sends nothing and advances to the end at once. The week shows its price requests, forecasts and drivers.
- `starter` plays with the kit's own starter (`spread.starter`), which never changes: a fixed baseline, the handbook's.
- `dispatch` plays with the `Desk` of our current `dispatch.py`.
- `explore` plays like `starter` (the kit's, so explore weeks stay comparable while our strategy changes), but quotes every option at a random multiple of its list price (`--quote-range`,
  default 0.7 to 1.8) and pays each order's gigs a random multiple of the starter's fees (`--fee-range`, default 0.6
  to 1.6). The same seed draws the same multiples. Its other options:
  - `--quote-share 0.3` quotes only that share of the requests and declines the rest (10 times the list price), so
    the week does not win more cars than drivers can move. Lateness would lower the dealers' prices and skew the data.
  - `--fee-shape` is one shape for the whole week, because drivers learn our fees: `rising` (the starter's, the
    default), `flat` (the opening fee only), or `slow` (a straight rise from the opening fee to `--fee-cap` times the
    typical fee, default 2.5, ending 3 hours before the order's `lastPickupAt`). After a deadline warning every shape
    goes steep, as the starter does.
  - `--offers 2` sends each order's first gig, in the minute it is posted, as a direct offer to up to that many drivers (at most 3) who live within
    30 road km of the pickup and fit the gig's audience, each at a random multiple of the typical fee
    (`--offer-range`, default 0.4 to 1.6). The answers are `offer_answered` events. From level 3.
- `--sample-every 120`, with `starter` or `explore`, reads the positions of our drivers every 120 minutes. It is off
  by default: it reads the whole snapshot each time, about 1 MB late in the week.
- `--tag <name>` names an experiment: its weeks go to `out/scrape/<policy>-<name>` and form their own group in
  `summary.json`. Give each set of options its own tag, or the second run skips the seeds as saved before.

Seeds are `<--seed-prefix>-<n>`, default `scrape-1` and up. Each week goes to `out/scrape/<policy>/L<level>/<seed>/`
(`out/` is not committed): `events.jsonl.gz` (every event), `reveal.json.gz`, `snapshot.json.gz` (orders and gigs at
the end), `drivers.json.gz` (the driver list at the start), `score.json` and `meta.json` (every option and the git
commit). It also saves what the server keeps no record of: `actions.jsonl.gz` (each action with its minute and answer:
the reveal keeps only the last quote, and the snapshot only each gig's last fee schedule), `rosters.jsonl.gz` (the
driver list at each midnight and at the end: its completed gigs and drops count only our gigs, so it shows our drivers'
record, not who works) and, with `--sample-every`, `positions.jsonl.gz`. A week that a killed
scrape left behind is saved without these three files (`"recorded": false` in its meta). A saved week is skipped, so
running the same command again resumes. Ctrl-C, and a kill such as `timeout` or a stopped session (SIGTERM, SIGHUP),
deletes the worlds in play, so they free the team's practice slots. A week's folder holds `world.json` while its world
is in play: after a harder kill, the next run deletes that world and plays the week again, or saves it if it ended. `--workers` weeks run at once (default 4), and the scraper always leaves
`--keep-free` practice slots (default 2) for teammates. A week with a policy that acts takes about 2,000 requests: a
few minutes at 175 ms a request through a Claude Code cloud proxy. The scraper's client goes through `HTTPS_PROXY`
when one is set (see [Claude Code cloud environments](#claude-code-cloud-environments)).

Which scrape answers which question of `SPREAD_AGENT_BRIEF.md`:

| Question                                                        | Scrape                                                                                    |
| --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Requests, dealers, roster and shortage by town                  | `--policy passive --levels 6,7,8`                                                         |
| Win model by lane and day, price war, option choice             | `--policy explore --tag win --quote-share 0.3 --quote-range 0.8,2.0`                      |
| Dealer ceiling when the competitor is down (level 6 outage)     | `--policy explore --tag ceiling --levels 6 --quote-share 0.3 --quote-range 1.0,2.5`       |
| How low drivers go; booking hazard by fee and lead time         | `--policy explore --tag slow --fee-shape slow --fee-range 0.3,1.0` and `--fee-shape flat` |
| Per-driver answers at a known fee                               | `--policy explore --tag offers --offers 3`                                                |
| Do gigs that end near the driver's home fill cheaper            | any played week: `delivered` events and the driver's home, or `--sample-every`            |
| Thresholds or probabilities; the exact price where a quote wins | not a scrape: it needs a fork of one world at one minute                                  |

`summary.json` has one entry per level and policy (`L8/explore`) and a catalogue of every event kind:

- `eventCatalogue`: for each kind, its count, its fields with their types and number ranges, the values of each
  enumeration (for example `visit_failed.reason`), and one example.
- `arrivalsPerHourOfWeek`: requests per hour from Monday 00:00, per week.
- `numbers`: quantiles of counts per week, request timing and distance, fees over list prices, gig views, minutes to
  booking, booked fee over the typical fee, drops, no-shows and late drivers per booking, lateness, and driver ratings.
  `gigs.minutesFromBookingToDrop` gives, for each `gig_dropped`, the minutes since that gig's last booking.
- `counts`: shares of legs, option sets, note languages, private addresses, car types, failed-visit reasons, order
  status, and the truth of won cars from the reveal. `gigs.bookedShareByPostHour` gives, for each hour of the day a
  gig was posted, the number of gigs (`count`) and the share of them that were booked (`share`).
- `fits`: straight lines for list price against km, typical fee against drive minutes, and booked fee against the
  typical fee.
- `quoteResponse`: for bins of quote / list price, how often the dealer took the option and won the request.
- `feeResponse`: the drivers' side of `quoteResponse`. Gigs in bins of 0.2 of opening fee / typical fee for their cars
  (`1.2` holds 1.2 to 1.4): the number of gigs, the share booked, quantiles of minutes to the first booking, and drops
  per booking. Explore weeks spread the ratio, so they give the booking curve.
- `priceOverFit`: what moves prices besides distance. Each request's list price (one entry per option) and typical
  fee, divided by the straight line fitted on one-car requests (km for list prices, drive minutes for the typical
  fee), summed over the request's legs. Quantiles for all requests and split by `note` language (or `none`), `car`
  (`premium`, else `electric`, else `standard`), number of `legs`, and `privateAddress` (any stop at one).
- `driverHomeShare` and `ledger`: where drivers live, and money per week by account line.

### Probe a world: where does a quote or a fee flip?

`probe.py` answers what a scrape cannot: it forks one practice world at one minute, tries one price or fee in each
copy, and bisects to the value where the outcome flips. A copy has the same future draws as its parent, so the flip
comes from the action alone.

```sh
uv run --env-file .env probe.py quote --level 8 --seed scrape-1 --share 0.05 --days 0,1   # ~20 requests
uv run --env-file .env probe.py fee --level 8 --seed scrape-1 --limit 20       # 20 orders
uv run --env-file .env probe.py shape --level 8 --seed scrape-1 --days 0,1     # ~42 pairs
```

- `quote`: at a request's arrival, quotes one option at a time in copies and advances to `respondBy`. `flipRatio` is
  the highest price over the list price that wins this request with this world's draws: the competitor and the
  dealer's value as one number, to `--resolution` (default 1% of the list price), inside `--range` (default 0.6,2.5).
- `fee`: quotes the request at `--win-ratio` (default 0.5) of the list price to win it, then posts its cars at one
  flat fee per copy and advances `--window` minutes (default 180). `flipRatio` is the lowest flat fee over the typical
  fee that a driver books within the window (never past the order's `lastPickupAt`), with who booked it, how soon,
  the gig's views and whether it expired. `atFlip` also has the booking driver's `homePlaceId`, `toPickupKm` and
  `fromDeliveryKm`.
- `shape`: is one gig of two cars cheaper than two gigs? A pair is a `trade_in` (one request, two cars), a
  `round_trip` (two one-car requests on exact reverse lanes that arrive at most `--gap` minutes apart, default 180)
  or a `chain` (the second car starts where the first ends but ends 100 km or more from the start; a control, add it
  with `--kinds trade_in,round_trip,chain`). The first run of a seed and level scouts the week's requests into
  `out/probe/requests-L<level>-<seed>.json`; the request stream does not depend on our actions. The probe wins both
  orders, and at the minute the second is won bisects three gigs in copies: `single[0]` and `single[1]` (each car
  alone) and `combined` (both cars, its fee the gig's total). `savingRatio` is (sum of single flips - combined flip)
  over the pair's typical fee: positive means one gig is cheaper than two. `together` posts both single gigs at once at
  their single flips and says who booked them and whether one driver took both (`sameDriver`). `returnKm` is the drive
  from the last delivery back to the first pickup (12 km for a round trip, 100+ for a chain). The row's `ends` names
  each treatment that did not flip, as `combined:never`. The scout holds one slot, once per seed and level; a pair
  then costs about 39 copies and 35 seconds.
- `shape` limits: a round trip saves the drive to the second pickup and also ends where it began; comparing
  `savingRatio` of round trips and chains by `returnKm`, and `atFlip.fromDeliveryKm`, separates the two only in part.
  Each flip is the cheapest driver of that gig, often a different one per treatment, and a trade-in's own extra
  (trade-in, private address, the customer's slot) is mixed into its saving.
- Each row also has every trial and `monotone`: whether the outcomes change once as the value rises. Two extra trials
  a little either side of the bracket (`--checks`) test it. Monotone rows say the world answers with a threshold, not a coin.
- The parent posts no gigs and declines every other request at no cost, so each probe sees drivers who have learned
  nothing and dealers with no history: the world's first answer, not a week's. Two drifts remain. The competitor
  raises its prices each morning for dealers whose requests it wins, and the parent wins none, so late-week quote
  flips read high: `--days 0,1` probes only Monday and Tuesday. In fee mode the won orders are never delivered, which
  lowers what those dealers accept later. Rows carry `day` and `hour`, so price-war and outage days can be told apart.
- A quote row's `ends` says when it did not flip inside `--range`: `true` (won at both ends), `false` (lost at both)
  or `inverted`. A fee row's `ends` is `never` (no driver even at the top fee, see `expiredAtTop`) or `always`. A
  refused action or a lost win quote gives a row with `error` instead.
- Rows go to `out/probe/<mode>-L<level>-<seed>.jsonl`. `uv run db.py` loads them into the `probes` and `fee_probes`
  tables (not `shape` rows yet); run it again after a probe has grown. Running the same command again skips the rows saved. A probe
  holds the parent and one copy at a time (two practice slots) and leaves `--keep-free` slots (default 2) for
  teammates. Each bisection step is a fork, an advance and a delete: about 8 to 12 steps a probe.

### The baseline to beat

The unchanged starter on the seed `spread-1`. It quotes the list price, wins most cars and cannot find drivers for
them in time. Our copy of that starter is in [`strategies/baseline/`](strategies/baseline/README.md), so the bench can
play it beside our system.

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

They match the handbook to the cent. The first `dispatch.py`, an unchanged copy of the starter, gave the same level 8
result. We measured levels 6 and 7 with the organisers' TypeScript starter, before we chose Python; the handbook says
that both starters play alike.

### Level 1

At level 1 the dealer ignores our prices: every quote wins the request's first option at its list price, which is
only about 10% above the typical fee. So the margin comes from paying drivers less than the typical fee, and from
taking every request we can deliver on time. Level 1 has a [fee ladder](strategies/fees/README.md) (gigs open at half
the typical fee and rise every 30 minutes while no driver books them), and its own
[admission](strategies/admission/README.md) rules (it judges only the first option, and holds more unbooked orders).
Levels 2 to 8 play as before.

Practice weeks, `uv run dispatch.py --level 1 --seed <seed>`:

| Seed       | System                          | Margin    | Orders | On time |
| ---------- | ------------------------------- | --------- | ------ | ------- |
| `spread-1` | main before the ladder          | €20.97    | 462    | 98.9%   |
| `spread-1` | fee ladder                      | €6,037.26 | 527    | 98.3%   |
| `spread-1` | fee ladder, first-option quotes | €7,167.61 | 754    | 97.1%   |
| `spread-2` | fee ladder, first-option quotes | €8,180.57 | 734    | 97.3%   |

Ranking runs on 13 November, `uv run dispatch.py --level 1 --board`, all ranked. The organisers started the round
"Saturday 00:00" while run 2 was ending, so runs 1 and 2 count in the round "Friday 20:01" and runs 3 to 5 in the next:

| Run | Round          | Margin     | Orders | On time |
| --- | -------------- | ---------- | ------ | ------- |
| 1   | Friday 20:01   | €8,026.68  | 708    | 97.2%   |
| 2   | Friday 20:01   | €9,148.53  | 806    | 97.0%   |
| 3   | Saturday 00:00 | €10,921.47 | 786    | 99.0%   |
| 4   | Saturday 00:00 | €10,696.67 | 797    | 98.2%   |
| 5   | Saturday 00:00 | €7,610.01  | 730    | 95.6%   |

### Claude Code cloud environments

Variables belong to one cloud environment. Every session that starts in that environment gets them. Each environment
that works on this repository needs both variables in its settings:

- `SPREAD_URL=https://spread.bahnexpress.com`
- `SPREAD_KEY`, the team key, or a placeholder when the environment has the key as a network secret for
  `spread.bahnexpress.com`.

How the key reaches the server: `dispatch.py`, `scrape.py` and the bench create their client with `ProxyClient` from
`spread_proxy.py`. When `HTTPS_PROXY` is set, as in a cloud session, it tunnels each request through that proxy and
trusts the CA in `SSL_CERT_FILE`; the proxy swaps the placeholder for the real key. Without `HTTPS_PROXY`, or for a host
in `NO_PROXY`, it connects straight to the server, as the kit's client does. The vendored kit is unchanged. The proxy
does not pass WebSocket upgrades, so through a proxy the live event stream of `dispatch.py --final` polls
`GET /events` every 0.2 seconds instead (`ProxyWorld.stream`), with the same events in the same order; that is at most 5
of the final's 50 reads a second. Without a proxy, it uses the kit's WebSocket stream as before.

## Working in parallel

Four of us work at once, each with our own agent. Every change goes issue → branch (or worktree) → PR, as described
in `AGENTS.md`.
