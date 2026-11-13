# Adaptive quoting

`PricingModel` decides the price of a quote that we want to send. It learns, from our own wins and losses during the
week, the multiplier on the list price that wins about half of our quotes. It has no network access: `price(request,
now)` returns a price for each option, and `observe(event)` takes `order_won`, `order_lost` and `ledger` events.
`dispatch.py` calls it from `Desk.quote` and feeds it every event in `Desk.handle`.

## The model

- The price of each option is `list price × m`. `m` is `exp(world + pickup + delivery + dealer)`: one log multiplier
  for the world, and an offset for the pickup place, the delivery place and the dealer.
- Each outcome moves the world estimate by `0.03 × (won − 0.5)` and each offset by `0.015 × (won − 0.5)`. So the
  price rises after wins, falls after losses, and settles where half of the quotes win. Every step fades the older
  results, so the price follows the competitor when it moves, also for a dealer whose cars we win most of.
- An offset starts at 0 and only moves with data for its place or dealer, so it refines the world estimate where we
  have seen enough. Offsets stay within ±25%, and `m` within 0.9 to 2.0.
- The starting multiplier is about the middle of the level's range:

| Level | Start `m` | Why                                                      |
| ----- | --------- | -------------------------------------------------------- |
| 1–3   | 1.00      | Every quote wins the first option at its list price: fixed |
| 4–6   | 1.00      | The competitor is from 10% below to 10% above the list price |
| 7     | 1.25      | The competitor is 12% to 38% above the list price        |
| 8     | 1.35      | The competitor is 26% to 54% above the list price        |

## The price war (level 8)

The learner follows the competitor down within about ten losses, so a war never shows as a long run of losses. It
shows as a fall: the world multiplier drops 15% below its level at the day's first outcome, with losses on at least
six pickup places. Until 18:00 the multiplier keeps following the war (our price drops with the competitor's), and
place and dealer offsets stop learning. At 18:00 the multiplier returns to the day's opening level.
`Params(war_decline=True)` declines during the war instead. A war on Monday has no earlier level to fall from: it is
followed but not flagged. There is no war on the outage day, and one war a week.

## The outage (levels 6–8)

A region is a town and the places within 80 km of it, from the world map, and a request belongs to the region of its
pickup place. Fourteen wins in a region's last fifteen outcomes of a day, once the world has 100 outcomes, is the
outage there (one a week). What the region's wins taught today is undone, so they no longer lift prices everywhere
else. Until 18:00 its requests start at `1.2 × m` (dealers there pay about 30% more), and that boost learns from
their outcomes.

## Dealer trust (level 8)

A `ledger` revenue line with no late refund in the same minute is an order on time: that dealer's count rises by one,
up to 25. A late refund or an undelivered penalty halves the count, rounded down. The price for the dealer is
multiplied by `1 + count / 100`.

## Bench

Level 8, seeds `spread-1` to `spread-5`, margin in euros and the share of orders on time.

Level 8, margin in euros, orders won and the share on time. The list price row is the unchanged starter. The
versions are the stages of this branch; **the final version has not been benched yet**: the team's eight practice
slots were full.

| Version                                                      | `spread-1`              | `spread-2`             |
| ------------------------------------------------------------ | ----------------------- | ---------------------- |
| List price (starter)                                         | −72,612.51 · 949 · 45.5% | not run                |
| Learner, war flagged on a 9-of-10 loss run (fired every day) | −217.23 · 531 · 78.2%    | −2,089.58 · 448 · 79.0% |
| Learner, war on 18-of-20 losses (never fired)                | +1,282.22 · 499 · 81.6%  | not run                |
| Learner, war as a 15% fall, outage by region-vs-rest test    | +797.44 · 516 · 76.2%    | −7,683.61 · 520 · 76.5% |

What the bench taught:

- On `spread-1` the war is on Monday: our quotes averaged 1.27 × list that day against about 1.6 the rest of the
  week, and won about half. The learner followed it with no war logic at all.
- On `spread-1` the outage is Wednesday around Helsinki: requests from within 80 km of it won 58%, the rest 33%,
  because the capital's wins lifted the world multiplier. Hence the undo when the outage is flagged.
- The region-vs-rest outage test fired on most days (some regions win more until their offsets catch up), and the
  wrong outage undo made a false war; hence the run-of-wins rule and no war on the outage day.
- Margin is up about €73k on `spread-1`, and the share on time rises from 45.5% to about 80%: fewer, dearer orders.
  It is still under the 90% minimum; that is the job of admission control (#14) and fees (#15).
