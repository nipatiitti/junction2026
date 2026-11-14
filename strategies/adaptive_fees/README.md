# Adaptive fees

A dispatch system built on the root [`dispatch.py`](../../dispatch.py): its `Desk` replaces `FeePlanner` with
`AdaptiveFees`, which discounts the typical fee while the week's on-time share is above target. Issue #229.
The root dispatcher and `strategies/fees` stay as they are.

| File          | Class          | Builds on       | What it decides                                   |
| ------------- | -------------- | --------------- | ------------------------------------------------- |
| `fees.py`     | `AdaptiveFees` | `FeePlanner`    | The fee of a gig, and when to spend on-time slack |
| `dispatch.py` | `Desk`         | the root `Desk` | The system: swaps in the planner above            |

## Run it

From the repository root:

```sh
uv run strategies/adaptive_fees/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/adaptive_fees/dispatch.py dispatch.py --jobs 2
```

Its weeks are saved with the policy `adaptive-fees`. At the end of a week the planner prints the number of
schedules it discounted and the running on-time share.

## The idea

The target is **95% on time**, five points above the 90% delivery minimum. At or above it, the typical fee in
the schedule is multiplied by **0.85**; below it, every new schedule is the root fee planner's unchanged one.
This lowers both the opening and the top fee, and gives a direct test of whether buying back a few percentage
points of on-time share would have been cheaper.

The running share is smoothed towards 95% with a prior of 10 orders. It counts orders past their deadline as
late immediately, before an eventual delivery, so a deteriorating week switches back to normal fees rather
than continuing to discount. `Desk.rejoin` feeds saved events to the planner too, so the state is rebuilt on
a restart. Bundles keep the root bundler's fee planning.

Useful question to measure: fee saved against extra late refunds, with the on-time share still comfortably
above 90%. If the share falls below the target, this system should be visible paying normal fees rather than
ploughing on cheaply through an unranked week.

This is an on/off discount, not an optimiser: the target and the 15% discount are deliberately small enough
to preserve a buffer around the 90% rule.
