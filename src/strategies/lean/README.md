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
  to `urgentTop` (2) when the time is over. With `jitter` 1, each raise moves by up to 20 minutes and 5%, drawn from
  the order id, so a driver cannot plan a second look for the rise.
- A gig posted with under an hour of planning time left (`lateWithin`) opens at `lateOpen` (1.25) and climbs as an
  urgent one.
- The urgent climb, from the deadline warning on or with under 45 minutes left to book: from `urgentOpen` (1.15),
  `urgentStep` (0.125) every `urgentEvery` (15) waking minutes to `urgentTop`. A car that is late already climbs
  from `lateFrom` (1.1) by `lateStep` (0.05) every `lateEvery` (30) minutes to `lateTop` (1.7). A gig that a driver
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

## Params

`open` 0.88, `raiseAt1` 0.3, `raise1` 1.05, `raiseAt2` 0.55, `raise2` 1.25, `raiseAt3` 0.8, `raise3` 1.55, `jitter` 1,
`early` 0.8, `rest` true, `lateWithin` 60, `lateOpen` 1.25, `urgentOpen` 1.15, `urgentStep` 0.125, `urgentEvery` 15, `urgentTop` 2,
`lateFrom` 1.1, `lateStep` 0.05, `lateEvery` 30, `lateTop` 1.7, `feeRatio` 0.84, `lateCost` 1, `premium` 3,
`privatePickup` 0.25, `privateDelivery` 0.25 (both below level 7 only), `costLevel` 0.98, `minHours` 4, `noise` 0.11,
`tax` 0, `taxEuros` 0, `taxLoad` 0.47, `middle` 1.4, `trust` 0.7, `lateHard` 0.05, `chains` true, `maxHop` 60, `maxCars` 4, `minSaving` 0.15, `maxDrive` 8,
`pickLead` 20, `chainLast` 3, `holdHours` 2, `chainPatience` 1.
