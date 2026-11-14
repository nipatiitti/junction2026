# Trust as value

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk whose admission counts the dealer trust that an order on time buys. Issue #187. Ceiling and the root system stay
as they are.

| File           | Class                 | Builds on        | What it decides                                         |
| -------------- | --------------------- | ---------------- | ------------------------------------------------------- |
| `admission.py` | `TrustValueAdmission` | `ChainAdmission` | Which requests to take, with the trust they buy valued  |
| `dispatch.py`  | `Desk`                | the ceiling desk | The system: points admission at ceiling pricing's trust |

## Run it

From the repository root:

```sh
uv run strategies/trust_value/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/trust_value/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `trust-value`. Its admission line adds how many requests had a trust value, and
the mean value.

## The strategy

At level 8 each order that a dealer gets on time from us makes it accept 1% more from us, up to 25 orders, and ceiling
pricing lifts its prices for that dealer by the same. So an order is worth its margin plus 1% of what that dealer will
still pay us this week. Ceiling admission sees only the margin.

1. **The value of one more order on time**, in cents:
   `trust_step × requests still to come × the dealer's share of our quotes × its price × on_time`.
   - The requests still to come: the dealer's requests so far per open minute (08:00–18:00, Monday to Friday, at least
     `observed` = 4 hours), times the open minutes left after the car arrives, about `arrival` = 12 hours from now.
   - The dealer's share: our quotes it took, of those we priced, shrunk to the world's share with `win_prior` = 4.
   - Its price: the mean first list price of its requests × `markup` = 1.35. `trust_step` = 1%, `on_time` = 0.97.
2. **The net cost.** Admission takes the value off the driver cost, at most `value_cap` = 30% of it. Ceiling's margin
   check and its price floor both use the net cost, so a busy dealer's car is taken, and priced, at a thinner margin
   while the week has time to cash the trust in. A dealer at 25 orders, or the end of the week, has no value left.

It differs from `strategies/ratchet`'s trust admission, which lets a dealer below a trust cap take a small loss: here
the value comes from the dealer's own requests in the week, and is worth most for a busy dealer early in the week.

## Offline replay

`analysis.replay`'s quote replay with this desk on the ten distinct saved `ceiling` weeks. 546 to 596 requests a week
have a value, €19 to €34 on average. Admission takes 70.8% of the requests against 65.5% for
ceiling. Of the orders that the weeks won, it keeps 3,226 of ceiling's 3,233, with the same on-time share (97.9%), and
a margin of €65,647 against €65,680. The requests it takes in addition were not won in those weeks; the bench below
measures them.

## Bench

To be played.
