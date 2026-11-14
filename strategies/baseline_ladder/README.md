# Baseline with a price ladder

The [baseline](../baseline/README.md) with two changes: its quotes and its driver fees. The baseline quotes the list
price and posts at the typical fee; this system quotes one shared multiple of the list price that follows our wins
and losses, and pays drivers on a ramp from half the typical fee to 2.5 times it. Admission, the note reader, the retry,
the desk and the play loop are the baseline's own code, imported and not copied.

| File                 | What it holds                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------ |
| `baseline_ladder.py` | The runner: the baseline's desk and loop, with the two strategies below in the baseline's  |
| `pricing.py`         | `BaselineLadderPricing`: the list price of each quoted option, times the ladder's multiple |
| `fees.py`            | `RampFees`: the fee of each gig, rising with the clock                                     |

## The quotes

The ladder is one multiple of the list price, shared by every request of the week:

- It starts at 1.49 × list, its ceiling.
- Every quote we lose (`order_lost`) lowers it by 0.03: 1.49 → 1.46.
- Every quote we win (`order_won`) raises it by 0.01, up to 1.49 again: 1.46 → 1.47.

The unequal steps settle it where about three quotes in four win: three wins undo one loss. Up to level 3 every
quote wins, so it stays at 1.49.

Three rules then apply to each quote:

- **No driver left.** Each city has an audience: the drivers who live there. Every request takes one driver off for
  the day, whether we win the quote or not: from its pickup city, or, when that has none left, from the nearest
  neighbouring city that has. A neighbour is a city whose drivers reach the pickup in 60 road minutes. At midnight
  every city has all its drivers again. A request that finds no driver left in any of them is quoted at 3 × list
  instead of the ladder's multiple, so that we take few orders that nobody can drive. For a premium car only the
  experienced drivers count (rating at least 4.8 and at least 50 completed gigs), as the baseline posts it; a request
  does not say whether a car is manual, so the licence does not count. The outcome of such a quote does not move the
  ladder, and a line is printed when we win one: `Won at 3 x list: order … from …`.
- **Same day.** A `same_day` option is quoted 8% higher, so up to 1.49 × 1.08 = 1.61 × list.
- **Floor.** No quote is under the request's typical fee (`referenceFeeCents`) plus one cent.

`Params` in `pricing.py` holds the ceiling, the two steps, the multiple of 3, the 60 minutes, the 8% and the cent.
Its `refill_daily=False` counts the requests over the whole week instead of each day.

## The fees

`RampFees` pays each order on one line, as a share of its typical fee:

- 0.5 × the typical fee when the order is won;
- rising evenly with the clock to 2.5 × the typical fee, 6 hours before the order's delivery deadline;
- sooner when the order's last on-time pickup (`lastPickupAt`) comes first: 2.5 × is then reached 1 hour before it,
  since a driver who books later cannot deliver on time;
- an order won with less time than that still starts at 0.5 ×, and rises to 2.5 × in its first hour;
- 2.5 × from then on. The deadline warning changes nothing: no fee passes 2.5 ×.

A driver books at the fee the line has reached. A gig's schedule holds the line from the minute it is posted, in up
to 48 steps at least 5 minutes apart. A gig posted again, after a failed visit or an ended window, goes on at the fee
the line has reached. Level 1 takes one fee only, the line's fee at the post. `Params` in `fees.py` holds the two
shares, the 6 hours, the two single hours and the 5 minutes.

## Run it

From the repository root, like the baseline:

```sh
uv run --env-file .env python strategies/baseline_ladder/baseline_ladder.py --level 8 --seed spread-1
```

The week ends with a line on the ladder: its last multiple, the quotes won and lost, and the requests quoted at 3 ×
with how many of them we won. Against the baseline on the same seeds:

```sh
uv run --env-file .env python -m strategies.bench strategies/baseline_ladder/baseline_ladder.py strategies/baseline/baseline.py
```

Its weeks are saved like every online run (`record.py`), with the policy `baseline-ladder`, so they form their own
group in `out/spread.sqlite`.
