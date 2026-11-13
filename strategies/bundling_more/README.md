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
