# Low opening

A dispatch system built on [`strategies/slack_fees`](../slack_fees/README.md): its `Desk` is a subclass of the
slack-fees desk whose first post of a car that can wait opens under the plan's opening fee. Issue #210. Slack fees, the
ceiling system and `strategies/fees` stay as they are.

It does not pay: on five practice weeks, both openings tried made less than slack fees, because drivers waited for
the next raise instead of taking the low fee. The numbers are below.

| File          | Class               | Builds on           | What it decides                                          |
| ------------- | ------------------- | ------------------- | -------------------------------------------------------- |
| `fees.py`     | `LowOpeningPlanner` | `SlackFeePlanner`   | The fee schedule, opening a patient gig's first post low |
| `dispatch.py` | `Desk`              | the slack-fees desk | The system: the slack-fees desk with the planner above   |

## Run it

From the repository root:

```sh
uv run strategies/low_opening/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/low_opening/dispatch.py strategies/slack_fees/dispatch.py --jobs 2
```

Its weeks are saved with the policy `low-opening`. The `Slack fees` line at the end of a week adds how many first
posts opened low, and how far under the plan's opening on average.

## The idea

Driver fees are the largest cost: about €61 of €84 a car for `ceiling` on `spread-1` to `spread-3`. The plan of
`strategies/fees` opens every gig at 0.9 x the typical fee, and no saved level-8 week had opened one lower. On the
three slack-fees weeks of the bench in #188, 749 of the 816 one-car orders were posted 19 hours or more before their
last pickup, and 417 of those booked at the opening fee within 30 minutes. Had all of them taken 0.8 x the typical
fee, the three weeks would have paid €2,466 less; at 0.7, €4,774 less.

## The strategy

1. **Only the first post of a patient gig.** With `PATIENT_SPAN` (16 hours, from slack fees) or more before its top
   fee is due, an order's first post opens at `low` = 0.8 x the typical fee.
2. **A ramp to the plan's opening.** `ramp` = 30 minutes after the post, the fee is the plan's 0.9 x, so a driver
   who would have booked at the opening fee still finds it. Every later step is slack fees': the first raise an hour
   after the post, then a hold until 3 hours before the top.
3. **Everything else as before.** A re-post keeps the order's first viewed fee, so it opens at the plan's fee, as do a
   reprice after a deadline warning, a bundle and a gig with less time.

## Offline replay

`analysis.replay`'s fee replay on the three slack-fees weeks of the bench in #188. Slack fees' plan reaches the fee
and the minute of 822 of the 824 one-car bookings; with the low opening, 405 bookings came while the plan was still
under the fee that the driver took, nearly all at the opening fee in the first half hour. A saved week cannot tell
whether those drivers would have taken less; the bench below does.

## Bench

`strategies.bench` on 2026-11-14 at level 8, `spread-1` to `spread-5`, in one run: this folder with `low` = 0.7
(commit `0fb92eb`), with `low` = 0.8 (commit `ae09558`), and slack fees. Every week was ranked. Slack fees played
its weeks of #188 again to the cent on `spread-1` to `spread-3`. The weeks are saved under `data/scrape/runs/L8/`
with the policy `low-opening`.

| Seed       | `slack_fees` | Opening 0.8 | Opening 0.7 | 0.8 − `slack_fees` |
| ---------- | -----------: | ----------: | ----------: | -----------------: |
| `spread-1` |   €10,206.83 |   €9,489.43 |   €8,358.71 |           −€717.40 |
| `spread-2` |    €6,891.04 |   €6,911.56 |   €6,909.77 |            +€20.52 |
| `spread-3` |    €4,077.60 |   €4,083.27 |   €3,792.47 |             +€5.67 |
| `spread-4` |    €8,903.18 |   €9,106.87 |   €8,506.35 |           +€203.69 |
| `spread-5` |    €7,125.85 |   €6,503.22 |   €5,699.96 |           −€622.63 |
| Total      |   €37,204.50 |  €36,094.35 |  €33,267.26 |         −€1,110.15 |

| Version      | Fee per one-car order | Booked at the opening fee | Minutes to booking | Late refunds | Drops |
| ------------ | --------------------: | ------------------------: | -----------------: | -----------: | ----: |
| `slack_fees` |                €65.55 |                       62% |                213 |         €869 |   194 |
| Opening 0.8  |                €65.06 |                       42% |                248 |       €1,028 |   211 |
| Opening 0.7  |                €66.52 |                       28% |                254 |       €1,101 |   233 |

What the weeks show:

- **Drivers waited.** Of the gigs that opened at 0.8, 39% booked within 30 minutes, at 0.7 only 26%. Their bookings
  came at 0.97 and 0.98 x the typical fee on average, above the plan's 0.9 opening: drivers who saw the fee rise held
  out for the raise an hour after the post rather than book when it reached 0.9. The handbook says drivers learn how
  far our fees rise, and a ramp is a rise.
- **The saving was small and the cost was not.** At 0.8 a one-car order paid €0.49 less to its driver, but late
  refunds rose by €159 and dropped bookings by 17 over the five weeks, and the week lost €1,110. At 0.7 the drivers cost
  more, not less.
- **What it says about the opening.** 0.9 x the typical fee is close to what the cheapest drivers need, as the
  oracle's fee bound (about 0.88 of what we paid) suggested. A lower first fee that later rises teaches drivers to
  wait. The default stays at 0.8, the cheaper of the two to try again.
