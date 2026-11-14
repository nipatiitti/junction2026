# steady

Tests the trust hypothesis: a quote held near 1.4 × list while a dealer's trust grows should win more orders at the
same margin per order, instead of drifting to a higher price and half the wins.

- One multiple of list per option (`sameDay` 1.40, `nextDay` 1.30, `within3` 1.22; lowered by 0.1 after winning 12-29% on spread-6 and spread-8), times `1 + trustStep × trust`
  (`trustStep` 0: flat), times `1 - mondayDiscount` on Mondays (0.08: Monday won 21% on spread-8). Never under cost × `minMargin` (base).
- Every option the base admits is quoted; the dealer takes the fastest it accepts.
- Big dealers (at least `bigShare` 0.05 of the requests, after 20): options with under `bigComfort` 12 hours of slack
  are left out, and their gigs open at `bigFee` 1.1 × the base's opening fee (never stepping below it).
- Capacity: the base's brake defaults.

The summary line adds the win rate and the mean trust of the quoted dealers for each weekday.

```sh
node --env-file=.env src/bench.ts steady --level 8 --seeds spread-8
```
