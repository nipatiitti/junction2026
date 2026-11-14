# thompson

Pricing as a contextual bandit. Arms are multiples of the list price on a grid (`gridLo`..`gridHi` by `gridStep`).
A context is the dealer's trust bucket (our own count of on-time orders: `<trustMid`, `<trustHigh`, more) x the option
x whether the delivery goes to the capital region. Each arm keeps a Beta posterior of its win chance, with a prior of
`priorN` pseudo-observations from the measured flip quantiles (src/BRIEF.md), scaled by region, option and trust.
A request answers with a threshold, so a win at m adds a win to every arm at or under m and a loss adds a loss to every
arm at or over m. Each night the observations keep `dayDecay` of their weight. For each option we can serve on time
(`canServe`), the arm is chosen by Thompson sampling of (price - cost) x win chance with a seeded generator (`seed`
and the request id), and the best option is quoted alone; below `minValueCents` expected margin, or with under `minSlack` minutes of slack, we decline.
Cost = `costMult` x typical fee (x `premiumCost` for premium cars). Gigs use the starter's stops; the fee opens at
`feeOpen` x typical and rises linearly to `feeTop` over `feeSteps` steps of `feeStepMinutes` (reposts and retries
open at `repostOpen`, premium x `premiumFee`); after the deadline warning the starter's steep fees apply.

Params: `seed, gridLo, gridHi, gridStep, priorN, capitalScale, otherScale, sameDayScale, nextDayScale, threeDayScale,
trustSlope, trustCap, trustMid, trustHigh, dayDecay, costMult, premiumCost, minValueCents, minSlack, feeOpen, feeTop, feeSteps,
feeStepMinutes, repostOpen, premiumFee`.
