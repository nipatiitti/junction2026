# A price ladder per city

The price ladder of [`../price_ladder/`](../price_ladder/README.md) with one ladder position for each pickup city,
instead of one shared position for the whole week: each town learns the price that wins there. Everything else is the
price-ladder system: the same shadow admission (`ShadowAdmission`, reused from `strategies/price_ladder`), the same
price war, outage and dealer trust, and the same desk loop. Issue #193.

| File          | What it holds                                                                 |
| ------------- | ----------------------------------------------------------------------------- |
| `dispatch.py` | A copy of the price-ladder `dispatch.py` that quotes with `CityLadderPricing` |
| `pricing.py`  | `CityLadderPricing`: the price ladder with one position per pickup city       |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/city_ladder/dispatch.py --level 8 --seed spread-1                                  # a practice week
uv run python -m strategies.bench strategies/city_ladder/dispatch.py strategies/price_ladder/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`record.py`), with the policy `city-ladder` instead of `dispatch`, so they
form their own group in `out/spread.sqlite` and `summary.json`.

## The city's ladder

Like the price ladder, a city's position is a multiple of the list price, inside `[floor, ceiling]` (1.0 to 1.5 × list
by default) and starting at the top of its range. A won quote raises the city's position and a lost quote lowers it, by
the same 1% up and 3% down steps, in logs so the price moves by a share of itself. The one change is the state: a
quote's city is its first pickup place, and only that city's ladder moves. A city we have not quoted yet starts at the
top.

The price war, the outage and dealer trust are the parent's. The war is detected on a world ladder that still moves on
every outcome, exactly as the shared price ladder moves it; the outage boost and the dealer trust multiply each city's
price as before. The war's 18:00 restore applies to the world ladder, so a city keeps the day's net move and climbs
back with its own wins.

`summary()` prints how many cities the week quoted, the range of their positions, and how many sat at the floor or the
top.

## The sparsity

On the saved level-8 week of #182 (`spread-1`, world `w2f8e2db87df1cec68d67`) the 1,037 price requests fall on 30
pickup cities: mean 34.6 each, median 17, from 1 to 187, and 8 cities with fewer than five requests all week. A city
sees enough quotes for its ladder to move, so it is a better base than a per-lane one (308 lanes, median two requests).
The sparsest cities still sit near their start price and behave much like the shared ladder.

## Bench

Not run yet: the bench plays online, which needs the user's approval. Run it against
`strategies/price_ladder/dispatch.py` on the same seeds, and compare each week's margin and on-time share.
