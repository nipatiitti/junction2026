# Tight margin

A dispatch system built on [`strategies/max_margin`](../max_margin/README.md): its `Desk` is a subclass of the
max-margin desk whose pricing charges like ceiling while the week's drivers keep up, and like max margin once they fall
behind. Issue #211. Max margin and the systems under it stay as they are.

Over five practice weeks it made €2,324.61 more than ceiling (6.7%), higher on four seeds, and €594.96 more than max
margin, but €293.51 less than slack fees. The numbers are below.

| File          | Class          | Builds on           | What it decides                                                   |
| ------------- | -------------- | ------------------- | ----------------------------------------------------------------- |
| `pricing.py`  | `TightPricing` | `MaxPricing`        | Ceiling's prices until the drivers fall behind, then max margin's |
| `dispatch.py` | `Desk`         | the max-margin desk | The system: the max-margin desk with the pricing above            |

## Run it

From the repository root:

```sh
uv run strategies/tight_margin/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/tight_margin/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `tight-margin`. Its pricing line ends with when the week turned tight, or how
many deadline warnings and expired gigs a calm week had by Tuesday night.

## The idea

Issue #211 guessed that max margin's higher maximum paid where the competitor is dear. It does not: on the three seeds
where max margin was played, ceiling sold at 1.46 x the list price on `spread-1`, where max margin lost, and at 1.34
on `spread-2`, where it won. What set `spread-2` apart was its drivers. It had the fewest (736, against 832 and 759),
ceiling's cars there paid their drivers €65.62 against €53 to €62 on the other seeds, and its late refunds were the
highest. Max margin, winning fewer cars at higher prices, paid €57.47 a car and refunded €26 instead of €205: in a week
short of drivers, a higher price rations the cars, and each car left gets a cheaper driver.

The early sign of such a week is our own gigs. By Tuesday night, ceiling's and slack fees' weeks had 6 or 7
`deadline_close` warnings and `gig_expired` gigs on `spread-2` and 10 on `spread-4`, against 0 or 1 on
`spread-1`, `spread-3` and `spread-5`.

## The strategy

1. **Calm: ceiling's prices.** The week starts with a maximum of 1.39 x the list price (`calm_markup` = 0.39), the
   lane and dealer offsets of ceiling (`calm_key_step` = 1.5%, `calm_key_limit` = ±25%) and a floor of the driver
   cost x 1.10 (`calm_risk_premium` = 0.10). Admission counts on the lifted maximum, as in ceiling.
2. **Tight: max margin's prices.** At `tight_after` = 4 deadline warnings and expired gigs before Tuesday 24:00
   (`tight_by`), the pricing turns into max margin's version 3 for the rest of the week: up to 2.0 x the list price,
   the option and lane-length offsets, a floor of the driver cost x 1.25, and admission counting on the learned price
   x 1.2. Later in the week a busy day brings a few warnings in every world, so only Monday and Tuesday count.
3. **The rest.** War guard's price war and outage, and slack fees' patient fees, all week.

## Offline replay

`analysis.replay`'s quote replay on ceiling's three weeks of the bench in #188, with each week's events: the week
turns tight on `spread-2` at Tuesday 10:01, and stays calm on `spread-1` (no warning or expired gig by Tuesday
night) and `spread-3` (one). Without the cut-off at Tuesday 24:00, `spread-1` turned tight on Wednesday at 19:00.

## Bench

`strategies.bench` on 2026-11-14 at level 8. Run 1 played this folder, ceiling and max margin on `spread-4` and
`spread-5`; run 2 played this folder on `spread-1` to `spread-3`, against ceiling's weeks of #188 and max margin's
version 3 of #203 on those seeds. Slack fees' weeks are those of #210. A practice world is deterministic, and none of
those systems has changed since. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the
policy `tight-margin`.

| Seed       | Tight from |  `ceiling` | `max_margin` | `slack_fees` | `tight_margin` | − `ceiling` | − `slack_fees` |
| ---------- | ---------- | ---------: | -----------: | -----------: | -------------: | ----------: | -------------: |
| `spread-1` | never      |  €9,831.09 |    €9,453.90 |   €10,206.83 |     €10,188.94 |    +€357.85 |        −€17.89 |
| `spread-2` | Tue 10:01  |  €6,673.95 |    €7,879.61 |    €6,891.04 |      €6,864.79 |    +€190.84 |        −€26.25 |
| `spread-3` | never      |  €4,312.02 |    €3,297.57 |    €4,077.60 |      €4,276.95 |     −€35.07 |       +€199.35 |
| `spread-4` | Tue 11:01  |  €8,147.90 |    €9,821.84 |    €8,903.18 |      €9,340.35 |  +€1,192.45 |       +€437.17 |
| `spread-5` | never      |  €5,621.42 |    €5,863.11 |    €7,125.85 |      €6,239.96 |    +€618.54 |       −€885.89 |
| Total      |            | €34,586.38 |   €36,316.03 |   €37,204.50 |     €36,910.99 |  +€2,324.61 |       −€293.51 |

What the weeks show:

- **The switch reads the week right.** It turned tight on `spread-2` and `spread-4` on Tuesday morning, and they
  are the two seeds where max margin beat ceiling (by €1,205.66 and €1,673.94). It stayed calm on the three where max
  margin lost.
- **It beats ceiling and max margin.** Ahead of ceiling on four seeds and by €2,324.61 in all, and ahead of max margin
  by €594.96.
- **It does not beat slack fees.** Calm, this system is war guard's pricing with slack fees' fees, and that cost
  €885.89 against slack fees on `spread-5`, a seed war guard had not been played on, while it gained €199.35 on
  `spread-3`.
- **Tuesday is late.** On `spread-2` max margin, pricing high from Monday morning, made €1,014.82 more than this
  system, which switched on Tuesday at 10:01; on `spread-4`, €481.49 more.
