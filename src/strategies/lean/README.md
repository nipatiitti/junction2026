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

`holdHours` (0, off) lets a new car wait for a partner before it is posted alone, `chainPatience` takes a chain apart
that no driver took after so many waking hours, and `chainBid` plans the chain before the bid; the batches below
played them.

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

## Modifiers (`mods.ts`)

The rules that the Python systems of [`strategies/`](../../../strategies/README.md) measured on their own weeks, as
switches on `lean`. Each changes one decision and is off by default. **None has been played on `lean` yet.**

| Param                 | From                     | What it does                                                                                                                                                                                                                                                      | What the Python weeks measured                                                                          |
| --------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `dawn`, `dawnTop` 1.7 | `dawn_fees`, `all_in`    | Fees by the drivers' day: 0.9 × typical, 1.0 after an hour, held through every night; from the last 06:00 that leaves 3 hours, hourly steps from 1.05 to the top 7 hours before the last pickup; a gig with no morning opens at 1.1 and climbs in 15-minute steps | 74% of the gigs open at 06:00 book by 08:00, at any fee; +€1,772 on `spread-1` beside the lead cost     |
| `leadCost`            | `lead_cost`              | The driver cost from a table by hours to the last pickup and to the ready time: 2.4 × typical under 8 hours, 1.77 under 14, 1.03 for a car ready the next day                                                                                                     | +€1,668 on `spread-1`; scaling the table by 0.85 or 1.15 lost €8,000 to €10,000 over five weeks         |
| `bestOption`          | `lead_cost`, `same_day`  | Quotes only the option with the most expected margin                                                                                                                                                                                                              | A car ready tomorrow goes as `same_day` (8% dearer on the list, cost 1.03)                              |
| `pairDiscount`        | `pair_first`             | This share off the cost of a request that can go on with one of our open cars (0.15 there)                                                                                                                                                                        | +€245 a week on headroom, ahead on 3 of 4 seeds; lost with a low opening fee                            |
| `areaCap`             | `lead_cost`              | A pickup area holds this many open orders without a driver for each driver living within an hour (0.20 there, 2 at least)                                                                                                                                         | Half of it (0.10) lost €171 a week over 22 seeds                                                        |
| `priceCap`            | `headroom`               | No price above a maximum that starts at 1.39 × list and moves 0.6% up on a win at it and down on a loss, between 1.20 and 1.62                                                                                                                                    | +€855 on `spread-1`; cheaper prices lose online because the competitor undercuts a dealer we mostly win |
| `laneFee`             | `lane_fee`               | This share of the typical fee from the lane's road minutes instead of the request's own noisy figure                                                                                                                                                              | part of headroom's +€225                                                                                |
| `shortDrive`          | `lead_cost`              | Added × typical for a drive under 30 minutes (0.12 there)                                                                                                                                                                                                         | a short drive costs 14% more over its typical fee                                                       |
| `minEuros`            | `alignas` (another team) | The least margin a quote keeps (€8 there)                                                                                                                                                                                                                         |                                                                                                         |

Left out: the flu guard, trust farming, the outage reserve and the town opening fee each moved a week by under €250,
within what chance gives; `joint_bid` and lower opening fees under a ladder lost.

### How `lean` compares

- **`all_in`, the best Python system, is ahead.** Over 22 seeds it makes €12,268 a week, every week ranked, with 320
  orders at about 98% on time. `lean` makes €11,653 on five fresh seeds with 203 orders at 91–97% on time, and
  €9,497 against €13,592 on `spread-1`.
- **What `lean` has that they do not**, none of it proven against them: the chain search over every path of up to four
  cars with a loop priced without a trip home (their bundler appends or inserts greedily, three cars at most); the
  raises drawn per gig (`jitter`); the win model that learns each dealer and place during the week; a practice week
  in a few hundred requests.
- **Same finding on both sides:** drivers wait for raises, so a low opening under a ladder loses (their 0.55 opening
  lost €16,189 over three weeks; our slow climb lost €2,272 a week).

### Why the leaders are ahead, and what to try

The level 8 ranking round "Saturday 12:00" shows each team's orders. On its first world:

| Team                  |  Margin | Orders | Margin an order | On time |
| --------------------- | ------: | -----: | --------------: | ------: |
| No Empty Miles        | €21,290 |    477 |           €44.6 |     99% |
| Progresful            | €20,085 |    470 |           €42.7 |     97% |
| DaVinci's Night Shift | €18,866 |    433 |           €43.6 |     97% |
| House best            | €15,800 |    394 |           €40.1 |     96% |
| `lean`                | €11,718 |    270 |           €43.4 |     94% |

`lean` earns as much an order as the leaders. They win 430 to 500 orders a world, 45% of the requests, where `lean`
wins 270 and `all_in` 320 to 370, and they still arrive on time. So the measured fact that "winning more is worse" holds
only for a desk that cannot move the cars: the gap is volume at the same margin, and volume is bounded by lateness.

Hypotheses, in the order to play them:

1. **Admit by lead time** (`leadCost`, `bestOption`). Our late orders and dearest bookings are cars to collect the same
   day; the Python table prices them at 1.8 to 2.4 × typical, which declines them, and takes cars ready tomorrow at
   1.03. Fewer late orders lift the brake that holds our volume at 20–26% of the requests.
2. **Fees by the drivers' day** (`dawn`). A gig booked the day before it starts cost us 0.89 × typical against 1.13 ×
   on the day, and their weeks show the 06:00 planning hour takes what the app shows. Stepped fees count hours back
   from the last pickup and ignore the hour of the day.
3. **Then raise the target** (`target` 0.40 to 0.45) once weeks hold 97% on time. At 45% of the requests a quote must
   win at about 1.40 × list, 6% under our 1.49, so the margin an order holds only if drivers cost about 0.75 × typical.
4. **Chains for half of the cars, not an eighth** (`holdHours`, `pairDiscount`). A chain books at 0.66–0.78 × its cars'
   typical fees and moves three cars with one driver, which is both the cost and the capacity that 45% needs. Half of
   our single gigs book within 24 minutes, before a partner arrives, and 99% get a partner within a day.
5. **A price maximum** (`priceCap`) to stop teaching the competitor to undercut the dealers we win most; our Friday
   wins fall to 15% of the requests.

### What the first plays of these showed

Each batch is five fresh random seeds, with the baseline on the same seeds (level 8, mean margin a week).

| Batch | Variant                                                            |  Margin | Orders | On time | Unranked |
| ----- | ------------------------------------------------------------------ | ------: | -----: | ------- | -------: |
| 1     | baseline                                                           | €10,789 |    212 | 96–98%  |        0 |
| 1     | volume: `target` 0.45, `feeBrake` 0, `openGigs` 120, `holdHours` 1 | €11,388 |    359 | 92–98%  |        0 |
| 1     | every modifier above                                               |  €9,689 |    323 | 84–95%  |        1 |
| 1     | both                                                               |  €9,903 |    416 | 82–95%  |        2 |
| 2     | baseline                                                           |  €9,691 |    203 | 93–98%  |        0 |
| 2     | `holdHours` 1, `openGigs` 120                                      |  €9,675 |    200 | 93–100% |        0 |
| 2     | that, `pairDiscount` 0.25, `pairCharge` 0.3                        |  €9,627 |    290 | 88–98%  |        1 |
| 2     | that, `chainPatience` 6                                            |  €9,863 |    287 | 90–98%  |        0 |

- **Volume is ours to set, and it is worth little without cheap drivers.** 70% more orders made €598 more: the margin
  an order fell from €51 to €32, because every price fell (1.56 to 1.46 × list) and single gigs cost 1.16 × typical.
- **A car in a chain is the order that scales.** With `holdHours` 1, 55 to 117 cars a week ride in chains at 0.72 ×
  their typical fees and earn €42 to €49 each, 1.4% to 3.4% late.
- **A chain that comes apart is the leak.** Its cars book 30 hours after the win at 1.40 × typical and earn €8 to
  €11; `chainPatience` 6 lifts that to €27 and halves their late share.
- **`pairDiscount` leaks.** "An open car within half an hour" is true for most requests, so 161 single cars a week
  were sold at the chain price (1.45 × list) and earned €32 against €50. `chainBid` gives the chain price only to a
  request with a feasible chain among the cars we hold, each of which backs one bid at a time.
- **The modifiers as a set lose on `lean`.** `priceCap` caps the price that our capacity charge raises to hold volume,
  so the week takes more than it can move; `leadCost` prices a car ready tomorrow at 1.03 × typical, and big orders
  earned €35 against €69. Each needs its own batch.

The defaults are unchanged: every param of this section is off.

## Params

`target` 0.3, `capacity` 0.4 (its start), `gain` 0.02, `flatShare` 0.5, `flatEuros` 60, `open` 0.88, `climbTo` 0.88,
`stepped` true, `jitter` 1, `buffer` 0, `premium` 3, `privateAddress` 0.25, `feeRatio` 0.84, `overhead` 0.06,
`minHours` 4, `minMargin` 1.05, `trust` 0.7, `lateSoft` 0.04, `lateHard` 0.05, `openGigs` 40, `urgentTop` 2,
`lateTop` 1.7, `chains` true, `maxHop` 60, `maxCars` 4, `minSaving` 0.15, `chainHours` 5, `holdHours` 0, and the modifiers above. Override one
with `--set key=value`. The end of a week prints the share won, the mean price × list, the mean fee × typical, the
late orders and the chains posted, booked and taken apart.
