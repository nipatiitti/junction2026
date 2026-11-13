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

Eighteen losses in the last twenty quotes of one day, between 08:00 and 18:00, on at least six pickup places, is the
price war. At a 50% win target a run like that comes by chance on about one day in twenty; in the war we lose nearly
every quote, so it shows within about an hour. The model then undoes what those losses taught, and until 18:00 quotes `0.8 × m` (the competitor's 20% cut).
Those quotes teach nothing. The next day it quotes `m` again. `Params(war_cut=None)` declines during the war instead.

## The outage (levels 6–8)

A region is a town and the places within 80 km of it, from the world map. Six wins in a row in one region on one day,
with a win share more than 20 points above the rest of the day, is the outage there. Until 18:00 the requests that
touch the region get `1.2 × m` (dealers there pay about 30% more). Three losses among the last six boosted quotes end
the boost early.

## Dealer trust (level 8)

A `ledger` revenue line with no late refund in the same minute is an order on time: that dealer's count rises by one,
up to 25. A late refund or an undelivered penalty halves the count, rounded down. The price for the dealer is
multiplied by `1 + count / 100`.

## Bench

Level 8, seeds `spread-1` to `spread-5`, margin in euros and the share of orders on time.

BENCH_TABLE

## Tests

```sh
uv run pytest strategies/pricing
```
