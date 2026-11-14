# A price ladder per dealer

The price ladder of [`../price_ladder/`](../price_ladder/README.md) with one ladder position for each dealer, instead
of one shared position for the whole week: each dealer learns the price it accepts from us. Everything else is the
price-ladder system: the same shadow admission (`ShadowAdmission`, reused from `strategies/price_ladder`), the same
price war, outage and dealer trust, and the same desk loop. Issue #193.

| File          | What it holds                                                                   |
| ------------- | ------------------------------------------------------------------------------- |
| `dispatch.py` | A copy of the price-ladder `dispatch.py` that quotes with `DealerLadderPricing` |
| `pricing.py`  | `DealerLadderPricing`: the price ladder with one position per dealer            |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/dealer_ladder/dispatch.py --level 8 --seed spread-1                                  # a practice week
uv run python -m strategies.bench strategies/dealer_ladder/dispatch.py strategies/price_ladder/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`record.py`), with the policy `dealer-ladder` instead of `dispatch`, so
they form their own group in `out/spread.sqlite` and `summary.json`.

## The dealer's ladder

Like the price ladder, a dealer's position is a multiple of the list price, inside `[floor, ceiling]` (1.0 to 1.5 ×
list by default) and starting at the top of its range. A won quote raises that dealer's position and a lost quote
lowers it, by the same 1% up and 3% down steps, in logs so the price moves by a share of itself. The one change is the
state: only the quoting dealer's ladder moves. A dealer we have not quoted yet starts at the top.

The price war, the outage and dealer trust are the parent's. The war is detected on a world ladder that still moves on
every outcome, exactly as the shared price ladder moves it; the outage boost and the dealer trust multiply a dealer's
price as before. The war's 18:00 restore applies to the world ladder, so a dealer keeps the day's net move and climbs
back with its own wins.

`summary()` prints how many dealers the week quoted, the range of their positions, and how many sat at the floor or the
top.

## The sparsity

On the saved level-8 week of #182 (`spread-1`, world `w2f8e2db87df1cec68d67`) the 1,037 price requests fall on 40
dealers: mean 25.9 each, median 11, from 2 to 251, and 10 dealers with fewer than five requests all week. The busiest
dealer sees 251 requests, so its ladder moves a lot; the thin tail sits near its start price and behaves much like the
shared ladder. A dealer ladder is therefore between the shared ladder and the per-city one: it separates the few big
dealers and leaves the rest shared.

## Bench

Not run yet: the bench plays online, which needs the user's approval. Run it against
`strategies/price_ladder/dispatch.py` on the same seeds, and compare each week's margin and on-time share.
