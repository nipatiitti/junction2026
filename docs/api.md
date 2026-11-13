# API (short)

Condensed from [API.md](https://spread.bahnexpress.com/kit/API.md) and
[openapi.json](https://spread.bahnexpress.com/openapi.json) (OpenAPI 3.1).
Base URL `https://spread.bahnexpress.com`.

- Auth: `Authorization: Bearer <team key>` on everything except the map,
  leaderboards, `/openapi.json` and `/kit/`.
- Times: whole world minutes from Monday 00:00 (1440 = Tuesday 00:00). Money:
  whole cents. A fractional number → 400.
- Free, no key: `/kit/` (kits + docs), `/viewer/`, `/screen/`.

## Routes

| Route                                      | Body → Returns                                                                                                 |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `GET /v1/worlds`                           | → `{ worldId, kind: practice\|final, level, parent, season, boardRun, ended }[]`                               |
| `POST /v1/worlds`                          | `{ level: 1-8, seed?, board? }` → 201 `{ worldId }`. `board` + `seed` → 400.                                   |
| `GET /v1/worlds/{id}`                      | → `DeskSnapshot` `{ worldId, now, endsAt, openRequests, orders, gigs, driverPositions, score }`                |
| `DELETE /v1/worlds/{id}`                   | → 204. Unended ranking run plays to its end first.                                                             |
| `POST /v1/worlds/{id}/actions`             | `Action[]` (1–50) → `ActionResult[]` same order                                                                |
| `POST /v1/worlds/{id}/advance`             | `{ to }` \| `{ by }` \| `{ untilEvent: Kind[], max }`, optional `actions` (1–50) → `{ results?, now, events }` |
| `GET /v1/worlds/{id}/events?after=&limit=` | → `DeskEvent[]` with `seq > after` (default -1 = all)                                                          |
| `GET /v1/worlds/{id}/drivers`              | → `DriverProfile[]` (≤ 5 s stale while moving)                                                                 |
| `POST /v1/worlds/{id}/fork`                | → 201 `{ worldId }`; 403 on ranking runs                                                                       |
| `GET /v1/worlds/{id}/score`                | → `Score`                                                                                                      |
| `GET /v1/worlds/{id}/reveal`               | → `Reveal` after end; 409 before; 403 for ranking runs                                                         |
| `GET /v1/worlds/{id}/stream?after=`        | WebSocket, one `DeskEvent` per message                                                                         |
| `GET /v1/map`                              | no key → `{ places: [{ id, name, lat, lon }], roads: [{ from, to, km, minutes }] }`                            |
| `GET /v1/leaderboards/practice?level=`     | no key → `{ level, current, previous }` (`BoardSeason`)                                                        |
| `GET /v1/final`                            | → `{ worldId, startsAt (ISO), now }`; 404 before set                                                           |
| `GET /v1/leaderboard`                      | no key, SSE every 2 s: `{ status: none\|scheduled\|running\|ended, now, endsAt, teams[] }`                     |

`advance` applies `actions` at the current minute, then moves the clock; it
never passes the world end. Its `events` hold everything since the previous
`advance` (after a server restart there may be repeats — dedupe by `seq`). The
first `advance` on a fork returns the whole history.

In the final, `advance`, `fork`, `DELETE` → 403; `reveal` → 403 until the end.
Use the stream and fill gaps with `GET /events?after=`.

## Actions

```ts
{ type: "quote", requestId, prices: { same_day?, next_day?, within_3_days?: cents } }
{ type: "post",
  stops: [{ orderId, leg: 0|1, kind: "pickup"|"delivery",
            window?: { from, to }, withPlates?, withCharging? }],  // ≥ 2 stops
  audience: { experienced: boolean, manualLicence: boolean },
  schedule: [{ at: minute, feeCents }] }                          // 1–48 steps, fees non-decreasing
{ type: "offer",    gigId, driverId, feeCents }
{ type: "reprice",  gigId, schedule }
{ type: "withdraw", gigId }
{ type: "release",  gigId }
```

`ActionResult` = `{ ok: true, id }` or `{ ok: false, reason }` (reasons never
depend on hidden facts).

## Key types

- `PriceRequest`: `id, dealerId, batchId, arrivedAt, respondBy, legs[1-2],
  options[{ kind, deadline, listPriceCents }], referenceFeeCents, note`.
- Leg: `car { premium, electric, chargePercent }`, `pickup` / `delivery`
  `{ placeId, privateAddress, window { from, to }, hours }`. `hours` is
  `{ opens, closes, weekdays: 0-4[], saturday: { opens, closes } | null }`
  (minutes of day) or null for a private address.
- `Order`: `id, dealerId, option, priceCents, deadline, legs, status,
  deliveredAt, lastPickupAt`.
- `Gig`: `id, stops, audience, schedule, status (open|booked|working|done|withdrawn),
  postedAt, feeCents, driverId`.
- `DriverProfile`: `id, homePlaceId, rating (1-5), licence (manual|automatic_only),
  completedGigs, drops`.
- `Score`: `marginCents, revenueCents, marginShare, wonOrders, onTimeShare,
  undeliveredShare, ranked`.
- `LedgerLine`: `at, kind (revenue|late_refund|undelivered_penalty|driver_fee|
  failed_visit|release_fee|waiting|fine), cents, orderId, gigId, detail`.

## Reveal

After a practice world (or the final) ends. Not for ranking runs.

- `requests[]`: `request`, `quote` (your last prices or null), `outcome`
  (`won|lost|unquoted`), `option` taken.
- `orders[]` (won, incl. cancelled): `orderId`, `legs[]` with `readyAt`,
  `releasedAt`, `pickupHours`, `deliveryHours` (real hours), `manualGearbox`,
  `needsPlates`, `summerTyres`, `noteDeadline`, `pickedUpAt`, `deliveredAt`.
- `views[]`: `gigId, driverId, at, feeCents` (fee the driver saw).

Never shows competitor prices or driver costs. Below level 5 the facts equal
what the request stated.

## Stream

WebSocket with the same auth header. Without `after`: events from the moment
it opens. With `after=seq`: backlog first, then live, in order, no repeats.
More than 4 MB behind → closed with code 1013; reconnect with `after`. Max 16
open streams per team.

## Practice rankings

- A round (season) = 5 secret worlds per level, same for all teams.
  `POST /v1/worlds { level, board: true }` starts run n of the round.
- 409 if: no round started, your run at that level hasn't ended, or you've
  played all 5.
- Deleting an unended run plays it to the end without you; it still counts
  (`deletedAt` shown).
- `BoardSeason`: `{ season, name, startedAt, teams: [{ rank, team, name, played,
  ranked, marginCents, onTimeShare, runs: [{ run, marginCents, onTimeShare,
  wonOrders, ranked, deletedAt }] }] }`. Totals and rank are null until 5 runs
  end. Team ranked = all 5 runs meet the minimum. `house-*` teams have no rank.
  At most 2 s stale.

## Limits

| Bucket        | Refills                                                                                     | Max           | Cost                                                         |
| ------------- | ------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------------------ |
| Practice      | 10,000/s server-wide split among active teams, ≤ 1,000 per team; 20/s during a (test) final | 1 s of tokens | 1 per practice request of any kind (incl. create/list)       |
| Final actions | 20/s                                                                                        | 50            | 1 per action in a batch                                      |
| Final reads   | 50/s                                                                                        | 50            | 1 per GET on the final world, `GET /v1/final`, stream opened |

- Practice over-limit waits up to 1 s in the server, else 429 (no token
  taken). Final over-limit → 429 immediately, no token taken.
- Headers on charged answers: `RateLimit-Policy` (`"practice";q=166;w=1`),
  `RateLimit-Limit` (tokens/s), `RateLimit-Remaining`, `RateLimit-Reset` (ms
  until +1 token). If remaining < cost, wait reset + one token-time per extra
  token. The kit clients do this.
- Max 8 unended practice worlds (forks count), 16 streams, 50 actions/batch.

## Errors

`{ error, field? }`.

| Code                          | Meaning                                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| 400                           | Body/query doesn't parse; `field` e.g. `[2].prices.next_day`                                    |
| 401                           | Missing or unknown key                                                                          |
| 403                           | Not your world, route closed in the final, or fork/reveal on a ranking run                      |
| 404                           | No such world, or no final for this team                                                        |
| 409                           | Slot/stream limit, reveal before end, ranking run can't start                                   |
| 429                           | Over limit; `Retry-After` in ms                                                                 |
| 502/503/504                   | Server restarting (no JSON body); back within a minute, worlds resume. Retry and re-read state. |
| 200 + `{ ok: false, reason }` | Action parsed but can't be done                                                                 |
