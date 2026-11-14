# Eighty

A dispatch system built on [`strategies/headroom`](../headroom/README.md) that puts the changes that each beat the
headroom desk into one desk, adds three switchable layers of its own, and tunes the variables on five seeds. Issue
#254: the goal is €80,000 of margin over the level-8 practice seeds `spread-1` to `spread-5`, every week ranked. It is
not reached yet: the best version makes €50,369 (below). The systems it builds on stay as they are.

| Part      | Class             | Builds on                               | What it decides                                                                                |
| --------- | ----------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| fees      | `SoftTopPlanner`  | [`soft_top`](../soft_top/README.md)     | The dawn fee schedule, topped at 2 × the lane fee                                              |
| admission | `ScaledAdmission` | [`same_day`](../same_day/README.md)     | The fastest option that pays; `cost_scale` on its driver cost                                  |
| pricing   | `CostPricing`     | [`lane_prior`](../lane_prior/README.md) | The headroom price lifted by the delivery place; a cost-aware move and per-key maximum offsets |

`ScaledAdmission` is in `admission.py` and `CostPricing` in `pricing.py`, next to this file. Both are subclasses of
`Strategy` ([`strategies/strategy.py`](../strategy.py)) through the classes they build on, with a frozen `Params`.
Their new variables are off by default, so with them off the parts are exactly the classes they build on.

## Run it

From the repository root:

```sh
uv run strategies/eighty/dispatch.py --level 8 --seed spread-1
uv run --env-file .env python -m strategies.bench strategies/eighty/dispatch.py --seeds spread-1..spread-5 --jobs 4
EIGHTY_TAG=cap30 EIGHTY_PARAMS='{"admission": {"capacity_per_driver": 0.30}}' \
  uv run --env-file .env python -m strategies.bench strategies/eighty/dispatch.py --seeds spread-1..spread-5 --jobs 4
```

Its weeks are saved with the policy `eighty`, or `eighty-<tag>` for a variant.

## The variables

`PARAMS` in `dispatch.py` holds the values this system plays with, by part, over the defaults of each part's class:
today fees `open` 0.8, the gig's opening fee over the lane fee (0.9 in `strategies/dawn_fees`). Three environment
variables change a run without a new file:

| Variable        | What it does                                                                                                                                               |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EIGHTY_PARAMS` | JSON with a key per part (`admission`, `pricing`, `fees`, `lane`, `bundler`, `offers`) naming fields of its `Params`, for example `{"fees": {"top": 1.7}}` |
| `EIGHTY_TAG`    | Names the variant: its weeks are saved with the policy `eighty-<tag>`                                                                                      |
| `EIGHTY_LOG`    | An absolute folder: each week's output, with the strategies' summaries, also goes to `<tag>-<seed>.log`                                                    |

The desk sets admission's `price_factor` and `min_margin` itself before each quote, so changing those two does nothing.
The new variables:

| Part      | Variable       | Default | What it does                                                                                                                                         |
| --------- | -------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| admission | `cost_scale`   | 1.0     | Multiplies the lead cost: the decline threshold, the price floor                                                                                     |
| pricing   | `cost_slope`   | 0       | Moves a price by this share of log(cost / price) from the week's mean, within `cost_limit` (0.2)                                                     |
| pricing   | `shade`        | 0       | Lowers every price by this, in logs                                                                                                                  |
| pricing   | `key_cap_step` | 0       | Step of the maximum's own offset per pickup place, delivery place and dealer, learned at the maximum toward `cap_win`, within `key_cap_limit` (0.15) |

## Bench

Level 8, seeds `spread-1` to `spread-5`, four weeks at a time, 2026-11-14. Every week was ranked and is saved under
`data/scrape/runs/L8/` with the policy `eighty-<tag>`.

| Variant                                 | `spread-1` | `spread-2` | `spread-3` | `spread-4` | `spread-5` |   Total |
| --------------------------------------- | ---------: | ---------: | ---------: | ---------: | ---------: | ------: |
| **fees `open` 0.8 (the default)**       |    €12,857 |     €9,822 |     €5,712 |    €13,818 |     €8,159 | €50,369 |
| admission `capacity_per_driver` 0.30    |    €12,541 |    €10,365 |     €5,551 |    €14,306 |     €7,517 | €50,280 |
| `capacity_per_driver` 0.55              |    €12,838 |    €10,593 |     €5,471 |    €13,202 |     €7,874 | €49,978 |
| `capacity_per_driver` 0.40              |    €12,537 |    €10,403 |     €5,551 |    €14,243 |     €6,859 | €49,593 |
| fees `top` 1.7                          |    €12,654 |     €9,846 |     €5,444 |    €13,777 |     €7,236 | €48,960 |
| v1: the three classes at their defaults |    €12,587 |    €10,062 |     €5,305 |    €13,454 |     €7,337 | €48,745 |
| cost-aware 0.3, capacity 0.30           |    €12,405 |     €9,723 |     €5,756 |    €13,165 |     €7,458 | €48,507 |
| `capacity_per_driver` 0.14              |    €11,655 |    €10,062 |     €5,290 |    €13,352 |     €7,293 | €47,652 |
| per-key maximum 0.02, capacity 0.30     |    €12,347 |    €10,163 |     €5,512 |    €13,391 |     €6,234 | €47,647 |
| capacity 0.40, `open` 0.8               |    €12,783 |     €9,378 |     €5,590 |    €12,633 |     €7,065 | €47,450 |
| `target_win` 0.50                       |    €11,901 |     €8,475 |     €5,473 |    €13,278 |     €8,073 | €47,200 |
| capacity 0.40, `cap_win` 0.42           |    €11,632 |     €9,587 |     €5,959 |    €13,427 |     €6,548 | €47,153 |
| capacity 0.40, `cap_win` 0.58           |    €12,781 |     €8,721 |     €5,626 |    €13,613 |     €6,200 | €46,941 |
| capacity 0.40, `cap_win` 0.66           |    €13,822 |     €8,611 |     €5,762 |    €12,622 |     €5,993 | €46,811 |
| per-key maximum 0.04, capacity 0.30     |    €11,585 |     €8,782 |     €5,310 |    €13,594 |     €6,573 | €45,845 |
| `target_win` 0.40                       |    €12,507 |     €8,069 |     €5,496 |    €12,757 |     €6,556 | €45,385 |
| `cost_scale` 0.85, capacity 0.30        |    €11,874 |     €8,960 |     €5,195 |     €8,299 |     €6,249 | €40,576 |
| `cost_scale` 1.15, capacity 0.30        |    €11,353 |     €7,760 |     €3,735 |    €10,464 |     €5,431 | €38,743 |

## What the bench shows

- **The week is deterministic.** `cap_high` 0.75 and an admission `min_margin` (which the desk overwrites) played
  v1's €48,744.69 to the cent. A change moves the rest of the week, though: two changes that each gained about €1,600
  lost €1,300 together (capacity 0.40 with `open` 0.8), so read a difference under about €1,500 on the total as
  noise.
- **The maximum sets the price.** On `spread-1`, 469 of 808 quotes were at headroom's maximum, which settles where
  `cap_win` (half) of the quotes at it win. `target_win` moves only the quotes under it. Cheaper (`cap_win` 0.58,
  0.66) and dearer (0.42) both lost.
- **Cheaper prices lose online, though a replay says otherwise.** Against each request's price bracket, taken from the
  team's saved weeks of the same seed, quoting 6% lower would raise margin per quote by 19%, and the cost-aware move
  by as much again. Played, both lost: the competitor cuts its prices for a dealer where we win most of the requests.
- **The driver cost estimate is right.** Scaling it by 0.85 or 1.15 lost €8,000 to €10,000.
- **Little of the competitor's price carries between worlds.** Fitted leave-one-seed-out on the brackets, the places,
  distance, hour, option and drivers near both ends explain 6% to 9% of what the week and day do not; the lane of one
  world explains 48%, but a lane gets two quotes a week.

Every system the team has saved on all five seeds makes €48,000 to €52,000; the best was `r-sprint100` (€51,718). The
only one near €80,000 is the TypeScript `recall` (€77,519), which remembers each seed's requests from earlier weeks
and is plain `bidprice` on a week it has not seen.
