# Hazard-aware admission

A standalone system for the existing [`LeadCostAdmission`](../lead_cost/README.md), with the root `Desk`
around it. Issue #229. The `lead_cost` strategy itself is unchanged, as are the root and all other systems.

| File          | Class               | Builds on              | What it decides                              |
| ------------- | ------------------- | ---------------------- | -------------------------------------------- |
| `dispatch.py` | `Desk`              | the root `Desk`        | The system, swapping in the fitted admission |
| `__init__.py` | `LeadCostAdmission` | `strategies/lead_cost` | Re-exports the admission used by it          |

## Run it

From the repository root:

```sh
uv run strategies/hazard_admission/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/hazard_admission/dispatch.py dispatch.py --jobs 2
```

Its weeks are saved with the policy `hazard-admission`.

## The idea

Root admission charges every request roughly `typical fee x 1.15` in its expected margin, plus location and
timing adjustments. `LeadCostAdmission` instead uses a fitted cost table by hours to the last pickup and
hours to the car's ready time, so long-lead requests can be admitted at costs close to the typical fee while
urgent ones still carry a high expected fee. It also picks the option with the most expected margin.

The class has a checkout-local fitted table already committed in `strategies/lead_cost/admission.py`. It can
be re-measured on saved weeks with `uv run python -m strategies.lead_cost.fit`.

`LeadCostAdmission` also has the capacity defaults used on `headroom` (`capacity_per_driver = 0.20`,
`min_capacity = 2.0`), so this is a test of that strategy as a package, not a perfectly isolated test of its
lead-time cost table. Everything else remains the root dispatcher: pricing at the root multiplier, the root
fee schedule, offers and bundling.

The expected result to compare with the root system on the same seeds is the admission mix and expected cost,
not merely the overall margin: long-lead requests should be accepted at a lower expected driver cost than the
flat-factor model, without turning urgent requests into losses.
