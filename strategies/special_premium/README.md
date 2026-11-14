# Special-delivery premiums

The delivery-urgency system ([`../delivery_urgency/`](../delivery_urgency/README.md)) with a premium for each thing
that makes a request special. A premium car needs an experienced driver, and a manual car needs a manual licence:
today those only narrow the audience and tighten the admission's supply. Here each requirement **multiplies the quote
and the driver fee by `1 + SPECIAL_SHARE`** (5%), compounding, so both the dealer and the driver pay and gain more for
the harder request. Issue #231.

Same shadow admission, price war, outage, dealer trust and desk loop as the delivery-urgency system.

| File           | What it holds                                                                  |
| -------------- | ------------------------------------------------------------------------------ |
| `dispatch.py`  | A copy of the delivery-urgency `dispatch.py` with the three classes below      |
| `specials.py`  | `SPECIAL_SHARE = 0.05` and `factor(request, notes) = (1 + SPECIAL_SHARE) ** n` |
| `admission.py` | `SpecialAdmission`: expected driver cost, times the factor                     |
| `pricing.py`   | `SpecialPricing`: the urgency quote's multiplier, times the factor             |
| `fees.py`      | `SpecialFeePlanner`: the gig's typical fee, times the factor                   |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/special_premium/dispatch.py --level 8 --seed spread-1                              # a practice week
uv run python -m strategies.bench strategies/special_premium/dispatch.py strategies/delivery_urgency/dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`record.py`), with the policy `special-premium` instead of `dispatch`, so
they form their own group in `out/spread.sqlite` and `summary.json`.

## The factor

`n` counts the request's special requirements, from `specials.count`:

- **experienced** — any car with `car.premium`; only experienced drivers may take it (the €150-a-car fine);
- **manual** — `NoteReader.read(request).manual`: the note says it is a manual gearbox.

Then `factor = (1 + SPECIAL_SHARE) ** n`, so 1.0, 1.05, 1.1025 for none, one or two requirements. If more requirement
kinds (plates, charging, private address) are ever wanted, add them to `specials.count`; the compounding stays.

The factor applies at every level above 3. Up to level 3, where every quote wins, the quote's `multiplier` is left
alone.

## Where it lands

- **Quote:** `SpecialPricing.multiplier` multiplies the ladder's factor by `factor`. Every dispatcher sets
  `admission.params.price_factor = pricing.multiplier(request, now)`, so the **same** factor reaches the admission's
  margin check; then `UrgencyPricing.price` multiplies by the urgency ratio, so the premium sits on top of the urgency
  premiums, as intended.
- **Expected cost:** `SpecialAdmission.expected_cost` multiplies the base's cost by `factor`, so the admission budgets
  the higher driver fee rather than counting it as margin.
- **Driver fee:** `SpecialFeePlanner.typical` multiplies the typical fee by `factor`, which scales the whole
  opening/raise/top schedule and the bundle's units. This is the part that really pays the driver more; the
  price-plus-penalty ceiling still caps it.

Since both the quote and the fee scale by the same factor, the admission's _relative_ margin stays as before. The euro
margin per won order rises because the quote is bigger than the fee: 5% of the price is a larger number than 5% of the
fee. The cost is that the higher quote wins fewer requests; measure with the bench, not by reasoning.

| Variable        | File          | Default | What it does                                         |
| --------------- | ------------- | ------- | ---------------------------------------------------- |
| `SPECIAL_SHARE` | `specials.py` | 0.05    | The share each special requirement adds, compounding |

## Bench

Not run yet: the bench plays online, which needs the user's approval. Run it against
`strategies/delivery_urgency/dispatch.py` on the same seeds, and compare the margin, orders won and on-time share, and
the driver fee paid.
