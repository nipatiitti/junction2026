# Chain-optimised bundling

A dispatch system built on [`strategies/headroom`](../headroom/README.md). It replaces only the base
[`Bundler`](../bundling/README.md): `RouteBundler` considers where an order belongs in a route, rather than always
appending it to the end. Headroom's admission, lane fees, dawn fee schedules, pricing, notes, direct offers and desk
loop stay unchanged. The root dispatcher and the other systems are not changed.

## Run it

From the repository root:

```sh
uv run strategies/chain_opt/dispatch.py --level 8 --seed spread-1
```

Weeks are recorded with the policy `chain-opt`.

## The strategy

Orders wait and become ready exactly as in the base bundler. Ready orders head chains by their first pickup window;
orders still waiting can join them. Starting with one order, the route planner repeats these steps:

1. Take every unused order with the same audience as the chain's head. Insert its whole stop sequence at every boundary
   in the current route, including the front and the append position used by the base.
2. Reject an insertion unless the base `feasible` check accepts it and its marginal saving exceeds `min_saving`. The
   saving is the sum of the orders' solo costs minus the route cost. Costs use the base model: road drives, the trips
   out and home, and transit between a delivery and the next pickup, weighted by `transit`.
3. Take the feasible insertion with the largest marginal saving. For a given added order, this is the cheapest
   insertion: it gives the completed route the lowest total driver-minutes. Repeat until no insertion qualifies.

The base constraints are unchanged: at most `max_cars` cars and `max_drive` road minutes, always within the 12-hour
rule; every stop window and site's opening hours; the lead time, delivery buffer, longer-drive allowance and maximum
wait for the next pickup; identical driver audiences; and the minimum saving. Fee scaling uses the chosen route's cost
through the base `fee_share`, and all refusal, expiry, cancellation and deadline break-up behaviour is the base desk's.

Appending is one of the candidate positions. If cheapest insertion never selects an earlier position, `route_chains`
returns the base `chains` result, so the append-only fallback is exactly the base planner.

## The variables

`Params` is a frozen subclass of the base bundling `Params`. It adds no thresholds; every default is unchanged.

| Variable     | Default | What it controls                                             |
| ------------ | ------- | ------------------------------------------------------------ |
| `max_cars`   | 3       | Most cars in one gig                                         |
| `max_drive`  | 480     | Most planned road minutes, also capped by the 12-hour rule   |
| `transit`    | 0.5     | Cost of a transit minute relative to a minute at the wheel   |
| `min_saving` | 10.0    | Minimum marginal saving in driver-minutes for an insertion   |
| `max_wait`   | 120     | Longest wait for a later pickup's window to open             |
| `lead`       | 120     | Minutes allowed for a driver to see the gig and reach pickup |
| `slow`       | 1.15    | Timing-check multiplier on road minutes                      |
| `buffer`     | 60      | Minutes by which a delivery precedes its window's end        |
| `hold`       | 45      | Longest batch-order wait for more cars                       |
| `quiet`      | 20      | Batch inactivity after which held orders can go              |
| `safe`       | 360     | Latest waiting ends this long before the last pickup         |
| `fee_floor`  | 0.6     | Lower bound on bundle fees relative to the sum of solo fees  |
| `fee_cap`    | 0.95    | Upper bound on bundle fees relative to the sum of solo fees  |

## Limits

This is still greedy chain construction, not a global route optimiser: an accepted insertion is never revisited, and
chains are headed in the base order. Only whole orders move; stops within an order, including both legs of a trade-in,
are not interleaved or reversed. The candidate set is the orders waiting at that desk step, and all base timing and
capacity limits remain. No online runs or performance measurements were made for this change.
