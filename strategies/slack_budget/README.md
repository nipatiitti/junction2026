# Slack-budget admission

A dispatch system built on [`strategies/headroom`](../headroom/README.md): its `Desk` keeps headroom's pricing and
fees and replaces only admission. Above a small on-time reserve, admission may take a positive-margin request that
the usual cost check declines; at the reserve it refuses known delivery risks. Issue #243. Headroom and the systems
it builds on stay as they are.

| File           | Class                  | Builds on           | What it decides                                      |
| -------------- | ---------------------- | ------------------- | ---------------------------------------------------- |
| `admission.py` | `SlackBudgetAdmission` | `LaneCostAdmission` | When on-time slack permits cost or delivery risk     |
| `dispatch.py`  | `Desk`                 | the headroom desk   | The system, and the gig-posting facts admission needs |

`SlackBudgetAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through
`LaneCostAdmission`, with a frozen `Params`. Its optional `lane` and `notes` arguments share those strategies with
the desk.

## Run it

From the repository root:

```sh
uv run strategies/slack_budget/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `slack-budget`. The summary ends with the live counted, late and undelivered
orders, their slack, the cost-eased quotes and the known-risk declines.

## The live slack

A week is ranked only when at least 90% of its counted orders are on time. Admission uses the same slack formula as
`week_facts.late_slack` in [`analysis/facts.py`](../../analysis/facts.py):

```text
slack = counted // 10 - (late + undelivered)
```

`counted` is every order won and not cancelled, including orders still open. An order delivered after its current
deadline is late; an open order past that deadline is undelivered. A ledger `late_refund` also makes an order late,
because it knows tighter note deadlines that the order's deadline may not show, and an `undelivered_penalty` marks it
undelivered. `order_changed` updates the deadline and delivery times. `order_cancelled` removes the order from every
part of the account, including a late or undelivered state it already had. An order is never late and undelivered at
once; an undelivered penalty takes precedence if the ledger reports both outcomes.

**Positive slack is permission for risk, not a forecast of on-time delivery.** It is a live account of orders already
won; it says nothing about whether a new order will arrive on time, and later wins and outcomes change it.

## The two regimes

1. **Above the reserve:** `slack > reserve` (default `reserve` = 2). Admission first runs headroom's lane-cost
   decision unchanged. Only a decline for driver cost is retried. Expected driver cost is reduced by at most
   `risk_discount` = 10%, and the request is accepted only if this leaves a strictly positive expected margin. An
   area-capacity or insufficient-driving-time decline is never eased. With slack at or below the reserve, and always
   when slack is negative, there is no cost easing.
2. **At or below the reserve:** `slack <= reserve`. Headroom admission still makes its usual decision, but an
   accepted request is declined when any of these known risk factors is present:
   - a drive of at least `long_drive` = 6 hours with distance- and reliability-weighted pickup supply below
     `few_drivers` = 2;
   - a note whose parsed deadline is earlier than every option's deadline;
   - any private pickup;
   - a pickup town with at least `slow_evidence` = 2 resolved gigs, of which at least `slow_share` = 50% waited more
     than `slow_booking` = 6 hours for a booking or expired without one. The desk supplies each gig's first pickup and
     posting minute; only that town's own bookings count.

The reserve therefore stays unused rather than guaranteeing that every existing order will be on time. All other
headroom behavior, including option choice, capacity, return legs and pricing, is unchanged.

## The variables

`Params` in `admission.py` extends `LeadCostParams` and is exported beside `SlackBudgetAdmission`.

| Variable        | Default  | What it does                                                       |
| --------------- | -------- | ------------------------------------------------------------------ |
| `reserve`       | 2 orders | Slack that admission protects; easing requires strictly more       |
| `risk_discount` | 0.10     | Maximum expected-cost easing on a retried cost decline             |
| `long_drive`    | 6 hours  | Drive length that is risky with few drivers near the pickup        |
| `few_drivers`   | 2.0      | Weighted pickup supply below which such a drive is risky           |
| `slow_booking`  | 6 hours  | How long a gig may wait for a driver before its town counts as slow |
| `slow_evidence` | 2 gigs   | Resolved gigs needed before a town's booking speed counts          |
| `slow_share`    | 0.5      | Share of slow resolved gigs that makes the town a risk              |

No played-week result is claimed here: this system has been checked offline only.
