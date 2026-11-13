# A cheaper bundle fee

A folder that builds on [`strategies/price_ladder`](../price_ladder/README.md), as
[`../scarcity_cost/`](../scarcity_cost/README.md) does: its own copy of that dispatcher with a bundler that keeps a
smaller share of what a bundle's cars would cost alone. Issue #160. The root `dispatch.py` and `strategies/bundling`
stay as they are.

| File          | What it holds                                                                           |
| ------------- | --------------------------------------------------------------------------------------- |
| `dispatch.py` | A copy of `strategies/price_ladder`'s dispatcher that bundles with the strategy below   |
| `bundling.py` | `CheapBundler`: the bundling of `strategies/bundling`, with the bundle fee capped lower |

## Run it

From the repository root:

```sh
uv run strategies/bundling_cheaper/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/bundling_cheaper/dispatch.py strategies/price_ladder/dispatch.py --jobs 4
```

Its weeks are saved under the policy `bundling-cheaper`.

## What it changes

A bundle's fee is the sum of its cars' typical fees times the chain's cost over the sum of the solo costs, clamped to
`[fee_floor, fee_cap]`. The base clamps it to 0.6–0.95, so a bundle may pay 95% of what its cars would have cost
posted alone. Here the cap is **0.8**.

A two-car bundle then pays **1.2 to 1.6 times a single car's fee** for twice the work: more in total, which is what
makes a driver take it rather than the one car, but a smaller share of the solo bill, which is what we keep.

**The floor stays 0.6, and that is the point.** A bundle of `n` cars pays `n × share` of a single car's fee, so a
share at or under `1/n` would pay the driver less than the one car they could take instead, and no bundle would ever
be booked. For two cars that limit is 0.5; 0.6 is the base's floor and is comfortably above it. The floor cannot
simply be pushed down — only the cap can.

## Ablation

`Params(fee_cap=0.95)` reproduces the base's fee rule exactly, so the cap is the only difference and the bench
against the baseline isolates it.

## Bench

Level 8, seed `spread-1`, one practice week per variant, played on the server by `strategies.bench`. Margin is the
score; `fees / car` and `orders in chains` are read from each week's own ledger and snapshot.

| variant                       | margin        | vs `dispatch.py` | orders won | on time | ranked | fees / car | orders in chains |
| ----------------------------- | ------------- | ---------------- | ---------- | ------- | ------ | ---------- | ---------------- |
| `strategies/scarcity_cost`    | **€8,884.43** | +€821.03         | 364        | 98.6%   | yes    | €60.62     | 35               |
| `dispatch.py` (root)          | €8,063.40     | —                | 369        | 98.1%   | yes    | €64.21     | 40               |
| `strategies/price_ladder`     | €6,200.04     | −€1,863.36       | 440        | 97.3%   | yes    | €68.72     | 60               |
| `strategies/bundling_cheaper` | €6,182.79     | −€1,880.61       | 430        | 96.5%   | yes    | €69.65     | 59               |
| `strategies/bundling_more`    | €6,173.59     | −€1,889.81       | 441        | 97.3%   | yes    | €65.33     | 227              |
| `strategies/baseline`         | −€72,612.51   | +€80,675.91      | 949        | 45.5%   | no     | €125.23    | 0                |

The two bundling folders share their base: `strategies/price_ladder`. Against it, `bundling_more` chains 227 orders
instead of 60 and cuts fees per car from €68.72 to €65.33, and `bundling_cheaper` changes neither the number of chains
nor the margin. Both land within €26 of their base, which is noise on one seed; only `scarcity_cost` moved.
