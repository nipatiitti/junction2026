# The `lean` strategy

The whole policy in three decisions. Every constant is one of the level 8 facts measured on 14 November from 2,906
recorded practice weeks and the fork probes; nothing is fitted to a seed, a dealer or a place.

```sh
pnpm dispatch --level 8 --seed spread-1          # lean is the default strategy
pnpm bench lean --level 8 --seeds spread-1..spread-5
```

## 1. The price (`demand.ts`, `index.ts`)

- **What wins.** For one option of one request there is one price below which the dealer takes it. Its log, as a
  multiple of the list price, is a sum of effects: the world, the day, the dealer, the pickup place, the delivery place
  and the option. Each effect is a mean and a variance, and every quote that wins or loses moves each by its share of
  the doubt (a diagonal Kalman step on a logistic curve). The priors are the facts: half of the quotes win at 1.40 ×
  list, worlds differ by 7%, days by 15% (the price war is one such day), same-day takes 13% more, and 12% of noise
  stays in every request. Each morning the dealer and place effects get some doubt back, because the competitor moves.
  The dealer's trust (1% for each order on time, halved by a late one) moves its threshold up.
- **What it costs.** The typical fee × what this week's bookings paid (0.84 before any booking), more when the gig
  has little time to find its driver, for a private address (+0.25 × typical), a trade-in, a weekend, a note that narrows the work, and × 3 for a premium
  car.
- **What capacity is worth.** Drivers can move about a third of what dealers ask for, and the facts say that winning
  more loses money. So each order also costs `capacity` × its typical fee, the worth of its place in the week. Half of
  it is the same for every order (`flatShare` × `flatEuros`): a short hop takes a driver's place as a long one does.
  That worth rises with each win and falls with each loss, so that we win `target` of the requests (0.30 × the
  world's drivers over 777). The target falls when bookings cost more than planned, when more than 40 gigs wait without a
  driver, and when orders arrive late. Requests that arrive together from one yard, as a bulk order, count more.
- **The quote** is, for each option, the price with the highest chance × (price − cost − worth of capacity). With
  the worth of capacity high, this prices the requests where the competitor is dear high and still wins them, and
  loses the others: we win the dearest third, not the first third.

## 2. The fee (`fees.ts`)

Drivers learn that our fees rise and wait for the rise. In the first weeks of a slow climb from 0.68 × typical, 65% of
the drivers who booked had viewed the gig earlier at a lower fee and came back, and paid 1.04 × typical at the median;
drivers who booked on their first view paid 0.80 ×. So the fee holds still and rises rarely:

- **Stepped** (`stepped`, the default): the gig opens at `open` × typical (0.88) and rises only 24, 16, 10 and 6 hours
  before the last pickup, to 1.05, 1.25, 1.55 and 2 × typical. With `jitter` 1, each gig's rises move by up to 1.5
  hours and 5%, drawn from the order id, so a driver cannot plan a second look for the rise.
- **Flat, then late** (`stepped=false`): `open` until four fifths of the time to book are gone (`climbTo` above `open`
  adds a slow climb first), then to 1.30 and to 2 × at the end. It pays more on easy worlds and is late on hard ones.
- From the deadline warning on, or with under 45 minutes left, the fee rises 12% every 15 minutes to 2 ×; a car that
  is late already rises to 1.7 ×. A gig that a driver gives back starts again from the fee that booked it.

## 3. Chains (`chains.ts`)

Several open cars go as one gig when one driver can take them one after the other. The open single-car gigs are the
nodes of a graph, with an edge where the next car is collected within `maxHop` road minutes (60) of the last delivery.
The search walks every path of up to `maxCars` cars (4) inside 11.5 hours of driving, keeps the paths a driver can do
inside every window, opening hour and deadline, and takes the ones that save the most, each car once.

A chain's fee unit is what it costs a driver: one fixed part, the drive with the hops, and the trip home from the last
delivery to the first pickup, so a loop pays no trip home. A chain is posted when that is `minSaving` (15%) under its
cars' typical fees: on the strategy's tick the cars' own gigs are withdrawn and one gig carries them. A chain that no
driver took `chainHours` (5) before its last start is withdrawn, and its cars go back to single gigs for good.

`holdHours` (0, off) lets a new car wait for a partner before it is posted alone; it is built and not yet played.

## 4. The service (`src/ops`)

Only options that `canServe` says can arrive on time with five hours to spare are quoted (ten once 5% of the orders
are late), and only with `minHours` waking hours left to book a driver. The note decides the windows, plates and
licence of every gig, and a failed visit or an expired gig posts the car again with what it taught.

## What the saved weeks showed, and what each change did

Each change was played alone against the defaults of its time, on the same seeds (level 8, margin a week).

| Change                                     | Why (from the saved weeks)                                                |                      Mean difference | Seeds ahead |
| ------------------------------------------ | ------------------------------------------------------------------------- | -----------------------------------: | ----------: |
| Flat fee 0.88 instead of the climb         | 65% of bookers had waited for a rise                                      |                              +€2,272 |      5 of 5 |
| `flatShare` 0.5                            | orders under €25 typical earned €13 each and were half of the late orders |                              +€1,314 |      5 of 5 |
| `premium` 3, `privateAddress` 0.25         | premium cars 29% late at 1.37 × typical; private addresses 1.24 ×         |                              +€1,183 |      5 of 5 |
| Chains                                     | every car paid its own trip out and home                                  |                                +€973 |      5 of 5 |
| `flatShare` 1                              |                                                                           |             +€584, one week unranked |      3 of 5 |
| `buffer` 0.12 (twice)                      | a third of late orders had a driver in time                               |                          +€117, −€42 |      2 of 5 |
| `capacity` 0.7, `target` 0.36, `open` 0.80 |                                                                           | −€516, +€313 (one unranked), −€1,063 |             |

On those five seeds the defaults then made €15,035. On five fresh seeds the same defaults made €11,161 and three weeks
fell under 90% on time: gigs expired unbooked (13 a week) because the flat fee rises too late. Stepped fees made
€11,653 there with every week ranked (91–97% on time), and on the first five seeds €13,122 without chains, also all
ranked. So `stepped` is the default: an unranked week scores nothing. Chains book at 0.66–0.78 × their cars' typical
fees and carry about 30 cars a week; half of all single gigs book within 24 minutes, before a partner arrives.

## Params

`target` 0.3, `capacity` 0.4 (its start), `gain` 0.02, `flatShare` 0.5, `flatEuros` 60, `open` 0.88, `climbTo` 0.88,
`stepped` true, `jitter` 1, `buffer` 0, `premium` 3, `privateAddress` 0.25, `feeRatio` 0.84, `overhead` 0.06,
`minHours` 4, `minMargin` 1.05, `trust` 0.7, `lateSoft` 0.04, `lateHard` 0.05, `openGigs` 40, `urgentTop` 2,
`lateTop` 1.7, `chains` true, `maxHop` 60, `maxCars` 4, `minSaving` 0.15, `chainHours` 5, `holdHours` 0. Override one
with `--set key=value`. The end of a week prints the share won, the mean price × list, the mean fee × typical, the
late orders and the chains posted, booked and taken apart.
