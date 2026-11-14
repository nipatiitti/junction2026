# gambit

Every dealer is a poker opponent with a private threshold level (a multiple of list price, in within_3_days terms at
trust 0) that drifts. gambit keeps a Bayesian filter per dealer: a log-spaced grid of levels with weights. A win at
ratio r reweights each level by the chance it accepts r (log-normal scatter `noise`), a loss by the chance it refuses
the cheapest option offered. Each morning the belief diffuses (`drift`), and a dealer we mostly won from yesterday is
shifted down `undercutSteps` (the competitor undercuts them). New dealers start from the pooled belief of all dealers.
Each option is priced at the ratio maximising (price - cost + `winBonus` x list) x P(accept), with the option ladder
(`nextDay` 1.13, `sameDay` 1.367 over within_3_days) and `trustStep` per trust point. Then a bluff: with probability
`bluff` + `bluffShare` x dealer share (capped `bluffMax`) the quote goes one or two `bluffStep` higher, to probe.

Params: gridLow/gridHigh/gridStep, priorMid, priorSd, noise, learn, drift, undercutWins, undercutSteps, nextDay,
sameDay, trustStep, winBonus, bluff, bluffShare, bluffMax, bluffStep, priceLow/priceHigh/priceStep.
