# Urgency pricing

A folder that builds on the shared strategies, the way [`../baseline/`](../baseline/README.md) and
[`../price_ladder/`](../price_ladder/README.md) do: its own copy of the dispatcher and subclasses of the ladder and
its shadow admission, so the root `dispatch.py` and `strategies/price_ladder` stay as they are. Issue #153.

| File           | What it holds                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------- |
| `dispatch.py`  | A copy of the root `dispatch.py` that quotes and admits with the two strategies below                   |
| `pricing.py`   | `UrgencyPricing`: the ladder of `strategies/price_ladder`, with each option priced by its kind          |
| `admission.py` | `UrgencyAdmission`: the shadow admission of `strategies/price_ladder`, checking the kind-adjusted price |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/delivery_urgency/dispatch.py --level 8 --seed spread-1                        # a practice week
uv run python -m strategies.bench strategies/delivery_urgency/dispatch.py dispatch.py --jobs 4 # against the root system
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `delivery-urgency` instead of
`dispatch`, so they form their own group in `out/spread.sqlite`.

## The schedule

`UrgencyPricing` is `LadderPricing` with a different quote. The ladder still holds one multiple of the list price for
the whole week, but that multiple applies to the **anchor**, the longest option the request offers, and the other
options are derived from it. The options then keep a fixed relationship:

| option          | price                                               |
| --------------- | --------------------------------------------------- |
| `within_3_days` | the anchor: the ladder's multiple of its list price |
| `next_day`      | `1 + next_day_premium` times the anchor             |
| `same_day`      | `1 + same_day_premium` times the next day           |

With the defaults, next day is 2% more than within three days and same day is 8% more than next day, 10.16% more than
within three days. The two numbers are the fields of `Schedule`; the desk builds one and gives it to both strategies,
so it is the one place to tune.

A request without a `within_3_days` option is anchored on its longest option, so a `same_day + next_day` request still
quotes same day 8% over next day. A request with a single option, and every quote up to level 3, is priced as the base.

`UrgencyAdmission` overrides `assess` so its profit check uses the kind-adjusted price of the option it picks, rather
than the option's own list price times the ladder's multiple. A faster option is quoted higher, so it must clear the
cost at that higher price. The shadow price and the rest of the assessment are the base's.

## Why the anchor, not each list price

The world's list prices already differ by kind: a faster option's list price is higher. Multiplying each option's own
list price by a kind factor would compound with that difference. Anchoring on one option and deriving the rest sets
the ratios exactly, which is what this system tests.
