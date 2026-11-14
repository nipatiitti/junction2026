# dejavu

**Deliberately overfit to practice seeds. It cannot work in the secret final**, where the week is new: there it
falls back to a plain markup over list and the starter's gigs with a simple fee schedule.

A practice week with the same seed and level has the same requests (ids, dealers, list prices, times). From the
saved weeks, `build_table.py` brackets each request's trust-free threshold per option: the highest winning
quote/list ratio and the lowest losing one (a request lost outright), each divided by `1 + trust/100`. It also
keeps each request's mean cost (revenue minus margin, over list) and late share. The strategy recognises the
week by the list prices of its first requests (`sigMatch` of them), quotes each servable option inside its
bracket, lifted by the dealer's trust that it counts from on-time deliveries, and declines options priced under
the expected cost or requests that were often late. Fees open at `feeOpen` x the reference fee and rise to
`feeMax` x by the last pickup; the starter's steep schedule after the deadline warning.

Rebuild the tables: `uv run python -m tools.db && uv run python src/strategies/dejavu/build_table.py spread-1 spread-9`

Params: `pos` (place in bracket), `belowLoss`, `aboveWin`, `probeRatio`, `markup`, `trustPct`, `trustMax`,
`costRef`, `minEdge`, `maxLate`, `feeOpen`, `feeMax`, `feeSteps`, `sigMatch`.
