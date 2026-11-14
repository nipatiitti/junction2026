# Scarcity-priced urgency

A folder that builds on the shared strategies, the way [`../delivery_urgency/`](../delivery_urgency/README.md) and
[`../scarcity_cost/`](../scarcity_cost/README.md) do: its own copy of the dispatcher and one new `Strategy`. The root
`dispatch.py` and the strategies it builds stay as they are. Issue #172.

| File           | What it holds                                                                                         |
| -------------- | ----------------------------------------------------------------------------------------------------- |
| `dispatch.py`  | A copy of the root `dispatch.py` that quotes and admits with the strategies below                     |
| `admission.py` | `ScarcityUrgencyAdmission`: the urgency admission plus the town's scarcity, without the capacity gate |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/scarcity_urgency/dispatch.py --level 8 --seed spread-1                        # a practice week
uv run python -m strategies.bench strategies/scarcity_urgency/dispatch.py dispatch.py --jobs 4 # against the root system
```

Its weeks are saved under the policy `scarcity-urgency`.

## What it combines

On seed `spread-1` at level 8, one practice week each, two folders made a small change with a real gain:

| folder                        | its change                                                                                            | result                                 |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `strategies/scarcity_cost`    | the town's quotas per driver priced into the expected cost, and the capacity gate dropped             | **+€821** over `dispatch.py`           |
| `strategies/delivery_urgency` | the ladder's multiple set on the request's longest option, each faster option a fixed premium over it | **+€924** over its base `price_ladder` |

One changes the cost and the other the quote, so this folder has both:

- **the quote** is `UrgencyPricing` from `strategies/delivery_urgency`, unchanged. The desk builds one `Schedule` and
  gives it to both strategies, so its two premiums stay the one place to tune;
- **the admission** is `ScarcityUrgencyAdmission`: the urgency-checked profit check, plus
  `risk(pickup) = min(cap, safety × quotas per driver a day)` on the expected fee, with the capacity gate gone. A
  contested town has to be paid for rather than refused, and the town's quotas count the whole market's demand, which
  our own waiting cars cannot see.

## The base is the thing to watch

The urgency quote is defined on the ladder's anchor, so this folder sits on `strategies/price_ladder`, not on the
root's adaptive pricing that `scarcity_cost` uses. On `spread-1` the ladder family ran €0.9k–€1.9k behind the root, so
the ladder base may cost the combination more than the scarcity change gains. That is the first thing the bench has to
answer, so **it has not been played yet**.

## Ablation

`Params(gate=True)` puts the capacity gate back and `Params(safety=0)` removes the scarcity term, so one folder can
bench each change on its own. `Params(safety=0, gate=True)` is `strategies/delivery_urgency`: the same expected cost
for the same request (checked offline), the same gate, and the same quote.

The shadow price of `strategies/price_ladder` is kept, so the combination carries two capacity terms: the shadow on
the area's own waiting cars and the scarcity risk on the town's quotas. They measure different things — our load
against the market's demand — but they overlap, and the bench may show one should go.
