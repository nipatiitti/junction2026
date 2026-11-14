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

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), 553 to 608 requests a week have a value, €16 to
€28 on average. Admission takes 70.7% of the requests against 65.4%, and keeps 1,323 of ceiling's 1,327 won orders
(98.6% on time), for €30,293 against €30,465.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy
`trust-value`.

| Seed       |  `ceiling` | `trust_value` | Difference | On time |
| ---------- | ---------: | ------------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |     €8,995.51 |   −€835.58 |   97.9% |
| `spread-2` |  €6,673.95 |     €5,642.00 | −€1,031.95 |   98.4% |
| `spread-3` |  €4,312.02 |     €2,449.57 | −€1,862.45 |   97.3% |
| Total      | €20,817.06 |    €17,087.08 | −€3,729.98 |         |

Behind ceiling on all three seeds, by €3,729.98 in total: the furthest behind of the seven. It won 1,083 orders against
952, but the 876 orders that both won made €3,353 less, because the trust value lowers ceiling's price floor as well as
its margin check (1.335 × the list price against 1.373). 150 of its orders lost money (€6,483 together) against 102 for
ceiling (€3,316), and late refunds rose from €407 to €1,017 as the extra cars kept the drivers busy. Within the week,
the trust that the extra orders bought did not pay for the thinner prices.
