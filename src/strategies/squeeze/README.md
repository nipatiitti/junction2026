# squeeze

Trust is the largest price lever, so the price is one curve over the dealer's trust and size. A big dealer
(`dealerShare` at least `bigShare`, or anyone during the first `warmup` requests) gets cheap, safe quotes while their
trust is low (`lo` × list), so they reach high trust fast; then the price climbs a logistic in trust (centre `mid`,
width `width`) to `hi`, far above 1% per order. From weekday `lateDay` on, investing has no future, so the floor is
`loLate`. A small dealer never builds trust in a week, so pays `small` × list from the first request (plus
`smallTrustStep` per trust point). Options scale by `nextDay` and `sameDay` over within_3_days; deliveries into the
capital region pay `capital` × the price. Everything else comes from the base.

Params: `bigShare` 0.05, `warmup` 30, `lo` 1.16, `hi` 1.72, `mid` 8, `width` 3, `lateDay` 3, `loLate` 1.28,
`small` 1.46, `smallTrustStep` 0.01, `nextDay` 1.04, `sameDay` 1.09, `capital` 0.9.
