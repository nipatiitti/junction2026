# Pair-first admission

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Admission takes a request more readily
when its cars can continue on a transport we already hold, pricing a possible chain saving into the accept decision.
Issue #241. Headroom and the systems it builds on stay as they are.

| File           | Class                | Builds on           | What it decides                                     |
| -------------- | -------------------- | ------------------- | --------------------------------------------------- |
| `admission.py` | `PairFirstAdmission` | `LaneCostAdmission` | Which requests to take, preferring a possible chain |
| `dispatch.py`  | `Desk`               | the headroom desk   | The system: headroom with the admission above       |

`PairFirstAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through
`LaneCostAdmission`, `LeadCostAdmission` and `ChainAdmission`, with the constructor
`(roster, world_map, level=8, params=None, lane=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/pair_first/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `pair-first`. No online measurement was done for this version.

## The strategy

For each request, `ChainAdmission.chain` looks for one of our undelivered orders whose last delivery is within
`near` road minutes of the request's pickup (30 minutes by default). Its driver must be able to reach that pickup
within the usual return-leg timing limits: no more than `wait` before the car is ready, inside its pickup window, and
with time to deliver by the earliest deadline less `spare`. A premium request still needs a premium partner.

Unlike ceiling's return leg, the request's last delivery need not be near the partner's first pickup (`back` is
unbounded). A pair is a possible continuation of the same gig, not necessarily a drive back towards home.

When a partner exists:

1. **The expected driver cost falls by `chain_discount`.** The default 0.15 takes 15% off the usual headroom cost.
   This replaces headroom's return-leg multiplier rather than stacking with it, so the lower cost affects both the
   option choice and whether admission accepts the request.
2. **The request takes `pair_weight` of an area-capacity place.** The default 0.5 is half a place, the same as the
   base return leg, instead of a whole new-driver place.

`ChainAdmission` still owns the claims. An accepted request claims its partner at most once; other requests cannot
claim that transport while the request is pending or its won order remains undelivered. The existing desk `release`
and admission `restore` paths handle a decline and a restart unchanged, and a lost request stops holding its claim
under the base claim-expiry rule.

With no partner, admission, its option choice and every other strategy behave exactly as headroom. Pricing, fees and
bundling are unchanged.

The variables are in `Params`, exported as `PairFirstParams`, next to headroom's inherited admission thresholds.

| Variable         | Default   | What it does                                                      |
| ---------------- | --------- | ----------------------------------------------------------------- |
| `near`           | 30 min    | The most road minutes from the partner's last delivery to pickup  |
| `chain_discount` | 0.15      | The fraction removed from a paired request's expected driver cost |
| `pair_weight`    | 0.5       | The area-capacity places a paired request uses                    |
| `back`           | unbounded | No return-to-start constraint for a pair                          |

The saving is an assumption until bundled drivers really take these cars. Admission may accept a pair at a lower
expected cost, but this system does not change bundling or guarantee that a driver will combine the orders.
