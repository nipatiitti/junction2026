# cherry

A fruit picker who takes only the ripest. Each request gets an expected driver cost (typical fee x a cost score:
private pickup/delivery, trade-in, premium, weekend, Friday, and the drivers living within `nearMinutes` of pickup
and delivery against the median place) and an expected flip price (option median over list x capital/other region
factor x the dealer's trust from on-time deliveries). Each serveable option (`canServe`) is priced at the grid price
maximising (price - cost) x P(win) under a log-normal flip; the best option is quoted, slower serveable options no
lower than it, so the dealer pays for speed. Thin requests (`minEv`, `minMargin`) are declined. Fees open at
`feeOpen` x typical x cost score and rise (curve `feeCurve`) to `feeTop` over up to `feeHorizonH` hours; reposts and
urgent reprices start from the last fee and climb to `feeUrgent`.

Params: `flipSame/flipNext/flipThree`, `capitalFactor/otherFactor/capital`, `flipSd`, `trustStep/trustCap`,
`costBase` and the feature multipliers, `supplyPow/Min/Max`, `tightRisk/tightSlackH`, `minEv/minMargin`,
`gridLo/gridHi`, `ladderFloor`, `feeOpen/feeTop/feeUrgent/feeRepost/feeSteps/feeCurve/feeHorizonH`.
