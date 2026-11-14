# Order handling (`src/ops`)

What `dispatch.py` knows about serving an order, ported to TypeScript as pure functions: they take the kit's plain
data (`vendor/spread-typescript/types.ts`) and return plain data. Nothing here talks to the server, keeps state
or depends on a seed, a dealer, a driver or a place name. Input a function cannot read gives a safe answer (no
facts, no gig, a declined option), never an error. Import everything from `src/ops/index.ts`.

Most functions take a `Context`: `{ map, forecasts?, level?, tightening? }`, with the world map from
`client.map()`, the `forecast` events seen so far, the level (8 by default) and admission's tightening (1 by
default, see `pickOption`).

## Functions

| Function                                                | Returns                                                                                        |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `readNote(note, arrivedAt)`                             | `NoteFacts`: ready and release time, real hours of both sites, deadline, manual, plates, tyres |
| `gigShape(order, legs, facts, retry, now, context)`     | `GigShape[]`: the stops and audience of each gig to post for the cars `legs`                   |
| `canServe(request, option, now, context)`               | `Service`: `ok`, the `slack` in minutes, and a `reason`                                        |
| `pickOption(request, now, context)`                     | The option to quote, or `null` to decline                                                      |
| `features(orderOrRequest, map, option?)`                | `Features`: the gig features that the fee model learns a multiplier for                        |
| `retryAfter(setback, order, request, leg, now, before)` | `Retry`: how to post a car again after a failed visit or an expired gig                        |
| `postAt(order, now, facts?)`                            | The minute to post an order's cars                                                             |

Helpers: `earliestPickup(facts)`, `undelivered(order)`, `withoutWindows(stops, before)`, `pickupWindow(...)`,
`minutes(map, from, to)`, `driveMinutes(map, legs)`, and `NO_FACTS`, `NO_FEATURES`, `FIRST_TRY`.

A strategy posts a won order roughly like this:

```ts
const facts = readNote(request.note, request.arrivedAt)
for (const { stops, audience } of gigShape(order, undelivered(order), facts, FIRST_TRY, now, context))
  outbox.push({ type: 'post', stops, audience, schedule })
```

and after a `visit_failed` or `gig_expired`, posts the car's leg again with
`retryAfter(event.reason ?? 'expired', order, request, leg, now, retryOfThatLeg)`, keeping the `Retry` per leg.

### `readNote`: the note reader

A port of `strategies/notes/reader.py` (its README lists the phrasings): Finnish, Swedish and English, typos one
letter off a known word, relative days and weekday names, clock times and hours in words, corrections and
denials, opening ranges and closing times at either site, deadlines, handover after payment, manual gearbox,
missing plates and summer tyres. The note speaks of the first car only: in a trade-in, the new car. The world's
notes state no other facts (charging, experienced drivers or contact rules): the reveal's `LegTruth` lists
exactly these seven.

One change to the Python: a short weekday followed by a Finnish hour word ("ma viideltä", "ma kahdelta") is that
weekday; `reader.py` read it as today.

**Measured on the saved weeks** (one-off scripts, not tests): on the 4,384 distinct notes of every saved reveal,
the TypeScript reader gives the same facts as `reader.py` on 4,382; the two others are the change above. Against
the reveals' truth, on the 2,204 won cars with a note, as `strategies/notes/check.py` counts:

| Fact            | Notes | Changed by the note | Reader agrees | Reads the change |
| --------------- | ----: | ------------------: | ------------: | ---------------: |
| earliest pickup | 2,204 |                 189 |        100.0% |          189/189 |
| pickup hours    | 2,022 |                  93 |        100.0% |            93/93 |
| delivery hours  | 2,117 |                  67 |         99.9% |            66/67 |
| deadline        | 2,204 |                 129 |        100.0% |          128/129 |
| manual gearbox  | 2,204 |                  42 |        100.0% |            42/42 |
| no plates       | 2,204 |                  57 |        100.0% |            57/57 |
| summer tyres    | 2,204 |                  27 |        100.0% |            27/27 |

### `gigShape`: stops, windows and audience

Ports `stops_for`, `audience_for`, `narrower`, `without_windows` and `Desk.post` of `dispatch.py`, and
`pickup_window` and `delivery_window` of `strategies/notes/plan.py`. Each rule below avoids a fine or a failed
visit (RULES.md, "Rules for handling cars" and "Your account"):

- **Pickup window** from the note's ready or release time, from a retry's `pickupFrom`, and after any forecast snow
  at either end for a car on summer tyres. With the note's real pickup hours, one day inside them, ending an hour
  (`MARGIN`) before closing: the driver plans by the stated hours. A window that starts after the stated one ended
  (a retry) stays open at least a day, so a driver can book it. A private seller's slot never extends: a window
  outside it is left out, and one that runs past it ends with it.
- **Delivery window** ends at the note's deadline, and an hour before the real closing time on its last day. When
  `now` (or the pickup window's start) plus the drive cannot meet it, the car is late whatever: the order's own
  window applies.
- A stop gets its own window only when it is narrower than the order's, and none that has ended by `now`, so the
  world never refuses the post.
- `withPlates` when the note says the car has none or a visit failed on plates; `withCharging` for an electric car
  under 30%.
- **Audience**: experienced drivers for a premium car (€150 a car), a manual licence when the note or a failed visit
  says so.
- **Trade-in over the 12-hour limit**: one gig per car, decided from the map's road minutes. In one gig, the old
  car's pickup comes right after the new car's delivery.

### `canServe` and `pickOption`: admission's time rules

Ports the time rules of `strategies/admission/admission.py`: an option's slack is its deadline less the ready time
(at least an hour from now) and the drive of all cars one after the other. An option needs 5 hours of slack, and
`pickOption` quotes the earliest option with 9 hours, else the last one we can serve. Both limits widen as
`context.tightening` falls from 1 to 0.25, as admission's on-time learner tightens.

On top, a hard check of whether the car can arrive at all, as the world decides it: collected once it is ready,
released and its site open (real hours from the note, Saturday hours, Sunday closed), delivered while the delivery
site is open, plus plates and charging minutes, by the option's deadline (moved by as many business days as the
note's ready time is later) and by the note's deadline. It replaces the check of `Desk.quote` that declined a
request whose note deadline passes before the car can be collected. On the 165 saved `dispatch.py` weeks at level
8, `pickOption` declines none of the 54,560 won orders that arrived on time; asking the 5 hours of slack against
this stricter measure declined 165 of them for 1 late car, so it stays a hard limit only.

Up to level 3, every quote wins the request's first option whatever option it prices, so `pickOption` judges only
the first option there and returns `null` to decline, so no quote goes out with empty prices (issues #108, #116).

### `features`

For the fee model's multipliers (SPREAD_AGENT_BRIEF.md, "Design", step 2): `privatePickup`, `privateDelivery`,
`tradeIn`, `premium`, `weekendDelivery` (a weekend lies between the car's ready day and its deadline, as for a car
ready on Friday), and the first car's `laneKm` and `laneMinutes`. A request takes the deadline of `option`, or of
its first option.

### `retryAfter` and `postAt`

`retryAfter` ports `Desk.retry`, `retry_from` and `Desk.repost`: after `not_ready` or `closed`, the pickup waits two
hours, or until the car should be ready when the dealer moved the deadline of a late car; after `licence`, a manual
licence; after `no_plates`, plates; after `expired`, the delivery goes without its own window (it runs to the end of
the world) and the pickup keeps only the window that the note or the retry needs. A `Retry` adds up what earlier
setbacks taught, where `dispatch.py` kept only the last one.

`postAt` holds the first post of a car ready two or more days later until 08:00 on the business day before (issue
#106), never later than a day before its last pickup. It is a hypothesis that the bench has not measured yet: a
strategy should put it behind a flag.

## Left out

| Rule                                                                                     | Why                                                                                                                                 |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Admission's capacity (driver supply, area load, reliability, stress) and on-time learner | State learned from the week: the brief replaces them with the capacity and on-time multipliers. `tightening` is the input they feed |
| Admission's expected cost, `risky_note` and profit check                                 | Pricing and fees (#136, #137)                                                                                                       |
| Fee schedules, the level 1 ladder, raises at `deadline_close`, repricing after a drop    | `strategies/fees`: the fee function of the brief (#136, #137)                                                                       |
| Bundling and direct offers                                                               | Not in #138                                                                                                                         |
| The desk's books: gigs per leg, rejoin, withdraw, split, `post_rest`                     | Tied to Python's structure: the harness keeps them                                                                                  |
| A booked car sent farther (#114)                                                         | `dispatch.py` does nothing there, and the saved weeks show no fix yet                                                               |
| Charging only on routes over 200 km (rule 3)                                             | `dispatch.py` charges every electric car under 30%; no saved week tells the route rule                                              |
