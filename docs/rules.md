# Rules (short)

Condensed from [RULES.md](https://spread.bahnexpress.com/kit/RULES.md)
(13 Nov 2026). The original is authoritative. All amounts in game euros; the
API uses whole cents and whole world minutes from Monday 00:00.

## Goal and ranking

- Score = gross margin = sum of your account (prices in; driver fees, refunds,
  penalties, fines out).
- **Delivery minimum:** at least 90% of won orders on time, or you are not
  ranked. Winning no order = not ranked. Cancelled orders do not count.
  Undelivered at the end counts as late.
- Equal margin to the cent shares a rank.
- Final: the 10 ranked teams with the highest margin present; a jury picks
  winners (elegant, clear, creative, robust).

## The week

- Requests arrive Mon 08:00 – Fri 18:00, almost all 09:00–18:00.
- Saturday: sites open short hours, some closed. Sunday: all closed.
- Next Monday is a business day with no new requests; last deadlines fall on
  it. World runs to Wednesday 22:00 so late cars can still arrive.
- Every deadline is 20:00 on a business day. Latest possible: 20:00 last Monday.

## Price requests

A request has: dealer; 1–2 legs (one car pickup → delivery; a trade-in is two
legs, new car out + old car back, one price); per stop a private-address flag
and a window; delivery options with deadline and list price; a typical fee
(`referenceFeeCents`); maybe a note; `respondBy` = arrival + 15 min.

- Pickup window starts at the stated ready time. At a dealer site it ends at
  the latest option's deadline (after winning: the won option's deadline);
  opening hours say when the site is open. At a private address the window is
  a booked slot (starts ≥ 1.5 h after `respondBy`).

| Option | Deadline |
| --- | --- |
| `same_day` | 20:00 the day the car is ready. Only if the request arrives by 15:00 that day and the drive can end 2 h before the deadline. |
| `next_day` | 20:00 next business day (Friday-ready → Monday). |
| `within_3_days` | 20:00 on the 3rd business day after ready day, not after the last Monday. |

- A private delivery or trade-in carries one option only. A private delivery
  is due 30 min after its booked hour ends.
- Quote one price per option you offer (any subset, at least one). A new
  quote replaces the old one; you cannot withdraw a quote.
- To decline: quote far above list price (a losing quote costs nothing). Not
  quoting costs a little dealer goodwill. Up to level 3 every quote wins, so
  there decline by not quoting.
- The dealer decides at `respondBy` on your last quote, comparing your prices
  with the competitor's and with the value of each option's speed. Quotes at
  or after `respondBy` are refused.
- List price = public price by distance. Competitor ≈ list price up to level 6;
  well above at levels 7–8.
- Late/undelivered cars make that dealer accept only lower prices from you;
  each on-time car wins back a little.

## Gigs

A gig = one or more legs in a fixed order of stops, posted with:

- **Stops**, each optionally with its own window: may not start before the
  order's window; at a private pickup must end inside the slot; elsewhere may
  end after the order's window (so late cars can still move). Without its own
  window a stop uses the order's window cut to stated hours; once that has
  ended (or no driver can still make it), stops without windows run to world
  end. A private slot never extends.
- Pickup options: `withPlates` (+30 min), `withCharging` (+40 min).
- **Audience:** everyone, or experienced only (rating ≥ 4.8 and ≥ 50 gigs);
  and/or manual licence required.
- **Fee schedule:** 1–48 steps `(time, fee)` in time order, fees never fall.
  App shows the latest started step (before the first starts, the first fee).
  Level 1: one step only.

Gig rules:

- A multi-car gig may plan at most **12 h of driving** (map road minutes,
  first pickup → last delivery, including drives between cars; plates and
  charging excluded). Single car: no limit. Split a long trade-in into two gigs.
- Trade-in gig: put the old car's pickup right after the new car's delivery;
  the driver collects it in the same visit however late. Posted alone, the old
  car must be collected inside the slot; if the slot passes, the dealer
  rebooks the same hours next business day (`order_changed`).
- Reprice (replaces the whole schedule) or withdraw only while unbooked.
  Raises send no notification.
- A gig with an already-ended stop window is refused. An open gig leaves the
  app the minute after its first stop window ends (`gig_expired`).
- A driver books only if they can reach every stop inside its window (road
  minutes + plates/charging). E.g. a 7 h drive due 20:00 gets no driver after
  13:00.
- Booked driver who can't make the first pickup window: `driver_late` with
  `pickupAt` at an open dealer site (they still come; free release until they
  leave), else `no_show` (gig reopens).
- Drivers may drop a booking any time before leaving; likelier the longer they
  hold it and when the fee only just paid; rare at night. A driver who dropped
  rebooks only at a higher fee. → `gig_dropped`, gig reopens.
- No driver 3 h before `lastPickupAt` → `deadline_close`. `lastPickupAt` = last
  minute to collect the first undelivered car and still deliver all legs on
  time (road minutes, EV charging, delivery stated hours). Reset on win, snow,
  change of plan, or a delivered leg. Warning repeats if the order loses its
  driver or `lastPickupAt` moves later; at most one pending.
- **Release** a booked driver until `gig_started`: fee 25% of the fee if
  pickup > 24 h away, 50% if less, 100% if < 2 h. Free after `driver_late`.

## Drivers

- Live in towns; not all work every day (you can't see who does).
- Cost to a driver: driving time + public transport to pickup (cheap ticket
  bought ahead) + trip home (dear ticket bought on the day) + extras (evening,
  weekend, private address, trade-ins, charging, plates). A far morning pickup
  may need a night away (more expensive).
- They book when fee − cost beats their other options and what they expect from
  waiting for a raise. Later-day gigs only if they know they work that day.
- Drivers learn your fee rises (from level 2) from orders they viewed and could
  do: how far the fee rose and how long it stayed open. A reposted car keeps
  its age. Close to pickup they wait less.
- Notified of a new gig when the first pickup is within 30 km (straight line)
  of home. Snow keeps some home (they drop same-day bookings).
- `GET /drivers`: home town, rating, licence, completed gigs, drops. You see a
  driver's position only while they work your gig, and each view of your gigs.

## Direct offers

- One gig to one driver for 10 min at your fee; the gig can also be in the app.
- Max 3 offers per driver per day; max 3 open offers per gig.
- No reading 23:00–07:00. Non-working drivers read few.
- Yes arrives within 10 min and books. `declined` / `expired` arrive after.

## Notes

Finnish, Swedish or English. The world follows the note whether you read it or
not.

- Days count from arrival day. No day / "tänään" / "idag" / "today" = same day.
  "huomenna" / "i morgon" / "tomorrow" (+ "tmrw", "imorgon") = +1;
  "ylihuomenna" / "i övermorgon" / "the day after tomorrow" = +2.
- A weekday name (incl. short forms like "to.", "Thurs") = that weekday 2–6
  days after arrival. Arrival day and next day are never named by weekday.
- Digits = 24 h clock unless am/pm. Hour in words (FI/SV) = working hour 9–17:
  "two" = 14:00, "half three" = 14:30.
- Corrections count; denied times ("not 3pm") do not. A note can hold several
  facts or none.
- Handover after payment: no pickup before the note's time; a `release` event
  comes then.
- After winning, the dealer may redirect a car (`order_changed`; world reroutes
  it even mid-gig; you pay extra driving) or cancel. On cancel each live gig
  with its cars is `withdrawn` (repost other cars), `released` (release fees
  apply), `shortened` (keeps other order's car, same fee) or `continues`
  (driver already left; skips the car; you pay the full fee).

## Rules for handling cars

1. Premium car → experienced driver only. Fine €150 per car.
2. Multi-car gig ≤ 12 h planned driving.
3. EV below 30% charge on a route over 200 km needs a charging stop; otherwise
   +90 min late and €100 fine.
4. Dealer sites accept deliveries only in opening hours. Arriving when stated
   hours show closed: car left at once, counts at next opening, no waiting fee.
   Closed when stated hours show open (per note): driver waits up to 2 h at
   €15/h, then leaves the car; counts at next opening.
5. Private delivery: deadline = end of booked hour + 30 min. Early arrival
   waits for free.

## Your account

| Line | Amount |
| --- | --- |
| Delivered order | Your quoted price (credited when the order's last car is delivered) |
| Late ≤ 2 h | 10% refunded |
| Late 2–24 h | 25% refunded |
| Late > 24 h, ≤ 2 business days | 50% refunded |
| Late > 2 business days | 100% refunded; car must still be delivered |
| Not delivered by Wed 22:00 | No price, penalty 2 × price |
| Driver fee | Paid when the gig is done |
| Failed visit | Half the car's share of the gig fee, min €25 |
| Release | See Gigs |
| Fines, waiting | See rules for handling cars |

- Failed visit causes: not ready / not paid, site closed, private seller absent
  outside slot, wrong licence, no plates. Multi-car gigs continue with the rest.
- On time = every leg delivered by its deadline. A car ready ≥ 1 day late moves
  the deadline by the same days (already in `order_won`). Lateness in business
  days skips Sat/Sun.

## Practice, levels, final

- Practice worlds stand still until `advance`. Deterministic: same seed, level
  and actions → same week to the cent. `fork` copies a world with the same
  future. Reveal after the end (not competitor prices or driver costs).
  Ranking runs cannot be forked or revealed.
- Up to level 6: ±20% drivers vs average, competitor level ±10% around list
  price. Part of each lane's competitor price is the same in every world.

| Level | Adds |
| --- | --- |
| 1 Posting | One car, one fee per gig. No competitor; every quote wins first option at list price (up to level 3). Cancellations. |
| 2 Market | Fee schedules; drivers learn your fees and drop bookings. |
| 3 Network | Multi-car gigs and direct offers (same world as level 2). |
| 4 Quotes | Competitor; dealer chooses between your options. |
| 5 Full | Notes, changes of plan, failed visits, handling rules, weather. |
| 6 Surprises | Unannounced: **outage** (competitor down 08:00–18:00 one working day in a town + 80 km region, dealers use a backup ~30% dearer); in some weeks **flu** (30% of planned drivers stay home a day) and **bulk order** (30–40 cars from one yard). |
| 7 Shortage | 26–40% of average drivers; competitor 12–38% above list. All three level 6 events every week. |
| 8 Trust | Shortage varies by town; competitor 26–54% above list; unannounced **price war** (one working day without outage, competitor −20% everywhere 08:00–18:00); **dealer trust**. |

- In a shortage, typical fee and list price stay at normal-week values. You can
  win more cars than can be moved; winning every car you can drops you below
  the minimum.
- **Dealer trust (level 8):** each dealer counts your on-time orders to it (max
  25); each adds +1% to the prices it accepts from you. A late order halves the
  count (round down). Starts at 0 each world. On-time = revenue line with no
  late refund.
- **Final:** one secret level 8 world, own copy per team, same requests and
  draws. Clock runs by itself (~18 real s per weekday hour). Unanswered
  requests go to the competitor. If your code stops, the world continues.
