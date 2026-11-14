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

## Bench

To be played.
