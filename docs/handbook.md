# Handbook (short)

Condensed from [HANDBOOK.md](https://spread.bahnexpress.com/kit/HANDBOOK.md).
Rules details are in [rules.md](rules.md), routes in [api.md](api.md). Where
they differ, the server's `RULES.md` is correct.

## Setup

```sh
export SPREAD_URL=https://spread.bahnexpress.com
export SPREAD_KEY=<team key from /join>
```

- **TypeScript** (Bun or Node ≥ 22.18, no packages):
  `curl -fsSO $SPREAD_URL/kit/spread-typescript.tar.gz && tar -xzf spread-typescript.tar.gz && cd typescript && bun starter.ts`.
  Make it your system by editing `starter.ts`. Node may print a harmless
  type-stripping `ExperimentalWarning`.
- **Python** (≥ 3.9, no deps): `pip install $SPREAD_URL/kit/spread-0.1.0-py3-none-any.whl`,
  run `spread-starter`; copy `spread/starter.py` out to modify it.

Starter options: `--level 1..8` (default 8), `--seed <text>`, `--board` (next
ranking run), `--final` (play your copy of the live final).

### What the starter does (~200 lines)

Sends each step's actions with the next `advance` (one request per step).

1. Quotes the list price of the dealer's first option.
2. Posts each order at once at the typical fee; +10% of it every hour, up to 1.5×.
3. Reads clock times in notes by keyword match.
4. Reposts after a failed visit or expiry.
5. From `deadline_close`: 1.5× typical fee, +0.25× every 30 min, up to 2.5×.
6. In the final, rebuilds state from the world first so it can restart safely.

It loses money: on seed `spread-1` it ends at −€1,172.51 (level 6),
−€50,442.49 (level 7), −€72,612.51 (level 8), with ~45% on time at level 8 —
not ranked. It wins most cars at list price and cannot find drivers for half.

## Practice tools

- **You move the clock** with `advance` (to a minute, by minutes, or until an
  event kind). It returns all events since the last `advance` and can carry the
  step's `actions`.
- **Deterministic:** same seed, level and actions at the same minutes → same
  week to the cent. A change alters driver behaviour from then on, so compare
  versions on _several_ seeds (same seeds for both). Run weeks in parallel.
- **`fork`** copies a world at the current minute with the same future (uses
  one of 8 slots).
- **`reveal`** after the end: your quotes and outcomes, truth about each won
  car, every view of your gigs with the fee seen. Never competitor prices or
  driver costs. `spread-reveal-csv <worldId>` / `bun reveal-csv.ts <worldId>`
  writes CSVs (`requests`, `legs`, `drivers`, `views`, `gigs`, `events`,
  `places`, `roads`); `--seed study-1` runs a fresh world with no actions.
- **Run viewer** at `/viewer/`: each order's money and story, worst first,
  plus a map replay.
- **Test finals:** Sat 14 Nov 14:00 and 20:00 Helsinki; random level 8 week
  from Thursday 00:00, ~19 min, live clock. Join like the final.

## Practice rankings

- API names: ranking round = season, ranking run = board run.
- A round = 5 secret worlds per level, the same for all teams; play them in
  order, once each. `client.create(level, { board: true })` / `--board`.
- Ranking runs can't be forked or revealed and use a slot. Deleting one early
  runs it to the end without you and still counts.
- `client.board(level)` shows the current and previous round. Teams whose 5
  runs all meet the minimum rank first, by total margin.

## The final

- One secret level 8 world, **Sunday 15 Nov 08:00 Helsinki**, set at 07:30.
  Own copy per team; same requests, drivers and draws.
- `client.final()` → world id and start time (404 before set; may return the
  last, ended final — check it hasn't ended). Start any time before 08:00.
- Clock: 06:00–22:00 weekday hour = 18 s, Saturday hour = 6 s, last-Monday
  hour = 9 s; night, Sunday and after last Monday = 3 s per hour. ~34 min total.
  15 world minutes to answer a request = 4.5 real s in the day.
- `advance`, `fork`, `delete` closed; `reveal` opens at the end.
- Read events from `world.stream()` (auto-resumes from last event). On start,
  rebuild state from `snapshot()` + `events()`.
- If your code stops, the world goes on (gigs keep schedules, drivers keep
  working, requests go to the competitor). Restart and continue.
- The server may restart during the final: treat no answer in 20 s or
  502/503/504 as `Unreachable`, wait ~5 s, rebuild, continue.

## Limits

- Practice: 1 token per request; up to 1,000/s per team (≈170/s with 60 teams,
  50/s with 200, 20/s during a final or test final). Over-limit requests wait
  up to 1 s. Systems on one key share it.
- Final: actions 20/s, reads 50/s; over-limit gets 429 immediately (free).
- ≤ 50 actions per batch, ≤ 8 unended practice worlds, ≤ 16 open streams.
- A level 8 week is ~1,900 requests: ~2 s quiet, ~95 s at 20/s; each request
  also pays the network round trip. Advance only to events you act on.

## Client

| Python / TypeScript                                  | Route                                  |
| ---------------------------------------------------- | -------------------------------------- |
| `Client()` (reads `SPREAD_URL`, `SPREAD_KEY`)        |                                        |
| `client.create(level, seed, board)`                  | `POST /v1/worlds`                      |
| `client.worlds()` / `client.world(id)`               | `GET /v1/worlds` / none                |
| `client.final()`                                     | `GET /v1/final`                        |
| `client.board(level)`                                | `GET /v1/leaderboards/practice?level=` |
| `client.map()`                                       | `GET /v1/map` (free)                   |
| `world.snapshot()`                                   | `GET /v1/worlds/{id}`                  |
| `world.act(actions)`                                 | `POST .../actions` (batches of 50)     |
| `world.advance({ untilEvent, max, actions })`        | `POST .../advance`                     |
| `world.events(after)` / `world.stream(...)`          | `GET .../events` / WebSocket           |
| `world.roster()`                                     | `GET .../drivers`                      |
| `world.fork()` / `score()` / `reveal()` / `delete()` |                                        |

Answers use API field names (`referenceFeeCents`). Types: `spread/types.py`,
`typescript/types.ts` (events are `DeskEvent`). Fractions are refused with a
`SpreadError`. Unreachable = no answer, > 20 s, or 502/503/504. An impossible
action returns `{ ok: false, reason }`.

Actions: `quote`, `post`, `offer`, `reprice`, `withdraw`, `release` (shapes in
[api.md](api.md#actions)).

## Events

Every event has `seq`, `at` (world minute), `kind`.

| Event                     | Meaning → what to do                                                                                              |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `price_request`           | Dealer asks for a price; `respondBy` in 15 min → quote (or decline by quoting high).                              |
| `order_won`               | Dealer took your price; has deadline, price, `lastPickupAt` → post a gig or offer.                                |
| `order_lost`              | Competitor won → your price was too high for this dealer/lane/day.                                                |
| `gig_viewed`              | A driver opened your gig; many only browse → nothing.                                                             |
| `gig_booked`              | Driver took it at the current fee → can still release (for a fee).                                                |
| `offer_answered`          | `accepted` / `declined` / `expired` → try another driver or the app.                                              |
| `gig_started`             | Driver left; can no longer release.                                                                               |
| `driver_late`             | Can't make the first window at an open dealer site; `pickupAt` given; still comes → keep, or release free.        |
| `no_show`                 | Can't make it elsewhere; won't come; gig reopens → as `gig_dropped`.                                              |
| `gig_dropped`             | Driver gave it back; gig reopens → check the schedule can still find someone, raise now.                          |
| `gig_expired`             | No booking before a stop window ended → repost.                                                                   |
| `deadline_close`          | No driver 3 h before `lastPickupAt` → raise fee now or send direct offers.                                        |
| `release`                 | Held car (payment/ready) can now be collected.                                                                    |
| `picked_up` / `delivered` | Car collected / delivered (closed site → counts at next opening).                                                 |
| `visit_failed`            | `not_ready`, `closed`, `licence`, `no_plates`; you pay ½ the car's fee share (min €25) → repost fixing the cause. |
| `order_changed`           | Redirect, snow-moved deadline, or private slot moved → re-check deadline and `lastPickupAt`.                      |
| `order_cancelled`         | Gigs `withdrawn` / `released` / `shortened` / `continues` → repost other cars of withdrawn gigs.                  |
| `forecast`                | Snow at places/hours (level 5+) → slower drives, some drivers stay home.                                          |
| `ledger`                  | One account line; their sum is your score.                                                                        |

## Map

`client.map()` (free): `places` (`id`, `name`, `lat`, `lon`) and `roads`
(`from`, `to`, `km`, `minutes`) for every ordered pair and each place to
itself. The 12 h rule and `lastPickupAt` use these minutes; real drives vary
and snow slows them. Public transport times are not published.

## How the world works

- **Drivers** live in towns and each morning decide whether/when to work, how
  many gigs, how late home, longest gig. Day-job drivers work evenings only;
  weekend drivers Saturdays only.
- **Gig cost to a driver** = driving time + trip to pickup + trip home (+
  extras). Transit time is cheap compared with wheel time; small towns lose
  their last evening connection. A gig ending near the driver's home or next
  pickup is cheap for them; a second gig for a driver already on your work
  costs only the extra. You see positions only of drivers on your gigs.
- **Typical fee** = cost for a typical driver living in the pickup town × one
  global factor + noise. Up to level 6, most gigs at the typical fee book; at
  levels 7–8 often no one books. It is not the cheapest driver's price.
- **Seeing gigs:** most views come in the first minutes. Notification only
  within 30 km of home, once per order, again after a drop/no-show; raises
  don't notify; nobody reads 23:00–07:00.
- **Learning your fees** (level 2+): drivers who viewed an order and could do it
  learn booked fee ÷ first viewed fee, and minutes from first view to booking
  (running mean, fades). Always raising teaches drivers to wait. A repost at a
  higher fee counts as a raise; the order keeps its first fee and age.
- **Drops** grow with how long a booking is held and with thin margins; a
  driver plans properly by the next morning and may drop then. Reliable drivers
  rarely drop for a better gig.
- **Direct offers** reach drivers notifications don't (e.g. one finishing your
  gig far from home). Save most where drivers expect a raise. Answers are
  noisy.
- **Competitor price** = list price × lane factor (part fixed across worlds —
  hard lanes with little return work cost more; part new per world) × day
  factor × world price level × small request noise. It moves during the week:
  some mornings steps by origin/destination; once a week the price curve
  reshapes (short vs long lanes). Each morning it cuts prices for dealers where
  you won most requests and raises them where you won few. Each team has its
  own competitor copy. Acceptance falls quickly above its price.
- **Good requests:** towards towns where drivers live; pair with an order you
  have or expect (return leg, same yard); busy area at an hour with many free
  drivers; a later option you can combine. **Bad:** to a town with no return
  traffic, long trip to pickup, hours with few drivers, risky notes. Winning
  everything loses money and uses up your well-placed drivers.
- **Dealer satisfaction:** late/undelivered lowers it (lower accepted prices);
  on-time raises it a little; unquoted requests lower it slightly. Requests are
  the same for all teams regardless.

### Notes (examples)

| Note                                                 | If ignored                                | Do                                                                          |
| ---------------------------------------------------- | ----------------------------------------- | --------------------------------------------------------------------------- |
| Pickup hours ("Nouto arkisin ennen klo 14")          | `closed`                                  | Pick up inside hours.                                                       |
| Ready later ("Klar först på onsdag kl 12")           | `not_ready`, you pay                      | Pick up after; a ≥ 1 day delay moves the deadline (already in `order_won`). |
| After payment ("Maksun jälkeen, ei ennen klo 13.30") | `not_ready`                               | Wait for the `release` event.                                               |
| Tighter deadline ("by tomorrow 17:00")               | Late by note                              | Plan for it or quote high.                                                  |
| Delivery hours ("Vastaanotto klo 16 asti")           | Waits ≤ 2 h at €15/h, counts next opening | Deliver inside hours.                                                       |
| "Manuaalivaihteisto"                                 | `licence`                                 | Audience `manualLicence`.                                                   |
| "Car has no plates"                                  | `no_plates`                               | `withPlates`.                                                               |
| Summer tyres ("kesärenkailla")                       | `not_ready` in snow                       | Avoid snow; snow forecast moves deadline +1 day.                            |

Notes use paraphrase, abbreviations, typos, mixed languages and corrections.
Reveal shows what each won order's note meant — use it to measure your parser.

### Shortage (levels 7–8)

- Level 7: 26–40% of average drivers, competitor +12–38%. Level 8: same count
  but each town scaled by its own factor (some keep most, some lose nearly
  all), competitor +26–54%, plus the price war.
- List price wins most cars; typical fee often finds no driver. You can win
  more cars than can be moved on time.
- The driver list shows where drivers live, not who works; views, bookings and
  drops reveal that during the week.
- House best (the organisers' best system) is ranked on all of 20 weeks at
  levels 7 and 8.

### Dealer trust (level 8)

Per dealer: on-time orders counted up to 25, +1% accepted price each; a late
order halves the count. Starts at 0.

## Research questions to start with

- At what price vs list do quotes start to lose, by lane and by day?
- At what fee, and how long after posting, do gigs on a lane book?
- Which notes did the parser get wrong?
