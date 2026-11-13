# More chains

A folder that builds on [`strategies/price_ladder`](../price_ladder/README.md), as
[`../scarcity_cost/`](../scarcity_cost/README.md) does: its own copy of that dispatcher with a bundler whose orders
all wait for a chain. Issue #160. The root `dispatch.py` and `strategies/bundling` stay as they are.

| File          | What it holds                                                                                   |
| ------------- | ----------------------------------------------------------------------------------------------- |
| `dispatch.py` | A copy of `strategies/price_ladder`'s dispatcher that bundles with the strategy below           |
| `bundling.py` | `WaitingBundler`: the bundling of `strategies/bundling`, with the wait and thresholds opened up |

## Run it

From the repository root:

```sh
uv run strategies/bundling_more/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/bundling_more/dispatch.py strategies/price_ladder/dispatch.py --jobs 4
```

Its weeks are saved under the policy `bundling-more`.

## What it changes

Bundling works but hardly fires: at level 8, **829 of ~12,500 paid cars** go in a bundle (6.6%), and the bench has it
within noise of main. Bundled cars cost **€38–54 each against €79.6 for a single**, so every car moved into a chain is
worth €25–40.

The bundling README says why it is rare: *"without the wait, a week has only 2 to 5 [bundles]"*, because only the
orders of a batch wait for a chain. Here:

- **every order waits** (`hold`, 60 minutes), not only a batch's — a non-batch order goes when its hold is over,
  where the base sends it at once;
- a car joins a chain for a smaller saving (`min_saving` 10 → 5 driver-minutes);
- a chain carries one more car (`max_cars` 3 → 4), still inside the rules' 12 hours and the base's own 8-hour cap.

The window, buffer and lead checks and the audience match are the base's, so a bundle never shrinks the drivers who
could take a car, and the on-time risk stays contained.

## Risk

The 187 bundles the base found are the best opportunities, so five times as many will include worse ones, and a
waiting order loses time to find a driver. That is what the bench has to show.

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
