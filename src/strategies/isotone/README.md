# isotone

Learns the win curve online and prices at its profit peak. For each context (trust bucket 0-2 / 3-9 / 10+ ×
delivery to the capital region or not) it keeps win and loss counts on a grid of normalised price multiples z
(1.00 to 2.20, step 0.05). Prices are normalised by the option ladder (same_day = 1.21 × next_day, next_day =
1.13 × within_3_days) over the request's within_3_days-equivalent list price, so all options share one curve. Every
request has a threshold, so a win at z counts as a win in every lower cell and a loss (at the cheapest option
quoted) as a loss in every higher one. Counts start from the trust-0 threshold quantiles weighted as `priorWeight`
observations and fade by `decay` per outcome. Each option takes the grid z maximising (z − cost) × win, with a
Thompson draw (one shared normal draw over the cells' Beta posteriors, made non-increasing).

Params: `gridLo` 1.0, `gridHi` 2.2, `gridStep` 0.05, `priorWeight` 25, `capitalScale` 0.88, `otherScale` 1.05,
`trustLift` 0.03, `trustMid` 3, `trustHigh` 10, `sameDayLadder` 1.21, `nextDayLadder` 1.13, `decay` 0.997,
`explore` 1, `costWeight` 1 (cost × this in the argmax; 0.85 lost margin on spread-1), `shade` 1, plus the base's.
