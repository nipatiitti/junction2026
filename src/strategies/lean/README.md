# The `lean` strategy

The whole policy in three decisions. Every constant is one of the level 8 facts measured on 14 November from 2,906
recorded practice weeks and the fork probes; nothing is fitted to a seed, a dealer or a place.

```sh
pnpm dispatch --level 8 --seed spread-1          # lean is the default strategy
pnpm bench lean --level 8 --seeds spread-1..spread-5
```

`strategies/lean/` is a Python port that plays the same weeks action for action. A change to either version gets an
entry in [`LEAN_CHANGELOG.md`](../../../LEAN_CHANGELOG.md) in the same PR.

## 1. The price (`demand.ts`, `index.ts`)

- **What wins.** For one option of one request there is one price below which the dealer takes it. Its log, as a
  multiple of the list price, is a sum of effects: the world, the day, the dealer, the pickup place, the delivery place
  and the option. Each effect is a mean and a variance, and every quote that wins or loses moves each by its share of
  the doubt (a diagonal Kalman step on a logistic curve). The priors are the facts: half of the quotes win at 1.40 ×
  list, worlds differ by 7%, days by 15% (the price war is one such day), same-day takes 13% more, and 12% of noise
  stays in every request. Each morning the dealer and place effects get some doubt back, because the competitor moves.
  The dealer's trust (1% for each order on time, halved by a late one) moves its threshold up.
- **What it costs.** The typical fee × `costLevel` (0.98) × what this week's bookings pay for such a car (`supply.ts`:
  the world, the pickup place, the delivery place, a pickup today; 0.84 before any booking) × what the order model
  says of this request against the mean order (`outlook.ts`, mean 1), plus `lateCost` × the list price × its chance
  to be late, and × 3 for a premium car. `costLevel` is the only level of the cost. The supply learns each booking
  over what the order model expected of that car when it was won, so a place effect holds only what the model does
  not say already.
- **What an order costs the others.** Each order per driver more raises the fee of every booking by 0.355 × typical
  and the refunds by €6.51 an order, so one more order costs the rest of the week €28.7 × the orders per driver:
  0.47 of the mean order's cost (`taxLoad`). The week's load is the share of the requests won so far, over a week's
  1,033 requests and the world's drivers.
- **The quote** is, for each option, the price with the highest chance × (price − cost − that charge), on a win
  curve of the dealers' measured scale (`noise` 0.11). A week that wins more raises its own charge, so it settles
  where the next order earns nothing. [Supply and demand](#supply-and-demand-15-november) has the fit.

## 2. The fee (`fees.ts`)

Drivers learn that our fees rise and wait for the rise. In the first weeks of a slow climb from 0.68 × typical, 65% of
the drivers who booked had viewed the gig earlier at a lower fee and came back, and paid 1.04 × typical at the median;
drivers who booked on their first view paid 0.80 ×. So the fee holds still and rises rarely:

- The gig opens at `open` × typical (0.88; 0.8 in its first waking hour when it is for a later day) and rises three
  times over the waking time that drivers have to plan it (`planBy`: by 21:00 the evening before for a last pickup
  before 16:00, else 5 hours before it): after 0.3, 0.55 and 0.8 of that time to 1.05, 1.25 and 1.55 × typical, and
  to `urgentTop` (1.6) when the time is over. With `jitter` 1, each raise moves by up to 20 minutes and 5%, drawn from
  the order id, so a driver cannot plan a second look for the rise.
- A gig posted with under an hour of planning time left (`lateWithin`) opens at `lateOpen` (1.25) and climbs as an
  urgent one.
- The urgent climb, from the deadline warning on or with under 45 minutes left to book: from `urgentOpen` (1.15),
  `urgentStep` (0.125) every `urgentEvery` (15) waking minutes to `urgentTop`. A car that is late already climbs
  from `lateFrom` (1.1) by `lateStep` (0.05) every `lateEvery` (30) minutes to `lateTop` (1.3). A gig that a driver
  gives back starts again from the fee that booked it.
- Every time in a schedule counts waking minutes (07:00 to 21:00): a raise at night shows to nobody.
- A gig whose last pickup is on the Monday after the weekend, posted before that Monday 06:00, keeps its opening
  fee over the weekend and raises on the Monday: from 06:00 to its usual planning minute, or to 3 hours before the
  last pickup when that minute fell on the Sunday (`rest`, #347). Of such cars 2 a week were booked on a Sunday and
  31 on the Monday, at the 1.54 × typical that the weekend's raises had left. `rest` false spreads the raises over
  the weekend as before.

## 3. Chains (`chains.ts`, `planner.ts`)

Several open cars go as one gig when one driver can take them one after the other. The open single-car gigs and the
cars that wait for a partner are the nodes of a graph, with an edge where the next car is collected within `maxHop`
road minutes (60) of the last delivery. The search walks the paths of up to `maxCars` cars (4) inside `maxDrive`
hours of driving (8), in the order of the cars' ids and 20,000 paths at most, keeps the paths a driver can start
right away and do inside every window, opening hour and deadline, and takes the ones that save the most, each car
once.

A chain's fee unit is what it costs a driver: one fixed part, the drive with the hops, and the trip home from the last
delivery to the first pickup, so a loop pays no trip home. A chain must be `minSaving` (15%) under its cars' typical
fees. Three rules decide the rest, each written once in `planner.ts`:

- **Which chain is posted** (`postable`): from Monday to Thursday, with `pickLead` hours (20) to its first last
  pickup, and with a car that no driver has seen.
- **When a chain may be in the app** (`mayBeOpen`): while drivers have `chainLast` waking hours (3) left to plan the
  day of its last start. The same rule posts it (with its `chainPatience` on top), withdraws it, and decides whether
  a new car waits `holdHours` (2) for a partner.
- **How long it stays** (`chainPatience`): one waking hour without a driver, then its cars go back to single gigs
  for good.

Everything the planner knows of a posted chain it reads from the post action and the world's answer, so a week that
is rebuilt from the journal has the same chains.

## 4. The service (`src/ops`)

Only options that `canServe` says can arrive on time with five hours to spare are quoted (ten once 5% of the orders
are late), and only with `minHours` waking hours left to book a driver. The note decides the windows, plates and
licence of every gig, and a failed visit or an expired gig posts the car again with what it taught.

## What the saved weeks showed, and what each change did

Each change was played alone against the defaults of its time, on the same seeds (level 8, margin a week).

| Change                                                    | Why (from the saved weeks)                                                |                      Mean difference | Seeds ahead |
| --------------------------------------------------------- | ------------------------------------------------------------------------- | -----------------------------------: | ----------: |
| Flat fee 0.88 instead of the climb                        | 65% of bookers had waited for a rise                                      |                              +€2,272 |      5 of 5 |
| `flatShare` 0.5                                           | orders under €25 typical earned €13 each and were half of the late orders |                              +€1,314 |      5 of 5 |
| `premium` 3, `privatePickup` 0.25, `privateDelivery` 0.25 | premium cars 29% late at 1.37 × typical; private addresses 1.24 ×         |                              +€1,183 |      5 of 5 |
| Chains                                                    | every car paid its own trip out and home                                  |                                +€973 |      5 of 5 |
| `flatShare` 1                                             |                                                                           |             +€584, one week unranked |      3 of 5 |
| `buffer` 0.12 (twice)                                     | a third of late orders had a driver in time                               |                          +€117, −€42 |      2 of 5 |
| `capacity` 0.7, `target` 0.36, `open` 0.80                |                                                                           | −€516, +€313 (one unranked), −€1,063 |             |

On those five seeds the defaults then made €15,035. On five fresh seeds the same defaults made €11,161 and three weeks
fell under 90% on time: gigs expired unbooked (13 a week) because the flat fee rises too late. Stepped fees made
€11,653 there with every week ranked (91–97% on time), and on the first five seeds €13,122 without chains, also all
ranked. So `stepped` is the default: an unranked week scores nothing. Chains book at 0.66–0.78 × their cars' typical
fees and carry about 30 cars a week; half of all single gigs book within 24 minutes, before a partner arrives.

## Modifiers (removed)

`lean` once carried the rules of the Python systems of [`strategies/`](../../../strategies/README.md) as switches:
their fee schedule by the drivers' day (`dawn`), their cost table by lead time (`leadCost`), one option per quote
(`bestOption`), a discount for a request near one of our open cars (`pairDiscount`), a limit of open orders per
pickup area (`areaCap`), a moving price maximum (`priceCap`), the lane's typical fee (`laneFee`), a surcharge for
short drives (`shortDrive`), a least margin (`minEuros`) and an early delivery window (`buffer`). The batches below
played them: together they lost €1,100 a week and a ranked week, and none won alone. They are removed from the code;
the results stay here.

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
| 3     | baseline                                                           | €12,034 |    227 | 95–100% |        0 |
| 3     | `holdHours` 1, `openGigs` 120, `chainPatience` 6                   | €12,399 |    227 | 95–98%  |        0 |
| 3     | that, `chainBid`, `pairCharge` 0.3                                 | €12,146 |    259 | 95–97%  |        0 |
| 3     | that, `chainBid`, `pairCharge` 0                                   | €11,306 |    424 | 86–97%  |        2 |

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

- **`chainBid` moves the right cars and still does not pay yet.** With `pairCharge` 0.3 it adds 32 orders a week and
  95 cars ride in chains at 0.69 × typical, for €112 more than the baseline (ahead on 3 of 5 seeds), within what chance
  gives. With no capacity charge at all it wins 424 orders, 106 of them in chains that come apart, and two weeks fall
  under 90% on time. The hold with `chainPatience` 6 made €365 more on batch 3 and €17 less on batch 2.

The defaults are unchanged: every param of this section is off. What is left to do for volume: stop chains from coming
apart (a third of those posted do), then raise the chain share of the bids step by step.

## Simulator batches (14 November, evening)

Played on the offline simulator ([`sim/`](../../../sim/README.md)): 40 recorded seeds per batch, every variant on the
same seeds, mean margin a week. The simulator agrees with the server on the winner of a pair in 90% of the cases
for gaps of €500 to €1,500 and in all cases above that; it does not rank on-time shares, is too gentle on overload
and is unreliable on fee timing. The server check is at the end of this section.

| Change                                                                                  | Margin            | Orders    | On time      | Against                          |
| --------------------------------------------------------------------------------------- | ----------------- | --------- | ------------ | -------------------------------- |
| Old defaults (`capacity` 0.4, `gain` 0.02, `noise` 0.08, no hold)                       | €15,251           | 246       | 96.8%        |                                  |
| `target` 0.45 / 0.6                                                                     | €15,761 / €14,829 | 332 / 402 | 96.6 / 95.7% | old: +€604 ± 187 / −€328 ± 262   |
| No capacity charge, `noise` 0.08                                                        | €12,740           | 482       | 93.6%        | old: −€2,416 ± 347               |
| No capacity charge, `noise` 0.28                                                        | €16,213           | 297       | 96.7%        | old: +€1,057                     |
| … and `holdHours` 2 (chain first)                                                       | €17,039           | 296       | 97.0%        | row above: +€826 ± 150           |
| … and the booking cost learned per car                                                  | €17,432           | 328       | 96.8%        | old: +€2,181 ± 186, 38 of 40     |
| … and the cost learned by place and by today's pickups (`supply`, **the new defaults**) | €18,200           | 362       | 96.6%        | row above: +€769 ± 161, 32 of 40 |
| … and `spread`                                                                          | €18,917           | 384       | 94.4%        | new: +€717 ± 223, 1 unranked     |

What they showed:

- **Volume alone pays nothing.** With the old win model, more orders came only at lower prices: the margin per order
  fell from €63 to €37 between 242 and 402 orders, at the same cost per order.
- **The win model was too sure.** With a noise of 0.08 it saw a steep win curve and priced low once the capacity
  charge was gone. With 0.28 the best price needs no charge and no controller (0.22 and 0.33 are both worse).
- **The cost of a booking differs by place more than by order** (`supply.ts`). One cost ratio for the week bids
  the same on a car that ends where drivers live and on one that ends where none do. Learning the ratio by pickup
  place, delivery place and today's pickups during the week wins 34 more orders at the same on-time share. More
  effects in it (order size, weekday, lane) add nothing.
- **Chain first.** A new car that waits up to 2 hours for a partner lifts the chained cars from about 55 to about
  200 of 300 a week, at 0.69 × typical; 4 hours loses €780.
- **Did nothing measurable, and are not in the code:** choosing chains by their chance to book (from driving time,
  trip home and drivers at the end town), limits on a chain's driving time and trip home, several chain tries per
  car, the dealer tables (towns, hour, order size, the competitor's daily answer). **Lost or flat:** bidding lower for a dealer's trust (−€800 to −€1,100), `overhead` 0.12, `minHours` 2, the model's middle at 1.3 or 1.5, `trust` 0.4 or 1, a flat charge per order, `minMargin` 1.15, `holdHours` 1.5 or 3, `maxCars` 3, `chainBid`, and (#331, 40 seeds) a lost quote moving the win
  model down 1.25 to 3 times as far as a win moves it up (−€371 to −€1,605: more orders and more of Friday, at a lower
  price on all of them) and a new day starting with 2 or 4 times its doubt (−€208, −€145, within chance).
  `FAILED_APPROACHES.md` has the table.
- **`spread` is the open question.** It cuts the fees of short-lead cars, which the old schedule opened at up to
  1.55 × typical, but 2.5 points more orders are late, and the simulator is weakest exactly there.

### Server check of the new defaults

Five fresh random seeds on the server, every variant on the same seeds (level 8, mean margin a week):

| Variant                | Margin  | Orders | On time by week (%)          | Ranked | Against the old defaults       |
| ---------------------- | ------- | ------ | ---------------------------- | ------ | ------------------------------ |
| Old defaults           | €10,951 | 229    | 97.3, 98.7, 99.0, 96.6, 96.0 | 5 of 5 |                                |
| New defaults           | €12,774 | 290    | 98.0, 95.7, 97.9, 93.7, 95.4 | 5 of 5 | +€1,823 ± 865, ahead on 4 of 5 |
| New defaults, `spread` | €13,165 | 306    | 96.8, 93.2, 91.8, 91.8, 92.9 | 5 of 5 | +€2,214 ± 440, ahead on 5 of 5 |

The server agrees with the simulator on the direction and about two thirds of the size. On the server 110 to 200
cars a week ride in chains at 0.68 to 0.76 × typical, against 12 to 34 before. `spread` earns €391 more than the
new defaults, but two of its five weeks end at 91.8% on time, 1.8 points over the minimum, so it stayed off until the fixes below.

### Why orders were late, and the second server check

The ten server weeks above had 158 late orders. With the first `spread`, 53 of its 103 found their first driver only
after the deadline warning: a last pickup before 16:00 was 20% of the orders and 52% of the late ones, because their
raises came on the morning of the pickup, when drivers have planned their day, and after a 2-hour hold in the
evening. 14 were cars of chains whose driver finished the next day: chains of 8 to 12 hours of driving.

The fixes: raises timed by the drivers' planning (`planBy` in `fees.ts`: by 21:00 the evening before for a last
pickup before 16:00), no hold and no open chain in the last planning hours, chains of 8 hours of driving at most
with 20% over the road minutes and 30 minutes of slack at each later pickup, and a chain's first pickup window ends
at its last start. Same five seeds:

| Variant                          | Margin  | Orders | On time by week (%)          | Ranked |
| -------------------------------- | ------- | ------ | ---------------------------- | ------ |
| Old defaults                     | €10,951 | 229    | 96.6, 96.0, 99.0, 97.3, 98.7 | 5 of 5 |
| First `spread`                   | €13,165 | 306    | 91.8, 92.9, 96.8, 93.2, 91.8 | 5 of 5 |
| Fixes, `spread` off              | €13,377 | 293    | 95.1, 96.3, 97.5, 97.4, 96.6 | 5 of 5 |
| Fixes, `spread` on (**default**) | €14,065 | 317    | 93.5, 95.0, 98.3, 96.6, 96.7 | 5 of 5 |

`offers` (direct offers at the app's fee to drivers who viewed a gig and live near it, `offers.ts`) is built and
off: in the simulator 0.2% of 2,000 to 3,500 offers a week are accepted and the margin does not move. The server
has not played it.

### Offers, the early fee and special orders

Same five server seeds as above, against the default of that section (€14,065):

| Variant                               | Server                                             | Simulator (40 seeds)       |
| ------------------------------------- | -------------------------------------------------- | -------------------------- |
| `offers` 1 / 0.9                      | +€826 ± 512 / +€611 ± 476, 1 to 28 accepted a week | +€19 ± 132 / −€75 ± 124    |
| `early` 0.8 (**default**)             | +€686 ± 600, ahead on 4 of 5                       | +€403 ± 114, ahead on 29   |
| `early` 0.7                           | −€56 ± 1,024                                       | +€361 ± 141 (at 0.74)      |
| Special orders at their measured cost | not played                                         | −€495 ± 125, 1 point later |

- **Offers do nothing.** Under 1% of 1,200 to 3,000 offers a week are accepted, on the server as in the simulator;
  the server's gain hangs on one seed each time. They cost 2,500 requests a week, so `offers` stays 0.
- **`early`**: a gig for a later day shows 0.8 × typical for its first hour. Two thirds of such gigs booked at the
  opening fee of 0.88, half of them within 30 minutes.
- **Special orders**: 257 saved weeks paid 0.40 × typical more for a private pickup, 0.12 for a private delivery
  and 0.34 for a premium car than for a plain one. Pricing at those wins orders that then run late. The surcharges
  stay; `privatePickup` and `privateDelivery` are now two params.

### The order model of #305

PR #308 fitted three models on the saved weeks, on the old `lean`. On its own server weeks (`ab-1` to `ab-8`) the
dealer prior changed nothing, the fee-need models lost €1,100 to €1,400 a week, and the order model in the quote
won €1,984 a week. `outlook.ts` and `order.json` are that order model: for each request its cost as a share of the
mean order's (from the drive, the lead time, the day, the address, the drivers who live at each end, our load) and
its chance to be late, priced at the list price × that chance.

On top of the current defaults, ten server seeds (the five above and five fresh ones):

| Variant                    | Margin  | Orders | On time, mean and lowest week | Ranked   |
| -------------------------- | ------- | ------ | ----------------------------- | -------- |
| Defaults without the model | €14,566 | 325    | 95.5%, 92.3%                  | 10 of 10 |
| `order` (**default**)      | €15,337 | 365    | 97.6%, 94.6%                  | 10 of 10 |

+€771 ± 385 a week, ahead on 6 of 10 seeds, 40 more orders, and more orders on time in every one of the ten weeks.
The simulator had it €388 ± 176 behind with the same gain in orders and on-time share: it counts a late order too
cheaply.

## Clean-up and the fixes of the open problems (14 November, night, #320)

From 28 server weeks of the defaults above (372 orders a week, 11,108 orders):

| Change                                                                                                | What the weeks showed                                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The cost in `order.json` is fitted again (`uv run --with numpy python -m analysis.lean_cost --write`) | The model predicted 1.03 × typical for a private pickup that paid 1.35, and 0.98 for a Friday that paid 1.06. It charged +0.37 for a last pickup within 8 hours; the fees say +0.09. Cars ready today were right already (0.99 against 1.00) |
| Only chains that book are posted, and a car waits only for such a chain                               | Chains posted on a Friday, with under 20 hours to the first last pickup or without a new car booked 23% of the time (11 a week); the others 69% (76 a week)                                                                                  |
| `chainPatience` 1                                                                                     | 51% of the chains book within one waking hour. One still open then books 24% of the time, and its cars waited a median 16 hours and then paid 1.06 × typical                                                                                 |
| `lateOpen` 1.25                                                                                       | 8 cars a week opened at 1.5 to 2 × typical because the time of their raises was over; 5 of them were booked within 3 minutes at 1.98 ×                                                                                                       |
| The early fee compares a fee with a fee (#327)                                                        | A gig posted again after its window ended could open under the fee it had reached                                                                                                                                                            |

Not changed, because the weeks gave no reason: the price rule (where a quote was higher only for its cost, the
wins fell as a noise of 0.28 says), and the opening fee (40% of the single gigs for a later day book at the early fee
within minutes, 31% at 0.88).

Removed as dead or lost: `target`, `capacity`, `gain`, `flatShare`, `flatEuros`, `feeBrake`, `lateSoft`, `openGigs`
(all part of the capacity charge, which was 0), `offers` and `offers.ts`, `maxShare`, `chainBid`, `pairCharge`,
`chainRaise`, `chainTop`, and the switches `supply`, `order` and `chainPick`, which are now how `lean` works.

On the simulator (40 seeds) the whole set is even with the defaults before it: −€57 ± 158 with 377 orders against
403. The cost fit alone is +€328, `lateOpen` +€114, and the chain rules −€385; the simulator books 85 to 90% of the
chains where the server books 63%, so it cannot judge those. The server check follows below.

### Server check

Five fresh seeds, each version on the same seeds (level 8, a week):

| Version                                                                 | Margin  | Orders | Late orders | Lowest week on time | Ranked |
| ----------------------------------------------------------------------- | ------- | ------ | ----------- | ------------------- | ------ |
| main                                                                    | €12,546 | 338    | 10.6        | 93.2%               | 5 of 5 |
| The changes, with the cost level 8% up (a side effect of the first fit) | €12,605 | 310    | 6.6         | 95.8%               | 5 of 5 |
| The changes, with the cost level as before                              | €12,901 | 351    | 10.2        | 95.7%               | 5 of 5 |

+€355 ± 335 a week against main, ahead on 3 of 5 seeds: inside what chance gives. Gigs whose raises are over book at
1.32 × typical against 1.78, the cars of failed chains are late 1.7% of the time against 3.9%, and Fridays cost
1.02 × typical against 1.06. Fees a car (0.93 × typical) and the chains' booking share (about 60%) did not move.
Private pickups fell from 16 to 6 orders a week.

## Straightening (14 November, night, #335)

Three reviews of the code found state that a restart lost, rules written several times with different numbers, a
cost level set in four places, and most constants where `pnpm bench` and `pnpm tune` could not reach them. What
changed, with no tuned value changed on purpose:

| Checkpoint | Change                                                                                                                                                                                                                                                                 | Check on the simulator (40 seeds)                                                                                                                                    |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0          | Baseline                                                                                                                                                                                                                                                               | €18,614, 402 orders, 97.3% on time; slowest tick 3.2 seconds (over the 3-second budget); 65 chains withdrawn within 30 minutes of their post                         |
| 1          | The planner's state, the drops, the floors and the supply's inputs come from the events and the journal                                                                                                                                                                | +€74 ± 121 against 0. A week restarted twice ends within a few hundred euros of the same week uninterrupted, with the same chain counts                              |
| 2          | One rule for when a chain may be open; chains that would be refused no longer block others; a path is judged from its first start that works; the search is ordered and bounded                                                                                        | Slowest tick 0.2 seconds; 3 chains withdrawn within 30 minutes. The margin (−€800 ± 127) does not count: the simulator books 82 to 93% of the chains, the server 60% |
| 3 to 5     | One cost level (`costLevel`); the supply learns what the order model leaves; one test for "today"; `minMargin`, `overhead`, `spread` and `chainHours` removed; one planning-timed fee schedule and one urgent climb, in waking minutes; constants named or made params | +€183 ± 165 against 2, 387 orders against 395; no fault, no schedule that is empty, falls or starts in the past; every new param accepted by `pnpm bench`            |

`SPREAD_RESTART_AT=<minute>,<minute>` makes a practice week restart itself at those world minutes, and each week now
prints its slowest strategy calls.

The chain rules on the server, one seed (`rnd-16a57974`) played by checkpoint 1 and checkpoint 2 at the same time:
€13,559 against €14,310 (+€751), 403 and 405 orders, 12 and 7 late orders, 55 of 85 and 60 of 91 chains booked. One
week is a direction, not a measurement: it does not confirm the simulator's −€800.

Left as they are, and worth their own measurement: the dealer middle of 1.40 (the recorded seeds say 1.25 at zero
trust), the raises' sizes and times, a lost request that teaches the shared effects once per option, and the
premium factor of 3.

## Supply and demand (15 November)

Until now `noise` 0.28 did two jobs. It was the scale of the win curve, and, because the best price keeps at least
`noise` of itself over the cost, the only limit on volume: no price under 1.39 × cost. The dealers' own scale is
0.12, so the model read every lost quote as a far lower middle than the real one and then added a large markup.

The split: `noise` is the dealers' scale, and a charge on the cost says what an order costs the others. The fit is
`uv run python -m analysis.supply_curve`, on 60 server weeks of ten fresh seeds (`supply-1` to `supply-10`, level 8)
that differ only in a fixed `tax`, with one level per seed. The load is the orders won per driver (0.36 to 0.75):

| Function                | Fit                                 | R²   |
| ----------------------- | ----------------------------------- | ---- |
| Fee paid × typical      | +0.355 ± 0.038 per order per driver | 0.64 |
| Refunds per order       | +€6.51 ± 0.98 per order per driver  | 0.47 |
| Late share              | +0.143 ± 0.016 per order per driver | 0.62 |
| Demand's logistic scale | 0.122 ± 0.006                       | 0.90 |

One more order raises the load by 1 ÷ drivers for every order of the week, so it costs the others
load × (typical × 0.355 + €6.51) = €28.7 × load, or 0.47 × load of the mean order's cost (€61.7). The trust that a
late order loses with its dealer is not in it.

The same ten seeds, every week ranked (mean margin a week, against the defaults before, `noise` 0.28):

| Variant (`noise` 0.11 but the first) | Margin  | Orders | On time | Against `noise` 0.28   |
| ------------------------------------ | ------- | ------ | ------- | ---------------------- |
| `noise` 0.28, no charge              | €15,903 | 362    | 97.3%   |                        |
| `tax` 0.04                           | €15,425 | 523    | 95.1%   | −€478 ± 579, 3 of 10   |
| `tax` 0.12                           | €15,607 | 487    | 95.1%   | −€296 ± 474, 4 of 10   |
| `tax` 0.24                           | €16,626 | 437    | 97.0%   | +€724 ± 330, 8 of 10   |
| `tax` 0.28                           | €16,416 | 420    | 97.0%   | +€513 ± 504, 6 of 10   |
| `tax` 0.32                           | €16,632 | 406    | 97.3%   | +€729 ± 316, 7 of 10   |
| `tax` 0.40                           | €15,907 | 367    | 97.6%   | +€4 ± 250, 5 of 10     |
| `taxEuros` 8                         | €15,653 | 465    | 95.1%   | −€249 ± 489, 5 of 10   |
| `taxEuros` 16                        | €16,051 | 378    | 96.1%   | +€148 ± 630, 6 of 10   |
| `taxLoad` 0.47 (**default**)         | €16,875 | 436    | 96.6%   | +€972 ± 386, 7 of 10   |
| `taxLoad` 0.56                       | €16,946 | 421    | 97.1%   | +€1,043 ± 344, 7 of 10 |

- **The split is the gain.** With the real scale and the same lowest price (`tax` 0.24), `lean` wins 75 more orders
  at the same on-time share.
- **A fixed charge peaks at 0.24 to 0.32**, where the fitted one is at these loads (0.21 to 0.28).
- **The charge by load is €248 ± 322 ahead of `tax` 0.24**, on 7 of 10 seeds: within chance, and the default because
  it is the fitted function and not a number read off these seeds. 0.56 is level with it.
- **A flat charge in euros is worse than a share of the cost**: it turns away the short orders.
- An earlier check on four seeds, on the code before #335 (`noisechk-1` to `noisechk-4`): `noise` 0.20 without a
  charge made +€264 and 0.14 −€554 with one week unranked.

## What chains earn (15 November, #349)

`chains=false` on `supply-1` to `supply-10`, against the saved weeks of the defaults on the same seeds (level 8, mean
margin a week, every week ranked):

| Variant        | Margin  | Orders | On time | Fees × typical |
| -------------- | ------- | ------ | ------- | -------------- |
| Defaults       | €16,875 | 436    | 96.6%   | 0.96           |
| `chains=false` | €15,314 | 395    | 97.3%   | 1.00           |

Chains make €1,560 ± 495 a week, ahead on 8 of 10 seeds, with 41 more orders and 0.7 points fewer on time.

What the 15 saved weeks of the defaults (these ten and five ranking runs) say of the chains:

- **Half of them book.** 94 chains a week are posted and 53% book. 123 cars a week ride in booked chains at 0.68 ×
  typical; 133 a week were in a chain that failed or was dropped and then paid 1.04 to 1.10 × as single gigs. All of
  those at 0.68 would be €2,500 a week: the most that better chains can earn.
- **A failed chain costs time, not fees.** Its cars pay 1.04 × typical where cars that were never in a chain pay 1.03.
- **The fee does not decide it.** A chain that did not book was seen by a median 14 drivers. Booked and unbooked
  chains opened at the same 0.67 × their cars' typical fees, and in the 89 older weeks where chains stayed open
  through their raises, a view at 0.75 to 1.00 × booked 1% of the time against 3% at 0.60 to 0.75.
- **The shape decides it.** A chain that 200 or more drivers can do as a round from home (home to the first pickup
  and the last delivery to home in 90 road minutes together) books 80% of the time; 74% of the chains have no such
  driver and book 48%. A trip from the last delivery to the first pickup of over 3 hours books 36%, one of 31 to 60
  minutes 77%.
- **A chain books at once or not at all.** Half of the bookings come within 4 minutes and 90% within 37.

### Three tries to book more chains (#351)

Each played on the same ten seeds, against the saved weeks of the defaults (mean margin a week, all weeks ranked):

| Variant                                            | Margin  | Against the defaults | Orders | Chains posted, booked | Cars in booked chains |
| -------------------------------------------------- | ------- | -------------------- | ------ | --------------------- | --------------------- |
| Defaults                                           | €16,875 |                      | 440    | 94, 52%               | 120                   |
| `chainFit` 1                                       | €16,971 | +€96 ± 343, 6 of 10  | 446    | 96, 56%               | 130                   |
| `chainTries` 2                                     | €16,644 | −€230 ± 282, 3 of 10 | 443    | 132, 44%              | 142                   |
| `chainPatience` 0.67                               | €16,578 | −€297 ± 155, 2 of 10 | 440    | 94, 53%               | 123                   |
| `chainFit` 1, `chainTries` 2, `chainPatience` 0.67 | €17,028 | +€153 ± 351, 7 of 10 | 452    | 134, 47%              | 149                   |

- **None is a measured gain** without the chain model below (`chainFit` 0, `chainPatience` 1); with it,
  `chainTries` 3 is the default.
- **`chainFit`** ranks two chains that want the same car by saving × chance to book (`bookChance` in `chains.ts`,
  from the drivers who can do the chain as a round from home). 4 points more chains book and 10 more cars ride in
  them.
- **`chainTries`** lets a car of a failed chain join one more chain. 22 more cars ride in chains, but the second
  chains book less often, and the fees over all orders do not fall (0.963 × typical against 0.960).
- **The three together** put 29 more cars in chains (149 against 120) with 11 more orders; that should be worth
  about €500 and measures as +€153 ± 351. It needs more seeds to say.

### The chain model: a fee for each chain by its chance to book (#351)

**The fee decides whether a chain books.** Ten server weeks drew each chain's fee level by its cars' orders
(`chainSpread` 1, 898 chains): at 0.78 × the chain's fee 12% booked, at 0.88 × 31%, at 1 × 46% and at 1.12 × 66%.
With chains off, the cars that could ride in one pay 0.94 × typical as single gigs when won on the Monday and
0.99 × from Tuesday to Thursday (ten server weeks), so a chain at 0.75 × that books is worth more than one at
0.68 × that does not. Today's level is right on the Monday (73% book) and too low after it (38%).

**Which chains book is known ahead.** `uv run --no-project --python 3.13 --with scikit-learn python -m
analysis.chain_model` fits the chance that a chain books within an hour on every chain that the saved weeks posted
(26,151 chains of 295 weeks). On seeds it did not see, the fifth of the chains it rates lowest books 12% of the
time and the fifth it rates highest 88%. What counts most: the fee for each hour of driving, long chains late in
the week (the bookings so far per driver × the hours), the trip from the last delivery to the first pickup, the
drivers who live near the last delivery or can do the chain as a round from home, cars that no driver has seen,
and the Monday. The weights are in `chain.json`; `score` in `chains.ts` computes the same features.

**What `chainModel` does.** Each path gets the fee level from 0.85 to 1.3 that earns the most: its chance to book
at that level × (what its cars pay alone − the chain's fee) − (1 − the chance) × what a failed chain costs them
(0.05 × typical). The best chain earns the most a car, and a path that earns nothing is not posted.
`chainTries` 3 lets the cars of a chain that no driver took join two more chains.

On the server, against the defaults with the weekend rule (mean margin a week, every week ranked):

| Variant                                         | `supply-1` to `-10` | `supply-11` to `-20` | Both    |
| ----------------------------------------------- | ------------------- | -------------------- | ------- |
| Every chain at 1.12 × (`chainOpen`)             | +€307 ± 278         |                      |         |
| `chainModel`                                    | +€581 ± 400         |                      |         |
| `chainModel`, `chainTries` 2                    | +€914 ± 429         | +€1,242 ± 366        | +€1,078 |
| `chainModel`, `chainTries` 3 (**the defaults**) | +€872 ± 463         | +€1,379 ± 355        | +€1,126 |
| … and `chainAlone` 1.06                         | +€1,263 ± 450       | +€986 ± 414          | +€1,125 |
| … and `pickLead` 12, `holdHours` 3              | +€982 ± 307         | +€1,479 ± 304        | +€1,231 |

With the defaults 71% of the chains book where 53% did, 197 cars a week ride in them where 117 did, at 0.71 ×
typical where they paid 0.68 ×, and the week wins 27 more orders at the same on-time share (96.1% against 96.2%).

Each setting was then pushed one step past where it paid, on `supply-1` to `supply-10` over `chainModel` with
`chainTries` 3 (+€872): `chainAlone` 1.06 +€1,263, 1.12 +€665, 1.18 +€621; `holdHours` 3 +€1,055, 4 +€577;
`pickLead` 12 +€1,057, 6 +€985; `chainPatience` 1.5 +€943; `chainTries` 5 +€679; `minSaving` 0.05 +€780. On 20
seeds the settings of the last two rows are level with the defaults, so the defaults change the fewest params.

**Direct offers of an open chain do not pay** (`chainOfferSpread` 1, ten server weeks, 2,436 offers to drivers who
viewed a chain and did not book it). Drivers who read the offer took it 2.7% of the time at the app's fee, 8.4% at
1.15 × and 16.2% at 1.3 ×, so an offer over the app's fee does find drivers. But the chains they booked paid 0.79,
0.85 and 0.97 × their cars' typical fees, where the cars alone pay 0.99 ×, and the week made €372 less than
without offers. `chainOffers` stays 0.

### Premium cars at a lower cost factor (#351)

`premium` multiplies a premium car's cost by 3, so `lean` wins none of the 49 premium requests a week. Lower
factors on `supply-1` to `supply-10`, over the chain defaults above (mean a week, every week ranked):

| `premium` | Margin against 3 | Premium orders | Their fee × typical | Late  | Their margin |
| --------- | ---------------- | -------------- | ------------------- | ----- | ------------ |
| 2         | −€184 ± 270      | 0.4            | 0.89                | 0%    | €29 a week   |
| 1.5       | −€132 ± 451      | 3.4            | 1.03                | 5.9%  | €204 a week  |
| 1         | −€364 ± 433      | 15.2           | 1.09                | 13.2% | €496 a week  |

The premium orders earn €33 to €60 each, but the week does not earn more with them: at 1 they are late four times
as often as the other orders, and the week wins only 5 orders more in all. `premium` stays 3.

## No raises over the weekend (15 November, #347)

Cars due on the last Monday were booked at 0.84 to 0.91 × typical on the Friday and the Saturday (46 a week), 2 a
week on the Sunday, and 31 a week on the Monday at 1.54 ×: the raises had come on Saturday and Sunday, and Monday's
first drivers took what the app showed between 06:00 and 09:00. With `rest` such a gig raises on the Monday.

Server check, the ten `supply-*` seeds, both schedules on the same seeds (level 8, a week). Both win the same
orders, so the difference is fees and refunds alone:

| Variant                   | Margin  | Orders | On time, mean and lowest week | Ranked   |
| ------------------------- | ------- | ------ | ----------------------------- | -------- |
| `rest` false (before)     | €16,861 | 436    | 96.7%, 94.7%                  | 10 of 10 |
| `rest` true (**default**) | €17,485 | 436    | 96.4%, 94.3%                  | 10 of 10 |

+€624 ± 130 a week, ahead on 10 of 10 seeds (+€172 to +€1,375), with 0.3 points fewer orders on time. The `rest`
false week of `supply-1` is the saved week of the old schedule to the cent.

## Shared demand outcomes (14 November, experimental)

`sharedOutcome` changes only losses with several quoted options. The old code updates the world, day, dealer, pickup
and delivery effects once per option, so one lost request can count several times. With `sharedOutcome=true`, every
option's contribution is calculated from the same pre-outcome state. Each delivery-option effect still learns alone;
each shared effect receives the mean of the option contributions once. Wins and the `false` control are unchanged.
The default was false until the check on today's defaults at the end of this section.

The first 40 paired simulator seeds (`lean-so-screen-1..40`) were used to explore the change. Shared learning alone
gained €426.35 (SE €156.81, paired 95% CI +€109.17 to +€743.53). Adding `costLevel=1` gained €485.18 over the control
(SE €182.15, CI +€116.74 to +€853.62); its increment over shared learning alone was only €58.83 ± €140.35. These are
selection results, not independent proof. The combined candidate was then frozen, including its SHA-256 hashes, before
40 new seeds (`lean-so-validate-1..40`) were played. The hashes were unchanged afterward.

| Frozen validation, 40 fresh paired simulator seeds | Control    | Candidate  |
| -------------------------------------------------- | ---------- | ---------- |
| Mean margin                                        | €17,694.01 | €18,243.68 |
| Mean orders                                        | 449.0      | 420.2      |
| Mean on time                                       | 96.36%     | 96.53%     |
| Ranked                                             | 40 of 40   | 40 of 40   |

The paired candidate-minus-control gain was **€549.67 a week**, SD €776.66, SE €122.80, t(39) 4.476 and 95% CI
**+€301.29 to +€798.06**. It was ahead on 28 of 40 seeds, with a median gain of €588.67; a 10% winsorized mean was
€517.26, so the result is not just one large seed. No candidate week became unranked. This is simulator evidence only;
its CI does not establish that the true gain exceeds €500.

Every benchmark used a new `SPREAD_JOURNAL_DIR`; reusing one contaminates a restarted simulator because its world ids
repeat and the harness journals append by world id. Two identical configurations in a fresh directory produced the
same score to the cent before these comparisons. The validation seeds map to 39 distinct recorded request/driver packs
(one pack occurs twice), with independent hidden draws and quote decisions per named seed. Raw bench output:
[`shared-outcome-screen.csv`](shared-outcome-screen.csv) and
[`shared-outcome-validation.csv`](shared-outcome-validation.csv).

### Server check on 15 fresh seeds (14 November, issue #357)

Three arms played 15 new random server seeds each, level 8, one paired run at a time. The 45 weeks used `f1804809`
with only the two TypeScript source changes; #347's weekend schedule and #351's chain model were merged into this
branch afterward. These are therefore measurements on the pre-#347, pre-#351 base, not a replay of the final merge,
and should be repeated on it before the parameter is enabled.

| 15 paired server seeds | Control (`sharedOutcome=false`) | Shared only | Shared, `costLevel=1` |
| ---------------------- | ------------------------------- | ----------- | --------------------- |
| Mean margin            | €13,010.05                      | €13,457.10  | €13,173.53            |
| Margin SD              | €3,404.08                       | €3,366.07   | €3,414.27             |
| Mean orders            | 390.2                           | 370.7       | 359.7                 |
| Mean on time           | 96.33%                          | 96.72%      | 96.50%                |
| Ranked                 | 14 of 15                        | 15 of 15    | 14 of 15              |

| Paired difference       | Mean ± SD              | SE      | 95% Student-t CI        | Ahead |
| ----------------------- | ---------------------- | ------- | ----------------------- | ----- |
| Shared − control        | **+€447.06 ± €825.33** | €213.10 | **−€10.00 to +€904.11** | 10/15 |
| `costLevel=1` − control | +€163.48 ± €706.46     | €182.41 | −€227.74 to +€554.71    | 10/15 |
| `costLevel=1` − shared  | −€283.57 ± €725.16     | €187.24 | −€685.15 to +€118.01    | 5/15  |

Shared learning alone has the same sign as the simulator result but is not conclusive on 15 pairs: t(14) 2.098, with a
median paired gain of €212.57 and per-seed differences from −€967.65 to +€2,227.75. None of its weeks became unranked;
the control was unranked once where shared learning was ranked (its on-time share was 93.26% against 88.68%). There is
no support here for also raising `costLevel` from 0.98 to 1. Do not change the defaults on this evidence alone. Raw
bench output is [`shared-outcome-server-15.csv`](shared-outcome-server-15.csv); every week is under
`data/scrape/runs/L8/so15-<seed>/<world id>`.

The exact server comparison can be repeated with a fresh journal directory and recording enabled:

```sh
journal=$(mktemp -d)
SPREAD_JOURNAL_DIR="$journal" \
  pnpm bench lean:sharedOutcome=false lean:sharedOutcome=true lean:sharedOutcome=true,costLevel=1 \
  --level 8 --jobs 3 --csv out/lean-so-15.csv \
  --seeds so15-7b0c78dd,so15-65faabd4,so15-9ca165e4,so15-0dc06b05,so15-126df8b9,so15-61ebfa24,so15-ecb8752d,so15-8c6518e8,so15-63f8e141,so15-3d85f5d0,so15-a13b2a16,so15-7554c2e4,so15-7a3a06f0,so15-59edee08,so15-1ccfc1c6
```

The frozen candidate can be replayed offline against its unchanged control:

```sh
journal=$(mktemp -d)
pnpm sim --port 8787  # in another terminal
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim SPREAD_RECORD=0 SPREAD_JOURNAL_DIR="$journal" \
  pnpm bench lean:sharedOutcome=false lean:sharedOutcome=true,costLevel=1 \
  --level 8 --seeds lean-so-validate-1..lean-so-validate-40 --jobs 12
```

### Shared outcomes on today's defaults (15 November, #360)

The server check above was on the code before the weekend rule and the chain model. On today's defaults,
`supply-1` to `supply-20` (level 8, mean a week, every week ranked):

| 20 paired server seeds | `sharedOutcome` false | true (**default**) |
| ---------------------- | --------------------- | ------------------ |
| Mean margin            | €17,189               | €17,494            |
| Mean orders            | 453                   | 431                |
| Price × list           | 1.450                 | 1.488              |
| Fee × typical          | 0.916                 | 0.918              |
| Late orders            | 4.8%                  | 4.4%               |
| Margin an order        | €39.1                 | €41.8              |
| Lowest week on time    | 92.5%                 | 91.2%              |

+€305 ± 203 a week, ahead on 13 of 20. With the 15 seeds above (+€447 ± 213) that is about +€366 ± 147 over 35
seeds, so `sharedOutcome` is now true. The gain is the price: 22 fewer orders at 2.6% more, won less on Monday
to Wednesday (40%, 47% and 41% of the requests against 44%, 51% and 44%) and as much after.

Two biases of the same kind on the cost side were checked on those 20 weeks and are too small to act on. The
supply learns from every booking, also one that the driver gives back: 30 gigs a week are booked twice, at 0.88 ×
typical and then at 1.09 ×, but over all bookings that is 0.955 × learned against 0.961 × paid. And a car that
cannot ride in a chain is priced by places whose bookings are half chains: the 16 a week with under 22 hours of
lead pay 1.17 × typical and earn €26 an order against €38, which is €200 a week at most.

## Five decision algorithms (tried and removed, 15 November, #354)

Five well-known decision algorithms were tried in place of `lean`'s fixed rules, each as a param. None was a
measured gain, so none is in the code: it is on the branch of the closed PR #355. The results stay here, so that
nobody plays them again.

**What the saved weeks said first** (157 `lean` weeks of 15 seeds, level 8, mean €16,269 at 96.5% on time):

- Volume is at a flat top: within a seed, 40 orders more or fewer cost €400 to €700 a week, and 80 about €900.
- Early orders cost the later ones more: each Monday order per driver raised the fee ratio of Tuesday and Wednesday
  by 1.28 and their late share by 0.44, where `taxLoad` assumes 0.355 all week.
- One week of 157 was under 90% on time and eight under 93%.
- 59% of the single gigs booked after a raise, and 20% at 1.31 to 2 × typical.
- The win share of Monday morning's quotes differs by 0.17 between weeks, and Tuesday's by 0.07.

**What was tried** (the names are the params they had):

- **`value`**: dynamic programming for the quote. The `taxLoad` charge gave way to `value` × the charge of a value
  table: what one more order takes from the rest of the week, read by the minute of the week, the orders won so far
  per driver and the late share so far. Crowding made an order dear on Monday (about €25 for a mean order) and
  cheap on Friday (€4 to €6); the 90% rule charged an order for what it adds to the risk of an unranked week. At 1
  its mean equalled the `taxLoad` charge.
- **`feeTable`**: dynamic programming for the fee. A single gig's opening fee and planned raises came from a
  program over (share of the planning time, fee shown) for six classes of gig, with a charge on a booking above the
  opening fee for teaching drivers to wait. The table opened at 0.8 to 1.15 × typical, held for two thirds of the
  planning time and then raised two to four times.
- **`pace`**: pacing. A controller held a plan from the 40 best saved weeks (0.52 orders per driver, in day shares
  of 23%, 25%, 19%, 20% and 13%), lowered the planned volume when bookings paid more than planned or over 4% of the
  orders were late, and moved the charge between 0.5 and 2 × the plan's as the wins ran ahead of the plan or behind
  it. 1 was its own gain.
- **`sample`**: Thompson sampling. Each quote was the best price for one draw of the win model's effects, × `sample`
  of each effect's standard deviation, seeded by the request id.
- **`rollout`**: lookahead in the offline simulator. Before Monday and on the evenings of Monday to Wednesday it
  played `lean` on the 8 recorded simulator weeks most like the live one with the charge × 1, 1.5 and 2.5, and kept
  the scale in force unless another earned €500 a week more, clearly and over 92% on time.

**Server, the same ten random seeds for all** (`dp-a22ce2`, `dp-0742db`, `dp-ab2341`, `dp-57e1da`, `dp-42b22f`,
`dp-1f571c`, `dp-b49cf6`, `dp-c384ef`, `dp-8038fe`, `dp-200005`; level 8; every week ranked; ± is one standard
error of the paired difference):

Before the chain model (#351), against the defaults of that time:

| Setting      | Margin a week | Against the defaults | Seeds ahead | Orders | On time | Lowest week |
| ------------ | ------------: | -------------------: | ----------: | -----: | ------: | ----------: |
| defaults     |       €16,449 |                      |             |    418 |   96.5% |       94.1% |
| `value=1`    |       €16,970 |          +€521 ± 343 |     8 of 10 |    425 |   95.3% |       91.1% |
| `pace=1`     |       €16,575 |          +€127 ± 293 |     6 of 10 |    416 |   96.7% |       94.3% |
| `value=1.5`  |       €16,367 |           −€82 ± 429 |     3 of 10 |    377 |   95.6% |       90.7% |
| `pace=2`     |       €16,246 |          −€202 ± 403 |     5 of 10 |    405 |   96.7% |       95.4% |
| `rollout=1`  |       €16,144 |          −€305 ± 403 |     2 of 10 |    385 |   97.1% |       95.2% |
| `sample=1`   |       €15,842 |          −€607 ± 271 |     2 of 10 |    438 |   96.2% |       94.3% |
| `sample=0.5` |       €15,740 |          −€708 ± 365 |     3 of 10 |    419 |   96.4% |       94.1% |

With the chain model, against the defaults of that hour (`sharedOutcome` was still false, #360):

| Setting         | Margin a week | Against the defaults | Seeds ahead | Orders | On time | Lowest week |
| --------------- | ------------: | -------------------: | ----------: | -----: | ------: | ----------: |
| defaults        |       €17,669 |                      |             |    447 |   96.6% |       94.4% |
| `value=1`       |       €17,919 |          +€251 ± 457 |     5 of 10 |    445 |   95.6% |       91.3% |
| `pace=1`        |       €17,718 |           +€50 ± 280 |     5 of 10 |    442 |   96.6% |       94.7% |
| `feeTable=true` |       €15,610 |        −€2,058 ± 292 |     0 of 10 |    430 |   95.7% |       91.8% |

- **The value table** was the only one ahead, and with the chain model its gain is inside the noise, while it costs
  a point of on-time share both times and its worst weeks come near 90%. It is fitted on weeks played before the
  chain model, and those weeks vary the volume in one direction only, so it cannot tell many orders on one day from
  many orders so far.
- **The fee table** loses on every seed: it opens higher and raises late, pays more a gig and wins fewer orders.
  The saved gigs all raise at the same shares of their planning time, so the fit could not tell a raise from the
  hour.
- **Pacing** changes nothing, and **sampling** loses: at 1 it wins 20 more orders at lower prices, at 0.5 the same
  orders for less.
- **The rollout** kept the charge in four weeks, which are then the defaults' weeks, and raised it in six, which
  lost 33 orders a week on average: the simulator favours fewer orders than the server does.

Every week of both rounds is in [`decision-algorithms-server.csv`](decision-algorithms-server.csv), and saved under
`data/scrape/runs/L8/dp-*`.

## The squeeze (15 November, #367)

The ranking round "Sunday 00:00" and the recorded leaderboard of the 01:00 test final showed where `lean` was behind:
the leaders win 445 to 488 orders a week where `lean` won 364 to 405, most of the difference on Thursday and Friday,
and `lean`'s next order cost €92 in fees where its mean order cost €59, because the extra cars rode alone. Nine
benches on the server measured what helps. Two things about the measuring:

- **The defaults were tuned on `supply-1` to `supply-10`, so that set flatters them**: on it, both directions of
  one lever lost (`taxLoad` 0.3 and 0.6, `lateCost` 0.5 and 1.5). From the third bench on, every variant plays on
  fresh seeds (`squeeze-1` to `-10`, `confirm-1` to `-10`, `third-1` to `-10`) beside the defaults in the same
  bench. ± is one standard error of the paired difference; every week below is ranked unless said.
- "The combination" is `taxFade=1,urgentTop=1.6,lateTop=1.3,chainDays=5`.

| Variant, against the defaults of 14 November                    | `squeeze`     | `confirm`   | `third`       | Orders | Lowest week on time |
| --------------------------------------------------------------- | ------------- | ----------- | ------------- | -----: | ------------------: |
| `urgentTop=1.6,lateTop=1.3`                                     | +€558 ± 129   | +€483 ± 149 |               |     +5 |               92.5% |
| … and `chainDays=5` (**the defaults now**)                      | +€671 ± 150   | +€492 ± 147 | +€488 ± 176   |     +5 |               91.8% |
| … and `taxFade=0.5`                                             | +€885 ± 226   | +€627 ± 128 |               |    +21 |               91.1% |
| The combination (`taxFade=1`)                                   | +€1,024 ± 189 | +€729 ± 185 | +€1,168 ± 211 |    +41 |               90.0% |
| The combination and `pairShare=0.5` (**`volume.json`**)         | +€1,210 ± 321 | +€916 ± 168 | +€1,353 ± 325 |    +84 |               90.1% |
| The combination and `pairShare=1`                               | +€458 ± 340   |             |               |    +94 |               92.8% |
| The combination, `pairShare=0.5` and the flu guard (`guard=8`)  | +€371 ± 311   | +€540 ± 225 | +€457 ± 412   |    +53 |               91.4% |
| The combination, `pairShare=0.5` and the rescue (`rescue=0.06`) |               | +€281 ± 453 | +€927 ± 326   |    +78 |               90.1% |

- **The new defaults** are the three that gain with almost no change in the orders on time: lower tops of the urgent
  and late climbs (`urgentTop` 1.6, `lateTop` 1.3: the gigs that reached the last raises paid 1.47 × typical and
  carried 19% of the single gigs' fees) and chains on Friday (`chainDays` 5; 6 plays the same weeks).
- **`volume.json`** held `taxFade` 1 and `pairShare` 0.5. They are the defaults since
  [the room for late orders](#the-room-for-late-orders-15-november-381), and the file is gone.
  Over the defaults it wins about 80 orders a week more and makes €430 to €860 a week more, on all three sets. On
  the ranking round "Sunday 03:00" it made €83,342 with 2,391 orders at 95.1% on time, 2nd of 37 teams
  (`data/rankings/2026-11-15-0315/`). **Its risk is the delivery minimum**: of its 30 fresh weeks one ended at 90.1%
  on time (480 orders and 48 late with the combination alone: one late order more and the week scores nothing), and
  five of 74 weeks of the two volume settings were under 92%, against none of the defaults' 30.
- **`taxFade`** takes the `taxLoad` charge off on Friday and half of it off on Thursday. It is a patch by weekday.
  The reason it pays: fitted again on the 290 weeks with the chain model, one more order per driver no longer
  raises the fees of the cars booked after it (slope −0.24, not above zero on any day), where `taxLoad` 0.47 was
  fitted on 0.355 × typical before the chain model. A lower charge all week (`taxLoad=0.3`) made +€290 ± 344 on
  `squeeze` with 30 more orders.
- **`pairShare`** lets the quote see our books: a request that the chain search can put in a chain with open cars
  we hold has that chain's saving (the chain model's `worth`), × `pairShare`, taken off its cost, and no less than
  0.4 × the cost. It fires on about 600 quoted options a week at €22 to €26 each. Alone it gains nothing (−€93 to
  +€183); on the combination 0.5 adds about €186 on each of the three sets. A stricter form (only what the chain
  adds over the chains its partners make without the new car, one request per open car, half for a car already in
  the app) made +€782, +€679 and +€710 at 0.5, 1 and 1.5 on `squeeze`, under the simple form, and is not in the code.

**What lost, and stays off or as it was** (ten seeds each; the first eleven rows on `supply-1` to `-10`, against the
saved weeks of the defaults there, so each is some €300 to €500 too low):

| Variant                                        | Against the defaults                       |          Orders |
| ---------------------------------------------- | ------------------------------------------ | --------------: |
| `longCost=0` (no long-drive cost)              | −€1,319 ± 364                              |             −11 |
| `longCost=0,lateCost=0.5`                      | −€1,910 ± 548                              |              −6 |
| `lateCost=0.5` / `1.5`                         | −€505 / −€382                              |        +4 / −10 |
| `longCost=1.5`                                 | −€380 ± 360                                |              −6 |
| `chainStart=0.85` / `0.75` with `chainRamp=30` | −€665 / −€778                              |         −2 / −6 |
| `value=1` / `0.5`, table fitted again          | −€1,029 / −€686                            |       −27 / +37 |
| `taxLoad=0.15` / `0.3` / `0.6`                 | −€975 / −€698 / −€264                      | +62 / +28 / −25 |
| `raise3=1.4`                                   | −€288 ± 204                                |              −1 |
| `urgentTop=1.8,lateTop=1.5`                    | −€69 ± 171                                 |              −1 |
| `urgentTop=1.4,lateTop=1.2`                    | +€388 ± 235 (and +€333 ± 176 on `squeeze`) |              +2 |
| On the combination, `squeeze`: `maxHop=90`     | +€546 against the combination's +€1,024    |             +39 |
| … `maxCars=5,maxDrive=10`                      | +€930                                      |             +39 |
| … `holdHours=3,pickLead=12`                    | +€1,067                                    |             +44 |
| … `taxLoad=0.35`                               | under the combination (4 seeds)            |                 |

- **Long lanes are not underpriced.** `lean` wins 9% of the requests with a typical fee of €150 or more, and the
  dealers' limit there is about 1.31 × list where `lean` quotes 2.04 ×. But without the long-drive cost the week won
  6.5 long orders more that earned nothing more as a group, and the other orders lost €1,100 a week (16 fewer, fees
  0.92 against 0.90 × typical, 4.0% late against 2.8%). In the test final no team of the top won them either: the
  win share of long lanes has no relation to a team's margin (correlation +0.01 over 36 ranked teams).
- **A chain's fee is right.** 97% of the chains book at their opening fee after 3 minutes at the median, but a
  lower opening with a climb to the fee lost.
- **Wider chains do nothing.** 108 cars a week may join a chain and never do; a longer hop, more cars or longer
  drives did not bring them in.

**The flu, and why no guard is on.** The rules give every level 8 week one day on which 30% of the drivers stay at
home, unannounced. It shows in the first hour of that day: the drivers give that day's gigs back, 10 at the median
against 3 on the week's next-worst day (41 weeks of the defaults). For the defaults the weekday of the flu does not
matter (96 to 97% on time); with the combination a flu on Thursday or Friday costs 1.2 to 1.4 points, and the late
cars are those due on the second Monday (102 a week with the defaults, 131 with the combination), whose refunds come
after the weekend. Three guards were built and none pays:

- `guard` as a count of gigs given back, not started or expired in 12 hours (14 or 10): +€359 and +€131 where the
  combination made +€729, and the 90.0% week ended at 90.7%.
- `guard` as the first hour of a day (8, the code now): costs €190 to €840 a week against the same settings without
  it, and lifts the lowest week by about one point.
- `rescue` (when late orders and warned cars without a driver are that share of the orders won, warned cars climb to
  3 × typical): 0.06 made +€281 ± 453 on `confirm` and +€927 ± 326 on `third`, where the same settings without it
  made +€916 and +€1,353, and the lowest week stayed at 90.1%; 0.04 made −€277 and +€123, with one week at 89.1%,
  not ranked.

**The test final of 01:00.** Every team plays the same requests and each resolves at the same world minute, so a
team's order count in the recorded leaderboard (`data/finals/2026-11-15-0100-test/`) shows what it won among the
requests of each step; against our own week this agrees in 282 of 283 steps. `lean` came 6th of 41 with €12,875 and
364 orders, €1,236 behind the first. It sent its first quote at world minute 709 (the 50 requests before it got
none, some 22 orders and €650 to €700: the system was started after the hour, and `--final` waits by itself when it
is started before), and it won 101 orders on Thursday and Friday where the first three won 122 to 165.

## The room for late orders (15 November, #381)

A week under 90% on time scores nothing. The volume settings (`taxFade` 1, `pairShare` 0.5) end at 95.3% on average,
and one of their 47 saved weeks ended at 90.1% (`confirm-7`). The rule `room` keeps such a week ranked, and with it
the volume settings are the defaults.

**Where the week is lost.** The saved weeks of four settings on the fresh seeds (188 weeks) say:

- The last request comes on Friday before 18:20. From then on the number of orders is final, and so is the number of
  late orders that the week can take: a tenth of the orders.
- By Saturday 07:00 the worst week had used 85% of that number, and the median week 30%. No week was lost by then.
- `confirm-7` had room for 29 more late orders on Saturday, and 29 of its Monday orders came late. Nothing in the
  week before said so (0.7% of its orders were late by Thursday night). What said so on Saturday 07:00: 98 orders
  for Monday had no driver, where 30 is usual. Friday was the day when 30% of the drivers stay at home, and Friday is
  when Monday's gigs book.
- An order without a driver on Saturday 07:00 is late in 38% of the cases when its typical fee is €80 or more and
  its last pickup is before 15:00 on Monday, in 15% when only the fee is, in 19% when only the pickup is, and in 5%
  otherwise. With a driver on Saturday it is late in 1.7%.
- A long gig that books on Monday after 15:00 is always late (405 of 405): the deadline warning of such a car comes
  hours after its last pickup, at the minute the pickup place closes. So the urgent climb cannot save it.
- The drivers are there. In `confirm-7`, 283 drivers looked at the 107 open gigs on Saturday morning and 40 booked,
  at 0.88 × typical. On a Monday from 07:00 to 08:00 a view of a long gig books in 6% of the cases at 1.0 × typical,
  in 14% at 1.2 × and in 19% at 1.3 ×.

**The rule.** From Friday 21:00, `lean` adds up the late chances of its orders without a driver (the four numbers
above) and compares `room` (3.5) × that sum with the late orders the week can still take. The sum times 3.2 is the
most that any saved week had. While the room is too small, each single gig of an order with a chance of 15% or more
gets a new schedule from a higher fee: 1.1 × typical at least, then 0.1 × more at each rise, up to 2.5 ×. A rise
comes every 60 minutes on Saturday and every 30 minutes on Monday, between 05:00 and 21:00, and not on Sunday, when
nobody books (12 bookings in 62,000 views). The rises stop when enough orders have a driver. Chains keep their own
schedule. The week's summary line says how many rises there were.

In 174 of the 188 saved weeks the sum never reaches the room, and the rule does nothing.

**The result** on ten saved seeds of the volume settings (one server week each, 15 November):

| Seeds                                            | The rule    | Late on Monday, before → after | Margin against the saved week           |
| ------------------------------------------------ | ----------- | ------------------------------ | --------------------------------------- |
| `confirm-1`, `confirm-3`, `confirm-4`, `third-1` | did not act | the same                       | the same to the cent                    |
| `third-5`                                        | did not act | 2                              | −€740 (13 orders fewer by Friday)       |
| `confirm-7`                                      | 8 rises     | 29 → 20                        | −€687; 91.8% on time, was 90.1%         |
| `third-2`                                        | 2 rises     | 10 → 6                         | +€157                                   |
| `third-4`                                        | 13 rises    | 18 → 7                         | −€1,309 (12 more late orders by Friday) |
| `confirm-2`                                      | 1 rise      | 7 → 4                          | +€596                                   |
| `third-7`                                        | 3 rises     | 0 → 0                          | −€196                                   |

- A week on the server does not always replay the same: four of the ten weeks had a different number of orders by
  Friday, before the rule can act. `third-5` shows how much that moves a week without the rule.
- `third-4` is the week the rule is for. This time it had 36 late orders by Friday night (24 in the saved week) and
  room for 51. With the 18 late orders of its saved Monday it would have ended under 90%. With the rule 7 were late,
  and the week ended at 91.7%.
- In `confirm-7` the rule paid €1,353 more in fees and saved 9 late orders, which leaves room for 9 more.

**What the rule does not cover:** a week that uses its room before Friday night. The closest saved week used 85%
of it. `lateHard` works against that during the week.

## Params

`open` 0.88, `raiseAt1` 0.3, `raise1` 1.05, `raiseAt2` 0.55, `raise2` 1.25, `raiseAt3` 0.8, `raise3` 1.55, `jitter` 1,
`early` 0.8, `rest` true, `lateWithin` 60, `lateOpen` 1.25, `urgentOpen` 1.15, `urgentStep` 0.125, `urgentEvery` 15, `urgentTop` 1.6,
`lateFrom` 1.1, `lateStep` 0.05, `lateEvery` 30, `lateTop` 1.3, `feeRatio` 0.84, `lateCost` 1, `premium` 3,
`privatePickup` 0.25, `privateDelivery` 0.25 (both below level 7 only), `costLevel` 0.98, `minHours` 4, `noise` 0.11,
`sharedOutcome` true, `tax` 0, `taxEuros` 0, `taxLoad` 0.47, `middle` 1.4, `trust` 0.7, `lateHard` 0.05, `chains` true, `maxHop` 60, `maxCars` 4, `minSaving` 0.15, `maxDrive` 8,
`pickLead` 20, `chainLast` 3, `holdHours` 2, `chainPatience` 1, `chainTries` 3, `chainFit` 0,
`chainModel` true, `chainAlone` 1, `chainOpen` 1, `chainSpread` 0, `chainOffers` 0, `chainOfferSpread` 0,
`chainDays` 5, `taxFade` 1, `pairShare` 0.5, `room` 3.5, and the switches of
[the squeeze](#the-squeeze-15-november-367) that are off: `longCost` 1, `chainStart` 1, `chainRamp` 20, `value` 0,
`guard` 0, `rescue` 0.
