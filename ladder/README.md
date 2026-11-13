# The ride ladder

A second dispatch system for Spread, built from scratch and independent of the root `dispatch.py` (issue #82). It
climbs a ladder of ride difficulty: it takes only the rides that are easy to move on time at a profit, and unlocks
harder kinds of rides one rung at a time, each with the handling it needs. At level 8 there are too few drivers for
every car, so which cars we take matters more than anything else.

## Run it

From the repository root, with `SPREAD_URL` and `SPREAD_KEY` set (add `--env-file .env` after `uv run` to read them
from `.env`):

```sh
uv run ladder/play.py --level 8 --seed spread-1             # a practice week, at the default rung (4)
uv run ladder/play.py --level 8 --seed spread-1 --rung 1    # easy rides only
uv run ladder/rehearse.py --seed spread-1                   # play the final's code path on a practice world
uv run ladder/play.py --final                               # our copy of a test final or of the final
```

| Option    | Default                | What it does                                               |
| --------- | ---------------------- | ---------------------------------------------------------- |
| `--level` | `8`                    | The practice level, 1 to 8. The final is level 8.          |
| `--seed`  | random                 | The same seed gives the same week.                         |
| `--rung`  | `$LADDER_RUNG`, else 4 | The hardest rung of rides to take (see below).             |
| `--board` | off                    | Plays our next ranking run. Agree on it in the team first. |
| `--final` | off                    | Plays our copy of the final from the live stream.          |

It prints the starter's lines: `Practice world <id>, level <level>.` first, a line for each day, and at the end a
summary of what the ladder did (requests by rung, quotes, posts, warnings, the learned price and opening fees).
Each week is saved like `dispatch.py`'s (`record.Recorder`), under the policy `ladder`, so
`select * from weeks where policy = 'ladder'` in `out/spread.sqlite` lists them. While all eight practice slots are
taken, it waits for one, as the bench does.

To compare rungs on the bench, which passes only `--level` and `--seed`, set the rung in the environment:

```sh
LADDER_RUNG=2 uv run python -m strategies.bench ladder/play.py dispatch.py --seeds spread-1..spread-5
```

### Rehearse the final

The final plays from the live event stream, a code path that practice weeks never take. `rehearse.py` plays it on a
practice world: a second client moves the world's clock as the final's clock runs (`--speed 3`, three times as
fast, takes about 12 minutes), and `--restart-at <minute>` stops the desk at that world minute and starts a new one,
which must rebuild its books from the world, as after a crash in the final. In the final, `--final` rebuilds the
desk after any error and reads the events on from the last one the world has, so an event that broke a desk is not
read again, and a failed read of the events is tried again at once rather than rebuilding. The desk notes each real
quote that the world accepts in `out/ladder-<world id>.quoted`: a desk that restarts learns its price again from
the outcomes of those quotes only, since a decline, or a request that came while no desk ran, always loses. It
also replays the dealers' trust, the on-time estimate, snow forecasts and what failed visits taught. The learned
opening fees start again from their priors.

```sh
uv run ladder/rehearse.py --seed spread-1 --restart-at 3600   # a restart on Wednesday at 12:00
```

## The ladder

| Rung | Takes                 | What it needs                                                                                                       |
| ---: | --------------------- | ------------------------------------------------------------------------------------------------------------------- |
|    1 | Easy rides            | One plain car between dealer sites, no note, ready on a later day, a drive of up to 4 hours, drivers near both ends |
|    2 | Notes                 | The note reader (`strategies/notes`) sets the pickup and delivery windows, the licence and the plates               |
|    3 | Special cars          | Premium cars (experienced drivers only), electric cars that need a charging stop, private addresses                 |
|    4 | Rides ready today     | A later option only; the gig is posted for the next business morning                                                |
|    5 | Long and remote rides | A drive over 4 hours (up to 8), or few drivers near the pickup or the delivery; quoted only with a day to search    |
|    6 | Trade-ins             | Both cars in one gig when the drive fits the 12-hour rule (from level 3), else one gig each                         |

A ride's rung is the hardest thing it asks for (`rides.py`). `--rung n` takes every ride of rungs 1 to n.

### Why this order

In the starter's level 8 week (`data/scrape/starter/L8/smoke-1`, 809 orders), what decided whether a car arrived on
time was mostly when it was ready, against when its request came:

| Car ready                     | Orders | On time | First booking at the opening fee | Median minutes to book |
| ----------------------------- | -----: | ------: | -------------------------------: | ---------------------: |
| Within 3 hours of the request |    336 |   30.1% |                            14.6% |                  1,012 |
| Later the same day            |     21 |   33.3% |                            33.3% |                    419 |
| On the next day               |    385 |   62.3% |                            62.6% |                     16 |
| 2 or more days later          |     67 |   71.6% |                            25.4% |                    209 |

A gig for the next day reaches drivers when they plan that day, and they book it at once. Drives over 4 hours were
on time 18% to 31% of the time, premium cars 23%, trade-ins 14%, private deliveries 28%. A note made no difference
by itself. Drivers near the pickup made little difference; drivers near the delivery did: easy rides into towns
with few drivers booked at their opening fee 37% of the time, against 84% to 96% elsewhere.

## How it works

| File           | What it holds                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------- |
| `play.py`      | The entry point. It puts the repository root on the import path, as the bench runs it from here |
| `main.py`      | The loop for practice weeks and for the final, the daily lines, saving the week                 |
| `desk.py`      | What we know of the week, and our answers: quotes, posts, reprices                              |
| `rides.py`     | The ladder: the rung of each request                                                            |
| `admission.py` | Which requests to quote, and which of their options                                             |
| `pricing.py`   | The price of a quote, learned from our wins and losses, and the dealers' trust                  |
| `fees.py`      | Fee schedules, and the opening fee learned for each rung                                        |
| `market.py`    | The map and the driver list: road minutes, and the drivers within reach of a place              |

- **One decision pass a step.** Events only update what the desk knows. After all of a step's events, `tick`
  quotes the requests that wait, posts every car without a live gig, and reprices the gigs whose plan changed. In
  the final the desk reads the world's event log about five times a second and answers each page of new events in
  one pass, so a burst of requests goes out in one batch of actions. A desk that restarts rebuilds its books from
  the world's events and snapshot, and the next tick fills any gap. A post the world refuses goes again without
  windows of our own; after three refusals in a row the car goes again only after a pause that doubles each time,
  from an hour, so a refusal never loops and no car is given up.
- **Few requests.** While requests keep coming, the clock stops every 14 minutes rather than at each request or win:
  the dealer decides 15 minutes after the request, on our last quote. A level 8 week takes about 300 requests.
- **Admission.** A request is quoted when its rung is taken, an option leaves 5 hours beyond the drive (1 hour for a
  private delivery, which is due in its booked hour), and our cars that still wait for a driver near its pickup, on
  its day, are fewer than a tenth of the drivers within reach. That share shrinks when our estimate of the on-time
  share falls under 95%. A car ready today is quoted on later options only. A long or remote ride needs 21 hours from
  now to its deadline beyond the drive, and a drive over 8 hours is never taken.
- **Prices.** The list price times a multiplier that rises 2.5% after a win and falls 2.5% after a loss, so it
  settles where half of our quotes win, just under the competitor. Each dealer has its own offset on top, and at
  level 8 its trust: 1% for each order delivered to it on time, up to 25%, halved by a late one. Never under 1.25
  times the typical fee on rungs 1 and 2, and up to 1.6 times on the harder rungs, whose drivers cost more.
- **Fees.** A gig opens at the rung's opening fee and stays flat while there is time, so drivers learn that our fees
  do not rise. It rises 20% at 07:00 on the day of its last pickup minute, then from the deadline warning, 3 hours
  before that minute, to 1.5 times the typical fee and 0.2 more every 30 minutes up to 2.2. A car that is already
  late gets 1.6, rising every hour to 2.6: a car never delivered costs twice its price. After a drop, the gig opens at
  least 10% over the dropped fee. The opening fee of each rung moves up when its gigs book only after a raise, and
  never falls more than 5% under its start: a next-day gig gets its driver from the first wave of notifications or
  not at all. A gig opens at no less than half the price of its cars: on the 22 ladder weeks before this rule,
  cars whose typical fee was under 45% of their price (short rides) got deadline warnings 11.6% of the time,
  against 4.5% at 45% to 60% and 1.3% at 60% or more.
- **Cars ready today (rung 4).** The pickup gets a window that opens at 07:00 on the next business day, so drivers
  see the gig as one for the next day, which they book at once. In the starter's week such cars, posted as ready
  now, were on time 30% of the time; on the five rung 4 bench weeks, posted for the next morning, 588 of 602
  (97.7%) were.

## Bench results

Level 8, seeds `spread-1` to `spread-5`, each rung on the same five weeks (rungs 1 and 2 at commit `90fec4f` with the
opening fee of 1.0, rungs 3 and 4 at `1b7c28f`):

| Rung                  | Margin, 5 weeks | Orders | On time | Ranked |
| --------------------- | --------------: | -----: | ------: | -----: |
| 1, easy rides         |      €10,305.84 |    389 |   99.7% | 5 of 5 |
| 2, + notes            |      €19,368.44 |    706 |   99.2% | 5 of 5 |
| 3, + special cars     |      €21,961.61 |    839 |   98.8% | 5 of 5 |
| 4, + cars ready today |      €35,748.74 |  1,596 |   98.4% | 5 of 5 |

| Seed       |    Rung 1 |    Rung 2 |    Rung 3 |    Rung 4 |
| ---------- | --------: | --------: | --------: | --------: |
| `spread-1` | €2,843.64 | €5,103.55 | €5,758.31 | €9,620.64 |
| `spread-2` | €1,647.72 | €3,664.22 | €4,070.13 | €7,089.85 |
| `spread-3` | €1,526.62 | €2,670.85 | €3,091.97 | €4,228.55 |
| `spread-4` | €2,513.42 | €4,580.82 | €5,173.91 | €8,837.45 |
| `spread-5` | €1,774.44 | €3,349.00 | €3,867.29 | €5,972.25 |

A week takes about 300 requests at rungs 1 to 3, and 330 at rung 4. In the rung 4 week on `spread-1`, 304 of the 354
gigs booked at their opening fee, and the fees paid were 1.00 times the typical fee (median), against prices of
1.63 times it.

**Above rung 4 the ladder stops paying.** At commit `0c39f83`, with long and remote rides and trade-ins on top (the
rung 6 of the time, before trade-ins moved to the top):

| Seed       |             Rung 4 | + long, remote, trade-ins |
| ---------- | -----------------: | ------------------------: |
| `spread-1` |  €9,325.82 (99.1%) |        €11,167.34 (97.9%) |
| `spread-2` |  €6,748.72 (98.4%) |         €8,439.37 (95.2%) |
| `spread-3` |  €4,358.11 (99.3%) |         €2,988.37 (94.4%) |
| `spread-4` |  €8,231.57 (98.7%) |         €9,269.95 (93.1%) |
| `spread-5` |  €5,467.06 (97.3%) |         €3,802.33 (90.7%) |
| Total      | €34,131.28 (98.6%) |        €35,667.36 (94.4%) |

The harder rides add 4.5% to the margin and take the on-time share down to 90.7% on one week, a step from the
delivery minimum. On `spread-1` and `spread-2`, long rides quoted with a day to search were late 2 times in 63, but
trade-ins 7 times in 20; and on `spread-3` the late cars that were neither long rides nor trade-ins (remote rides
among them) rose from 2 to 14. So trade-ins moved to the top rung, and the default stays at rung 4.

The first version on `spread-1`, rung 1: +€2,856.27, 93 orders, 100% on time, 281 requests. All 93 gigs booked, 88 at
the opening fee, half of them within a minute. Dealers took `same_day` on 74 of them.

The same seed at rung 2 with the opening fee learned down to 0.72: +€3,235.82, 111 orders, 91.0% on time. Nine of the
ten late cars were next-day cars that no driver booked at the cut opening fee; no raise up to 2.2 found one before
their windows closed, and each was booked a minute after it expired. Hence the floor on the opening fee.

For comparison on `spread-1`: the starter −€72,612.51 (45.5% on time), `dispatch.py` with admission control −€94.87
(95.9%).
