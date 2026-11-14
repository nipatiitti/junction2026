# Slack fees

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk whose gigs hold their early fee when the car has a day or more to wait. Issue #187. Ceiling, the root system and
`strategies/fees` stay as they are.

| File          | Class             | Builds on        | What it decides                                          |
| ------------- | ----------------- | ---------------- | -------------------------------------------------------- |
| `fees.py`     | `SlackFeePlanner` | `FeePlanner`     | The fee schedule of a gig, patient when the car can wait |
| `dispatch.py` | `Desk`            | the ceiling desk | The system: the ceiling desk with the planner above      |

## Run it

From the repository root:

```sh
uv run strategies/slack_fees/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/slack_fees/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `slack-fees`. The `Slack fees` line at the end of a week counts the schedules
that held their early fee.

## The strategy

The plan of `strategies/fees` opens at 0.9 × the typical fee, raises 10% of the way to the top an hour later, 30% of
the way 3 hours after the post (about 1.38 × the typical fee), and reaches the top a travel margin before
`lastPickupAt`.

On the saved `ceiling` weeks, the one-order gigs that booked break down by the hours from their post to their last
pickup:

| Hours to the last pickup | Gigs | Booked fee / typical fee | Booked at 1.07 × or less | Median minutes to book |
| ------------------------ | ---: | -----------------------: | -----------------------: | ---------------------: |
| under 8                  |  156 |                     2.22 |                       0% |                      6 |
| 8 to 16                  |   74 |                     1.60 |                       9% |                      0 |
| 16 to 28                 | 1258 |                     1.17 |                      59% |                      6 |
| 28 to 50                 | 1095 |                     1.06 |                      81% |                      6 |
| over 50                  | 1136 |                     1.18 |                      55% |                     30 |

Most gigs with a day or more to wait booked within minutes, at the opening fee or the first raise, but 19% to 45% of
them paid more: mostly the second raise, though the car still had most of a day.

1. **Patient.** With at least `PATIENT_SPAN` = 16 hours before the top fee is due, every raise after the first hour
   waits until `HOLD_LEAD` = 3 hours before the top. At night it comes at 22:00 the evening before, as every step of
   the plan. A driver who plans the pickup day still sees the early fee in the evening, and the fee climbs on the
   pickup day's morning.
2. **Unchanged otherwise.** A gig with less time, a bundle, and the fees after a drop or a deadline warning are
   planned as before.

## Offline replay

`analysis.replay`'s fee replay on the ten distinct saved `ceiling` weeks: each one-order gig's schedule is planned
from the minute the week posted it, and is judged on the fee and the minute its first driver booked. Where the plan
reaches that fee by then, it finds that driver too. Ceiling's plan finds 1,546 of the 3,044 drivers, and this one
1,309: it reaches the fee later. Where it does not reach the fee in time, the week cannot tell whether a driver would
have taken the lower fee later. The bench below does.

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), ceiling's plan finds 1,220 of the 1,223 drivers,
and this one 1,035. Most of those drivers booked at the opening fee (the median at 0.90 × the typical fee), which both
plans post first; the 185 gigs that this plan loses booked after a raise that it holds back.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy `slack-fees`.

| Seed       |  `ceiling` | `slack_fees` | Difference | On time |
| ---------- | ---------: | -----------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |   €10,206.83 |   +€375.74 |   97.9% |
| `spread-2` |  €6,673.95 |    €6,891.04 |   +€217.09 |   97.5% |
| `spread-3` |  €4,312.02 |    €4,077.60 |   −€234.42 |   99.2% |
| Total      | €20,817.06 |   €21,175.47 |   +€358.41 |         |

Ahead of ceiling by €358.41 in total, the most of the seven, on two of the three seeds. Driver fees fell from €61.08 to
€58.94 a car, so the orders that both won made €1,250 more. Holding the raise gave some of it back: late refunds were
€633 against €407, and it lost 41 orders that ceiling won (€1,519) while it won 36 that ceiling did not (€577). The lead
is under 2% on three seeds.
