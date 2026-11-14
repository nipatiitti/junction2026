# surge

Driver capacity is the scarce good, so `surge` prices it like ride-hailing surge pricing at closing time on a rainy
Friday. Utilisation `u = load / capacity` (open gigs plus pending quotes for the option's pickup day) sets a smooth
multiple `exp(surgeK × (u − target))`, clamped to `[idleFloor, surgeCap]`: idle days sell a little under the base to
fill drivers, busy days climb steadily, so capacity stays nearly full of the best-paying orders. The hard brake is
pushed out of the way (`maxOpenPerDay` 40, `brakeMarkup` 1.25 instead of declining) and is only a backstop. The late
share adds its own surge (`× (1 + lateK × lateShare)`): when deliveries slip, we sell less and dearer. Tight orders
(little slack) carry up to `tightPremium` because they cost more to serve safely; orders with days of slack lose up to
`slackDiscountMax`. A trust premium of `trustStep` per trust point follows the ~1% threshold rise per on-time order.

| Param                                | Default            | Why                                                                                                              |
| ------------------------------------ | ------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `sameDay` / `nextDay` / `within3`    | 1.42 / 1.36 / 1.30 | Neutral multiples near `flat`, low enough to build trust early; the option ratios follow the dealers' thresholds |
| `capacity`                           | 12                 | Open load per day where `u = 1`; week 1 peaked at 14.6 at 98% on time                                            |
| `target`                             | 0.5                | Surge is ×1 at half capacity                                                                                     |
| `surgeK`                             | 0.35               | At `u = 1.5` the multiple is ×1.42; at idle ×0.85                                                                |
| `idleFloor` / `surgeCap`             | 0.85 / 1.5         | Never sell under 0.85 × base, never surge beyond 1.5 ×                                                           |
| `lateK`                              | 3                  | A 5% late share adds 15%                                                                                         |
| `tightPremium` / `tightHours`        | 0.08 / 12          | +8% at zero slack, about +3% at 12 h                                                                             |
| `slackDiscount` / `slackDiscountMax` | 0.02 / 0.05        | −2% per day of slack past the first, at most −5%                                                                 |
| `trustStep`                          | 0.016              | +40% at full trust 25; 1.4 × list wins 46% at trust 0 and 95% at trust 15                                        |
| `maxOpenPerDay` / `brakeMarkup`      | 40 / 1.25          | Backstop brake only                                                                                              |
