# Contextual strategy mix

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Instead of fixing one pricing policy for
the week, its `ContextualPricing` chooses between two existing policies for each request from the booking rate at the
request's first pickup town. Admission, fees, bundling and offers are the headroom system's, unchanged.

| File          | Class               | Builds on         | What it decides                                 |
| ------------- | ------------------- | ----------------- | ----------------------------------------------- |
| `pricing.py`  | `ContextualPricing` | `Strategy`        | Which shared pricing policy quotes each request |
| `dispatch.py` | `Desk`              | the headroom desk | The system, and the post times pricing needs    |

## Run it

From the repository root:

```sh
uv run strategies/contextual_mix/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `contextual-mix`.

## The selection rule

1. **Time each gig from its post.** The desk passes each new gig's first pickup place and post minute to pricing. As
   in [`strategies/tempo`](../tempo/README.md), a gig booked within `quick` = 30 minutes is quick. One still waiting
   after 30 minutes, or one that expires first, is slow. An accepted direct offer counts as a booking.
2. **Estimate each town separately.** A town's estimate is its share of timed gigs that booked quickly. With no timed
   gigs in the town, there is no estimate and the base policy handles every request there.
3. **Switch below the threshold.** With at least one observation, a town whose quick share is below `slow_share` =
   0.5 uses the slow policy. A town at or above 0.5 uses the base policy. The choice is re-evaluated for every
   request, so later observations can switch a town either way.

Both admission's price ceiling and the quote itself delegate to the policy selected for that request. Everything else
about the request is unchanged.

## The two shared policies

The base is `HeadroomPricing` with its usual frozen parameters. The default slow policy is a second
`HeadroomPricing`, starting with `slow_markup` = 0.29 instead of the base's `max_markup` = 0.39. Its maximum still
moves as headroom pricing does. Slow towns therefore get cheaper quotes rather than higher prices when our gigs show
that cars there are hard to move.

There is exactly one base instance and one slow instance for the whole week, not new objects per town or request.
`ContextualPricing.observe` sends **every event to both instances**, while only the selected instance prices a given
request. Each one consequently retains its learned prices, quote outcomes, dealer trust, price-war state and outage
state across selection changes. Both must see every event: otherwise the policy entering a town would resume with
stale dealer and market state, and returning to the other policy would lose what happened while it was inactive. The
desk's strategy list contains only the wrapper, which prevents either instance from missing an event or seeing it
twice.

A different existing ceiling-pricing object can be injected as `slow_policy` when constructing `ContextualPricing`.
The default construction above is what this system's desk uses.

## The variables

`Params` in `pricing.py`, exported as `ContextualParams`, is frozen and inherits the base `HeadroomParams`.

| Variable      | Default | What it does                                                        |
| ------------- | ------- | ------------------------------------------------------------------- |
| `quick`       | 30      | Minutes after a post within which a booking counts as quick         |
| `slow_share`  | 0.5     | Below this observed quick share, an observed town uses slow pricing |
| `slow_markup` | 0.29    | The default slow policy's initial maximum markup over list price    |

The 30-minute quick window follows `strategies/tempo`; the 0.5 slow threshold and 0.29 markup are fixed starting
choices, not measured performance claims. No online weeks were run for this system.
