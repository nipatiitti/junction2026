# Max margin

A dispatch system built on [`strategies/war_guard`](../war_guard/README.md) and
[`strategies/slack_fees`](../slack_fees/README.md), the two systems that beat `ceiling` in #188: its `Desk` is a
subclass of the war-guard desk whose pricing may charge up to 2.0 x the list price, and which pays the patient fees
of slack fees. Issue #203. The systems it builds on stay as they are.

It aimed at two to three times ceiling's margin. It does not get there: over three practice weeks, all three
versions came within 3% of ceiling, below it. Charging more than the competitor's price trades orders for margin
almost one for one. The numbers are below.

| File          | Class        | Builds on          | What it decides                                            |
| ------------- | ------------ | ------------------ | ---------------------------------------------------------- |
| `pricing.py`  | `MaxPricing` | `WarGuardPricing`  | The price of each quote, up to 2.0 x the list price        |
| `dispatch.py` | `Desk`       | the war-guard desk | The system: the pricing above, with `SlackFeePlanner` fees |

## Run it

From the repository root:

```sh
uv run strategies/max_margin/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/max_margin/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `max-margin`. Its pricing line ends with the same-day quotes, the quotes above
ceiling's old maximum of 1.39 x the list price, and the learned offsets of the option and the lane's length.

## The idea

Ceiling pricing never quotes above 1.39 x the list price, lifted only for dealer trust and the outage. Its world
multiplier starts at that maximum, and the lane and dealer offsets add on top of it. So once the multiplier is at the
top, a request that would pay more never gets a higher price, and a world whose competitor sits at 1.54 x the list
price, as level 8 allows, is quoted as if it sat at 1.39.

What the saved weeks said before the first max-margin week (`out/spread.sqlite`, `analysis.oracle`):

- On `spread-1`, ceiling made €9,831. The oracle puts about €11,400 of revenue between the prices of the orders it won
  and what those dealers would have paid, and €4,591 of fees above the cheapest comparable gigs.
- Every system played so far won at 1.33 to 1.40 x the list price on average. None had priced higher across the
  board.
- For dealers with 15 or more orders on time, half of the quotes at 1.6 to 1.7 x the list price won. Those prices were
  sent where a system lifted them, for trust or the outage, so this was selection as much as willingness to pay.

## The strategy

1. **A far higher maximum.** The price may climb to `max_markup` = 1.0 over the list price, 2.0 x, before the trust
   and outage lift. The world multiplier starts at `start` = 1.39, ceiling's maximum.
2. **Offsets for the option and the lane's length.** Beside the pickup, delivery and dealer offsets, the price learns
   one for the option quoted (`same_day`, `next_day`) and one for the lane's length, read from the cheapest option's
   list price (`BANDS`: up to €35, €58 and €96, about 60, 150 and 300 km, and above). Each offset moves `key_step` =
   2% in logs per outcome (ceiling: 1.5%), within `key_limit` = ±50% (ceiling: ±25%).
3. **Half the quotes won.** Every quote aims to win half of the time, as in ceiling: `target_win` = 0.5, and
   `target_fast` = 0.5 for same-day quotes.
4. **No thin orders.** No quote goes under the driver cost x (1 + `risk_premium`) = 1.25 (ceiling: 1.10).
5. **Admission's price.** Admission takes a request when its driver cost x 1.25 fits under the learned price x (1 +
   `headroom`) = 1.2, lifted for trust and the outage, never above the maximum. Counting on the maximum, it would
   take every car whose driver costs less than 1.6 x its list price.
6. **The rest.** The fees of `strategies/slack_fees`, the price war and the outage of `strategies/war_guard`, and the
   timed return legs of ceiling.

## Offline replay

`analysis.replay`'s quote replay of the first version on the three `ceiling` weeks of the bench in #188 (`spread-1` to
`spread-3`). A saved week knows the answer to a quote only at or below the price it sent, so the replay cannot price
this idea: 917 quotes have no known answer (ceiling's own: 611), and the learned world multiplier drifts down to 1.24
to 1.38 on the answers it does know. It quotes 87 to 405 requests a week above the old maximum.

## Bench

`strategies.bench` on 2026-11-14 at level 8, three versions, each played alone on `spread-1` to `spread-3` and set
against ceiling's weeks of the bench in #188 on the same seeds (a practice world is deterministic: ceiling's code has
not changed since). Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy
`max-margin`; each version is its own commit.

1. **Version 1** (`042eb9e`): one learned price from 1.42, aiming to win 40% of all quotes.
2. **Version 2** (`c667e48`): the offsets for the option and the lane's length, from 1.39; same-day quotes aim at 40%,
   the others at half.
3. **Version 3** (`afcb736`, this folder): every quote aims at half.

| Seed       |  `ceiling` |  Version 1 |  Version 2 |  Version 3 | Version 3 − `ceiling` |
| ---------- | ---------: | ---------: | ---------: | ---------: | --------------------: |
| `spread-1` |  €9,831.09 |  €9,005.29 |  €9,078.92 |  €9,453.90 |              −€377.19 |
| `spread-2` |  €6,673.95 |  €7,853.19 |  €7,966.52 |  €7,879.61 |            +€1,205.66 |
| `spread-3` |  €4,312.02 |  €3,417.65 |  €3,447.77 |  €3,297.57 |            −€1,014.45 |
| Total      | €20,817.06 | €20,276.13 | €20,493.21 | €20,631.08 |              −€185.98 |

| Version   | Orders | Price / list | Driver fee per order | Margin per order | Orders that lost money | Late refunds |
| --------- | -----: | -----------: | -------------------: | ---------------: | ---------------------: | -----------: |
| `ceiling` |    952 |        1.373 |               €61.08 |           €22.54 |          102 (−€3,316) |         €407 |
| 1         |    597 |        1.505 |               €52.09 |           €34.27 |             41 (−€864) |         €139 |
| 2         |    633 |        1.470 |               €54.06 |           €32.97 |           49 (−€1,295) |          €61 |
| 3         |    682 |        1.462 |               €54.04 |           €30.45 |           63 (−€1,756) |         €154 |

What the weeks show:

- **Each order pays more.** On the orders that both version 3 and ceiling won, version 3 made €4,622 more (594
  orders): higher prices, cheaper drivers for fewer cars, and fewer late refunds.
- **But fewer are won.** It lost 358 orders that ceiling won, which had earned ceiling €7,662, and won 88 that ceiling
  did not (€2,350). In version 2, 349 of the lost orders were quoted, at a median 15% above the price ceiling won them
  at; only 37 sat at the driver cost floor.
- **Dealers are mixed.** In version 1's weeks, quotes to dealers with little trust won 48% at 1.2 x the list price and
  about 25% from 1.3 to 1.7. About a quarter of the requests take almost any price; the rest stop near the
  competitor's. A price that aims at half the wins sits above what the price-sensitive dealers accept. Ceiling's cap
  at 1.39 is close to their limit, which is why it keeps its volume.
- **What did not help.** Aiming at 40% wins lost on every option: version 2's same-day orders made €1,470 less than
  ceiling's. A dealer's early wins at a high price hardly told its later ones (a correlation of 0.17 between the two
  halves of its week), so per-dealer prices learn little.
- **What the world decides.** Every version beat ceiling on `spread-2` by about €1,200 and lost on `spread-3` by about
  €900 to €1,000. The higher maximum pays in some worlds and not in others; three seeds cannot tell which in advance.
