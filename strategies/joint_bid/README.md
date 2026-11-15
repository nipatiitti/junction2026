# Joint quote and fee pricing

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Admission estimates a driver cost to choose
requests, while the fee planner separately builds the schedule posted after a win. This system makes the quote use the
schedule's expected paid fee too, so the two prices are sides of one decision. Headroom and its desk stay unchanged.

| File          | Class             | Builds on         | What it decides                                     |
| ------------- | ----------------- | ----------------- | --------------------------------------------------- |
| `pricing.py`  | `JointPricing`    | `HeadroomPricing` | The quote, with the schedule's expected fee as cost |
| `fees.py`     | `JointFeePlanner` | `LaneFeePlanner`  | A pure preview of the schedule the desk would post  |
| `dispatch.py` | `Desk`            | the headroom desk | Wiring the fee preview into each quote              |

## Run it

From the repository root:

```sh
uv run strategies/joint_bid/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `joint-bid`.

## The joint estimate

After admission accepts an option, the desk asks `JointFeePlanner.preview` for the complete fee schedule: its opening
fee, top fee and every step between them. `JointPricing` uses only the two ends to estimate what the schedule pays:

```text
expected fee = opening + expected_step x (top - opening)
```

`expected_step` is 0.5 by default in the frozen pricing `Params`: halfway between the opening and top fees. Zero
expects every gig to book at its opening fee; one expects every gig to reach its top. This expected fee replaces
admission's generic estimate as the `cost` passed to headroom pricing, which applies its usual risk premium to it.

The learned price, moving ceiling maximum, dealer trust and outage lifts, price-war behaviour, and decline when the
cost floor is above the lifted maximum are all inherited unchanged.

## Preview and fallback

The preview constructs a would-be solo order containing all the request's cars. It uses admission's last-pickup
estimate for the selected option and values the order at that option's current lifted ceiling, because the final quote
does not exist yet. It then calls the same pure `dawn_plan` function as a real post. It neither posts nor reprices a
gig, and it does not increment the planner's schedule counts.

If there is no uniquely selected option, no cars, or no schedule, there is no fee estimate. Pricing then uses
admission's original cost estimate, exactly as headroom does.

The joint estimate assumes the previewed schedule does not change between quote and post. The eventual posting still
uses the real order and the planner's normal `schedule` method; a later bundle, change of plan or reprice is outside
the quote-time estimate.
