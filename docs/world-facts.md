# Spread level 8: measured facts

Measured on 14 Nov from 2,906 recorded practice weeks (359 level-8 seeds) and fork probes.
Money is game euros. "List" is the request's list price, "typical" is `referenceFeeCents`.
Rules and mechanisms: [RULES.md](spread/RULES.md), [HANDBOOK.md](spread/HANDBOOK.md). This file only adds numbers.
Revised 14 Nov 13:00 with 1,720 fee probes, 1,291 quote probes and 84 policy forks on 8 new seeds (`data/scrape/probe2/`).

## Exact

- **List price**, one car: next-day = `round(€20 + €0.25 × road km)` to whole euros. Same-day = ×1.08, within-3-days = ×0.93.
- **Fixed per seed, whatever you do:** the request stream, the driver list, each car's true facts (ready time, real hours, gearbox, plates, tyres, note deadline) and cancellations. Checked on 3 seeds × 40 policies, zero mismatches.
- **The server is deterministic and thresholds are sharp:** for one request in one world state there is a single price below which you win and above which you lose, and likewise a single fee above which a gig books (all 2,090 probes monotone).

## The week's shape

- About 1,035 requests a week (sd 3), 40 dealers, 30 places.
- Spread evenly over 09:00–18:00 (about 10% an hour) and over the days (Mon 22%, Fri 17%).
- Pickups are concentrated: Vantaa 19%, Hyvinkää 18%, Helsinki 7%, Espoo 7%.
- Option sets: same+next 45%, next only 26%, next+3-day 10%, all three 10%, same only 9%.
- 37% of cars are ready on arrival; median lead to ready is 3.3 h, 90th percentile 24 h.
- 43% carry a note, 13% have a private address, 15% electric, 5% premium, 2% trade-ins, 47% arrive in a batch.

## Drivers

- A level-8 world has a median of 777 drivers (5–95%: 649–932). 8% are experienced, 85% hold a manual licence.
- Homes: Helsinki 31%, Espoo 11%, Vantaa 9%, Tampere 8%, Oulu 7%, Turku 6%. Per-world town factors move these a lot; the driver list at minute 0 shows them.
- **Typical fee** ≈ €15.72 + €0.387 per road minute, with ±14% noise within a lane.
- **Lowest fee that books within 3 hours**, one gig probed alone at win time: median 0.76× typical (10–90%: 0.59–1.02). Never booked at any fee: 1.7%.
- Lane, hour, slack and drivers-in-town explain only 16% of that spread. The rest is who happens to be free.
- **Drive time**: actual/road-minutes median 1.00, 5–95% 0.88–1.15; long drives (3 h+) run up to 1.24.
- **Drops**: 14.6% of bookings. Chance of a drop by time held: under 1 h 0.4%, 1–4 h 4%, 4–12 h 7%, over 12 h 10%. Median drop comes 8 h after booking.

## Dealers and the competitor

- **Win curve** from randomly priced quotes (47k): 95% at 0.85× list, 85% at 1.05×, 69% at 1.25×, 47% at 1.45×, 28% at 1.65×, 11% at 1.85×.
- The 50% point is 1.40× list pooled, and 1.24–1.58× across worlds (5–95%).
- Within a world the day factor moves it by ±15% (sd). The price-war day sits about 20% below the world's level.
- Same-day's accepted multiple of list is about 13% higher than next-day's on the same request, but varies ±17% request to request.
- After removing world, day, option, lane and dealer effects, 12% noise remains per request. No table predicts a single request's threshold better than that.
- **Tuned policies' own win/loss history cannot fit this curve.** Their win rate is flat at 55–65% from 1.0× to 1.8× list, because they already quote near their own estimate. Only random prices or probes identify it.

## Economics

- Good policies so far: about €8,900 margin a week on €31k revenue, 340–350 orders won of about 1,035, ranked on 99–100% of seeds.
- Winning more is worse: policies that won about 400 orders averaged €6,000.
- One world is noisy. Margin sd across seeds is about €2,500. Two policies differ on the same seed with sd about €1,300, so a €236 average edge wins a single world only 59% of the time.
- The kit's starter wins about 900 orders and lands at 45–57% on time.
- **Marginal order, one seed, one fork point (indicative only):** from a desk at 356 orders and 84% on time, quoting 10% lower won 122 more orders and lost €9,200 more; quoting 10% higher won 114 fewer and gained €3,500.

## From the fork probes (14 Nov)

Dealers:

- **Limit at zero trust**: median 1.24x list in the probed weeks (1.29x over all recorded weeks, see below). Short lanes are lower (list under €40: 1.12x), long ones higher (€70–120: 1.34x).
- **Trust is real and is the rule's size**: each on-time order for a dealer raises its limit by 1% (fitted 0.92 ± 0.09 of that).
- **A late order** lowers that dealer's limit by about 2.1%, on top of halving its trust count.
- **Competitor reaction**: a dealer whose requests you mostly won accepts about 10% less than one you mostly lost, from the next day (the day-by-day steps are below).
- Monday limits were near 1.0x list on two of three seeds, then 1.25–1.5x. Expect to learn the level on Monday, and for trust to lift it later.

Drivers (lowest flat fee that books within 3 hours, over typical fee):

- **Pickup today costs half as much again as pickup tomorrow**: median 0.97 vs 0.66. This holds whatever the deadline.
- **No booking at any fee up to 1.8x**: 25% for pickup today, 9% for tomorrow, 29% for orders won on Friday.
- **Load**: with under 50 gigs booked, median 0.77 and 7% unbookable; with over 300, 0.94 and 25%.
- Private addresses: median 1.00 vs 0.78. Long drives (typical fee over €90) are unbookable 27% of the time.
- At the lowest fee that books, the booking comes after a median 45 minutes. A gig gets about 10 views in 3 hours.
- **Few drivers book**: about 15% of the driver list books on a weekday, 1.6 gigs each, even when fees go to 2.5x typical. Most of the list only browses.

Marginal orders (random-price desk winning 330–450 orders, forked Tue/Wed/Thu, 4 seeds):

- Quoting 10% lower won 84 more orders and lost €5,700 more: about -€67 per extra order. On-time share fell 5 points.
- Quoting 10% higher won 70 fewer and gained €2,900: about €28 saved per order shed. On-time share rose 3.5 points.
- Opening fees 0.15x typical lower or higher: no clear effect (within noise).

## From the recorded weeks (14 Nov, afternoon)

From 2.58 million recorded quotes, 3,864 recorded weeks, and 222,000 first gig postings replayed through the simulator (`sim/`).

Dealers:

- **Limit at zero trust**: 1.29x list for a typical week (5th–95th percentile of weeks: 1.14–1.46x). The day factor within a week has an sd of 14%.
- **Trust is the rule's 1%**: with each dealer's own baseline removed, the fitted step is 1.06–1.09% per on-time order. A fit without that baseline gives 1.3%, which is dealer differences, not a second mechanism.
- **A late order costs 2.1%** of what that dealer accepts. On-time orders win back almost nothing of it.
- **The competitor's answer is daily, per dealer.** Win over 55% of a dealer's requests in a day (3 or more requests) and it accepts about 7% less the next morning, 11% after two such days, 14% after three. Win under 30% and it accepts 9%, 16%, 20% more.
- **Towns**: pickups from Vantaa are accepted 8% higher, from Hyvinkää, Espoo and Helsinki 3–4% higher, from remote towns 12–22% lower (Kokkola, Vaasa, Savonlinna, Ylivieska lowest). Deliveries to remote towns are accepted 11–15% higher (Kajaani, Kouvola, Kemi), to the Helsinki region 5–8% lower. The table is `sim/lanes.json`.
- **Hour**: requests from 15:00 are accepted about 6% higher than morning ones.
- **Price war**: the day's level is about 0.77x the week's, and only from 08:00 to 18:00.
- **Outage**: found in 182 weeks, almost never on a Monday (1 of 182). Around Vantaa in 74 weeks, Hyvinkää 46, Porvoo 41. Requests picked up in the region are accepted 30–45% higher that day.
- A single request's limit still carries about 20–25% noise that no table removes.

Drivers:

- **One gig a day is the norm**: executed gigs per driver-day are 1 (75%), 2 (22%), 3 (2.5%), 4 (0.3%). A busy week recruits more drivers, not more gigs per driver. Only 5–9% of the driver list executes a gig on a weekday; 31–54% of it views one.
- **Chaining is minor.** 23% of bookings are by a driver who already holds a gig that day, but the next pickup is a median 100 km from the previous delivery (same town in 16%).
- **Drivers who live where the gig ends** book fast although they get no notification: for tomorrow's pickups they are 21% of bookings within 5 minutes and 38% of those between 5 and 30 minutes. Drivers who live within 30 km of the pickup are 62% of the bookings within 5 minutes (median 2 minutes).
- A driver's first gig of the day ends within 40 km of home in 40% of cases, against 10% of the other open gigs.
- **Booked fee over typical** rises about 6% per 100 km from the driver's home to the pickup, 6% per 100 km from the delivery to home, and 17% for a pickup today.
- **First postings**: 97% are booked in the end, 61% within 30 minutes and 79% within 3 hours, at a median 0.94x typical; 14% are dropped. Pickup tomorrow: 74% within 30 minutes, median wait 5 minutes, 0.91x. Pickup today: 46% within 30 minutes, median wait 39 minutes, 1.00x.
- **Fridays**: same-day postings book within 3 hours only 53% of the time, median wait 92 minutes. Cars ready on Friday are picked up on Friday 34%, Saturday 39%, Monday 26%. Saturday pickups are mostly booked on Saturday morning (73%).
- **Two or more orders in one gig** book fast and cheap: 81% within 30 minutes, 0.85x typical. **Trade-ins** are slow and dear: median wait 278 minutes, 1.32x typical.
- A new gig for tomorrow gets 3 to 5 viewers in its first 15 minutes; 11% of the viewers who live near the pickup book it.
- Under overload (the starter's weeks): 59% on time, about 330 late deliveries and 250 drops a week, and only 55% of new postings find a driver once 150 gigs are booked.

Where the money is (the simulator's oracle, `pnpm oracle`, on spread-1, spread-2 and nov-1; the simulator's hidden values, so indicative):

- One markup and one fee rule for the whole week, chosen in hindsight: about €14,000–16,000.
- Knowing every dealer's limit: €22,000–34,000. Knowing every driver's cost: €27,000–37,000. Both: €45,000–66,000.
- Against the best recorded week of each seed (€14,000–19,000), most of the gap is **which requests to win** (€18,000–27,000), then **fees** (€8,000–12,000). Price on the orders already won is €2,000–4,000.
- The best recorded policies paid 1.5–1.6 times the cheapest driver's cost.

## Still not measured

- Whether rising fee schedules make drivers wait, and how direct offers compare with the app.
- Per-seed competitor level for the recorded seeds.
