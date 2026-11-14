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
  has little time to find its driver, for a private address, a trade-in, a weekend, a note that narrows the work, and
  × 1.5 for a premium car.
- **What capacity is worth.** Drivers can move about a third of what dealers ask for, and the facts say that winning
  more loses money. So each order also costs `capacity` × its typical fee, the worth of its place in the week. That
  worth rises with each win and falls with each loss, so that we win `target` of the requests (0.30 × the world's
  drivers over 777). The target falls when bookings cost more than planned, when more than 40 gigs wait without a
  driver, and when orders arrive late. Requests that arrive together from one yard, as a bulk order, count more.
- **The quote** is, for each option, the price with the highest chance × (price − cost − worth of capacity). With
  the worth of capacity high, this prices the requests where the competitor is dear high and still wins them, and
  loses the others: we win the dearest third, not the first third.

## 2. The fee (`fees.ts`)

The lowest fee that books a gig within three hours is 0.76 × typical at the median and 0.59 to 1.02 for four gigs in
five, and lane, hour and town explain little of it. So a gig opens low and climbs through that range while drivers
are awake (07:00 to 21:00). With `time` waking minutes until 90 minutes before the last pickup:

- it opens at 0.68 × typical and climbs to 1.04 over half of the time, six hours at most (a gig with less than twelve
  hours opens higher);
- it creeps to 1.30 when four fifths of the time are gone, and climbs to 2 × by the end, so the one gig in ten that
  needs more finds its driver before the last pickup, not at it;
- a car ready two or more days later holds its opening fee until the morning before;
- from the deadline warning on, or with under 45 minutes left, the fee climbs 12% every 15 minutes to 2 ×; a car that
  is late already climbs to 1.7 ×;
- a gig that a driver gives back starts again from the fee that booked it.

## 3. The service (`src/ops`)

Only options that `canServe` says can arrive on time with five hours to spare are quoted (ten once 5% of the orders
are late), and only with `minHours` waking hours left to book a driver. The note decides the windows, plates and licence of every gig, and a failed visit or an expired gig posts
the car again with what it taught.

## Params

`target` 0.3, `capacity` 0.4 (its start), `gain` 0.02, `feeRatio` 0.84, `overhead` 0.06, `minHours` 4, `minMargin` 1.05, `trust`
0.7, `lateSoft` 0.04, `lateHard` 0.05, `openGigs` 40, `urgentTop` 2, `lateTop` 1.7. Override one with
`--set key=value`. The end of a week prints the share won, the mean price × list, the mean fee × typical and the
late orders.
