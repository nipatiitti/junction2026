# Learned hold

A dispatch system built on [`strategies/headroom`](../headroom/README.md). The one change is when the bundler posts
an order: every order waits for a chain, and its pickup town's recent bookings decide for how long. Headroom and the
shared bundler stay as they are.

| File          | Class                 | What it holds                                   |
| ------------- | --------------------- | ----------------------------------------------- |
| `dispatch.py` | `Desk`                | The headroom desk with the adaptive bundler     |
| `bundling.py` | `AdaptiveHoldBundler` | A `Bundler` with a learned wait for every order |

## Run it

From the repository root:

```sh
uv run strategies/learned_hold/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved under the policy `learned-hold`.

## The learning rule

The desk tells the bundler when a gig is accepted and where its first pickup is. For that town, the bundler keeps
only two running estimates and their effective observation weight:

- **minutes to a terminal outcome**, from the post to `gig_booked` or `gig_expired` (an accepted direct offer counts
  as a booking);
- **booked share**, one for a booking and zero for an expiry.

Each terminal gig updates both estimates by `1 / (1 + weight)`. The weight then grows by one, capped at four
(`memory`), so a mature estimate gives a new gig one fifth of its weight. Before each observation or hold decision,
the weight fades with a 12-hour half-life (`half_life`). A `gig_viewed` ages the estimates and records interest, but
is not a booking failure: only a booking or expiry changes the estimates.

Minutes per booked gig are `minutes / max(booked share, 0.05)`. The wait is linear between 30 minutes per booked gig
(`fast`), which gives a 15-minute hold (`min_hold`), and 180 minutes (`slow`), which gives 120 minutes (`max_hold`).
A smaller booked share therefore lengthens the wait. The result is rounded and bounded by `min_hold` and `max_hold`.
When the faded weight is below one, the learned wait is blended towards the base 45-minute wait, so stale evidence
gradually loses its effect.

With no terminal observations, a town uses the base **45 minutes** (`hold`). Every order waits, including one without
a batch; this is the waiting scope of `bundling_more`, with the base's other bundling thresholds. A batch can still
post early once it is quiet for 20 minutes. No order waits beyond the base safety limit of six hours before
`lastPickupAt` (`safe`). Deadline warnings still release a waiting order alone, and cancellation, change-of-plan and
bundle break-up behaviour are unchanged.
