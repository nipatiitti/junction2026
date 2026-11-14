# Headroom pricing

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling desk
with four strategies of issue #200. Three have their own folders, and the fourth, the pricing, is this one's. Ceiling
and the root system stay as they are.

| File          | Class             | Builds on        | What it decides                                       |
| ------------- | ----------------- | ---------------- | ----------------------------------------------------- |
| `pricing.py`  | `HeadroomPricing` | `CeilingPricing` | The price of a quote, under a maximum that moves      |
| `dispatch.py` | `Desk`            | the ceiling desk | The system: the ceiling desk with the four strategies |

| Strategy of the desk | Folder                                           | What it replaces                       |
| -------------------- | ------------------------------------------------ | -------------------------------------- |
| `LaneFee`            | [`strategies/lane_fee`](../lane_fee/README.md)   | The request's own typical fee          |
| `LaneCostAdmission`  | [`strategies/lead_cost`](../lead_cost/README.md) | Ceiling's admission (`ChainAdmission`) |
| `LaneFeePlanner`     | [`strategies/dawn_fees`](../dawn_fees/README.md) | The fee planner of `strategies/fees`   |
| `HeadroomPricing`    | this folder                                      | Ceiling pricing                        |

`HeadroomPricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `CeilingPricing`,
with the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`. The systems
[`lane_prior`](../lane_prior/README.md), [`town_open`](../town_open/README.md), [`same_day`](../same_day/README.md)
and [`soft_top`](../soft_top/README.md) each add one strategy to this desk.

## Run it

From the repository root:

```sh
uv run strategies/headroom/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/headroom/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `headroom`. The `Headroom` line at the end of a week gives where the maximum
ended, and the wins and losses at it.

## What the saved weeks show

Ceiling pricing quotes at most 1.39 times the list price, lifted by dealer trust and the outage. At level 8 the
competitor's price level is from 26% to 54% above the list price, new in every world, so one number cannot fit.

- On `spread-1`, 188 of the 677 quotes of the saved `ceiling` week were at the maximum, and the quotes at 1.65 to
  1.75 times the list price (the maximum with a trusted dealer's lift) won 63% to 70% of the time: the dealers would
  have paid more.
- The root pricing, which has no maximum and aims at half of its quotes won, earned €2,741 less than ceiling on
  `spread-1` to `spread-5`. So a maximum pays, but its height should come from the world.
- Over 198,543 saved quotes, a price 1% higher loses about 1.9 points of win share near 50%
  (`strategies/lane_prior/fit.py`). At that slope the margin of a week is almost flat between 45% and 65% of the
  quotes won: a lower price wins more cars for less each.
- What is not flat is the competitor. Each morning it lowers its prices for a dealer whose requests we mostly won,
  and raises them for a dealer where we won few (the handbook). So of two win shares that earn the same today, the
  lower one leaves a dearer competitor tomorrow.

## The strategy

1. **The maximum starts at 1.39** times the list price (`max_markup`), as in ceiling pricing, and every price
   starts there.
2. **A win at the maximum raises it, a loss at it lowers it.** After each quote that was priced at the maximum, it
   moves by `cap_step` × (won − `cap_win`), in logs: 0.6% up after a win and 0.6% down after a loss. It settles where
   half of the quotes at the maximum win, and stays between 1.20 and 1.62 times the list price.
3. **A win at the maximum counts as a usual win.** In ceiling pricing it moves nothing. Here the learned price may
   follow the maximum up, so the next quote is at the new maximum.
4. **What does not move it.** A quote priced with the outage boost, a quote on the price war's day, and a quote at
   the driver cost floor: each has its own rule in ceiling pricing, and none says where the usual maximum is.

5. **Under half.** The learned price settles where 45% of its quotes win (`target_win`), not 50% as in ceiling
   pricing: a loss lowers it by 1.35% and a win raises it by 1.65%.

Everything else is ceiling pricing: the learned multiplier with its place and dealer offsets, the floor at the driver
cost plus its risk premium, dealer trust, the outage and the price war.

## The variables

`Params` in `pricing.py`, exported as `HeadroomParams`, next to those of `strategies/ceiling` and
`strategies/pricing`.

| Variable     | Default | What it does                                                    |
| ------------ | ------- | --------------------------------------------------------------- |
| `max_markup` | 0.39    | Where the maximum starts: the list price × (1 + `max_markup`)   |
| `target_win` | 0.45    | The share of its quotes that the learned price settles to win   |
| `cap_win`    | 0.5     | The share of the quotes at the maximum that it settles to win   |
| `cap_step`   | 0.012   | The step of the maximum per outcome at it, in logs              |
| `cap_low`    | 0.20    | The maximum never falls below the list price × (1 + `cap_low`)  |
| `cap_high`   | 0.62    | The maximum never rises above the list price × (1 + `cap_high`) |

## Bench

Level 8, seeds `spread-1`, `spread-2` and `spread-4`, the code of this branch, with
`uv run python -m strategies.bench strategies/<system>/dispatch.py --seeds spread-1,spread-2,spread-4`. Every week is
ranked, and each is saved in `data/scrape/runs/L8/` under its system's policy. `ceiling` is the saved week of
`strategies/ceiling` on the same seed.

| Seed       | `ceiling`      | `headroom`     | `lane_prior`   | `town_open`    | `same_day`     | `soft_top`     |
| ---------- | -------------- | -------------- | -------------- | -------------- | -------------- | -------------- |
| `spread-1` | €9,831.09      | €12,670.71     | €12,170.85     | €12,137.41     | €12,283.73     | €13,297.12     |
| `spread-2` | €6,673.95      | €9,378.79      | €10,492.81     | €8,320.56      | €9,371.17      | €9,816.59      |
| `spread-4` | €8,147.90      | €13,089.25     | €13,086.78     | €12,604.28     | €13,975.61     | €13,658.73     |
| **Total**  | **€24,652.94** | **€35,138.75** | **€35,750.44** | **€33,062.25** | **€35,630.51** | **€36,772.44** |
| On time    | 97.9%          | 98.2%          | 98.6%          | 97.8%          | 98.4%          | 98.4%          |

All five systems are over €12,000 on `spread-1` and on `spread-4`. No system is on `spread-2`: that world's prices
are low (the price that wins half of a day's quotes is 1.03 to 1.39 times the list price there, against 1.23 to 1.50
on `spread-1`), and `ceiling` makes €6,674 in it.

**One week proves little.** The same seed moves by several hundred euros between two versions with little in common:
a booking a minute earlier changes which driver is free for the next car, and the rest of the week with it.

What the four strategies of this desk are worth, from single weeks on `spread-1` that differ in one of them (each
saved under the policy named):

| What was played                                                           | Policy               | Margin     |
| ------------------------------------------------------------------------- | -------------------- | ---------- |
| The ceiling desk                                                          | `ceiling`            | €9,831.09  |
| With dawn fees                                                            | `dawn-fees`          | €9,923.03  |
| With dawn fees and the lead-cost admission                                | `lead-cost`          | €11,591.16 |
| With those, the lane fee and room for twice the unbooked orders           | `a-lane`             | €11,815.71 |
| With those and this pricing: the headroom system                          | `headroom`           | €12,670.71 |
| The headroom system with the fee schedule of `strategies/fees`, a control | `x-cap-lane-oldfees` | €10,573.65 |

Tried on this desk and left out, each over `spread-1`, `spread-2` and `spread-4` unless said:

- **The win share.** Aiming at 45% of the quotes (and half at the maximum) made €35,139; at 50% (and 62%) €34,387
  (`y-sprint`); at 58% (and 68%) €32,672 (`y-sprint-high`).
- **The cost table measured under dawn fees** (`strategies/lead_cost`): €33,460, with 95.9% on time on `spread-4`.
- **Larger price steps for each day's first 20 outcomes**: €33,237 (`early-read`), and with half of that €33,735
  (`c-early-soft`). The day's level does move, but the larger steps also move the price on a morning's chance run.
- **The trust an order buys, taken off its driver cost** (`strategies/trust_value` on this admission): €10,757 on
  `spread-1` against €12,346 without (`x-cap-lane-trust`): 420 orders, and driver fees up by a fifth.
- **A warm start at 1.30 times the list price** instead of the maximum: €12,360 on `spread-1` (`c-warm`).
- **Bundles on the dawn schedule**: €35,506 (`c-bundles`), €367 more, within what one week moves by.
