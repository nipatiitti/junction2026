# Baseline with a fixed quote and fee tiers

The [baseline](../baseline/README.md) with two changes, to work on the share of orders on time level by level: a
fixed quote multiple, and driver fees in tiers by who may drive the car. Admission, the note reader, the retry, the
desk and the play loop are the baseline's own code, imported and not copied.

| File                | What it holds                                                                         |
| ------------------- | ------------------------------------------------------------------------------------- |
| `baseline_tiers.py` | The runner: the baseline's desk, with the two strategies below, and the practice loop |
| `pricing.py`        | `FixedMultiplePricing`: 1.2 × the list price of each quoted option                    |
| `fees.py`           | `TierFees`: the fee of each gig, by its tier and the clock                            |

## The quotes

Every quote is 1.2 × the list price of the request's first option. Up to level 3 the dealer ignores the price: every
quote wins at the list price, so the multiple counts from level 4 on. `Params` in `pricing.py` holds it.

## The fees

Each order's fee is a share of its typical fee (`referenceFeeCents`), by its tier:

| Tier        | Which gig                                 | When won | Rises to | Top  |
| ----------- | ----------------------------------------- | -------- | -------- | ---- |
| Anyone      | Every driver may take it                  | 0.8      | 1.3      | 1.3  |
| Manual      | A manual car: a manual licence is needed  | 1.0      | 1.25     | 1.25 |
| Experienced | A premium car: an experienced driver only | 1.0      | 1.3      | 1.3  |

- **The rise.** The fee rises evenly from the first share to the second, in the first half of the time to the top.
- **The top.** A gig that is still open is at its top fee 2 hours after the order is won, or halfway to the order's
  last on-time pickup (`lastPickupAt`) when that comes first.
- **Back to the first fee.** From 4 hours before the order's last on-time pickup, the fee is the first share again. A
  fee schedule cannot fall, so the desk reprices the order's open gigs at that minute, and the practice loop stops
  the clock for it.
- **The deadline warning.** From an order's deadline warning on, its open gigs go at the baseline's steep fees
  instead, and the fee no longer falls back: 1.5 × the typical fee at once, then a quarter of it more every half
  hour, up to 2.5 ×. The warning comes 3 hours before `lastPickupAt`, an hour after the fee fell back. An order won
  less than 4 hours before `lastPickupAt` stays at its first fee until the warning.
- **Manual cars.** A car is manual when its note says so (the reader of [`../notes/`](../notes/README.md)) or a
  visit failed for the licence. Its gig then goes to drivers with a manual licence from the first post, where the
  baseline learns it from the failed visit only. A premium manual car is in the experienced tier.

Before the warning the fee depends on the minute only, so a gig posted again, after a failed visit or an ended
window, goes on at the fee the line has reached. Level 1 takes one fee only, the line's fee at the post. `Params` in
`fees.py` holds the three tiers, the 2 hours, the two halves and the 4 hours.

## Run it

From the repository root, like the baseline:

```sh
uv run --env-file .env python strategies/baseline_tiers/baseline_tiers.py --level 2 --seed spread-1
```

Against the baseline on the same seeds:

```sh
uv run --env-file .env python -m strategies.bench strategies/baseline_tiers/baseline_tiers.py strategies/baseline/baseline.py
```

Its weeks are saved like every online run (`record.py`), with the policy `baseline-tiers`, so they form their own
group in `out/spread.sqlite`.
