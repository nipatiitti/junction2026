# shadow

Tails the competitor and prices just under it. A dealer accepts when our quote is under the competitor's price for
it, so each win says the competitor's flip was above our price and each loss says it was below.

- A grid filter (121 levels of price / list) holds today's competitor level; each win or loss multiplies it by the
  chance of that answer, with a log-normal request scatter (`scatter`).
- Each morning the belief drifts (`widen`), mixes in the prior (`reset`), and dealers we mostly won yesterday get
  a cut (`undercut`), since the competitor undercuts them.
- Offsets: capital-region deliveries (`capitalMult`) vs other towns (`otherMult`), a daily per-place offset learned
  from residuals (finds the outage region, `placeLr`), a per-dealer offset (`dealerLr`), trust (`trustPer`).
- The first `probes` requests each morning are probes spread from `probeLow` to `probeHigh` times the belief.
- Otherwise the price maximises (price - cost) x P(win), cost = `costMult` x typical fee, never under cost x
  (1 + `minMargin`). War day: level under `warDrop` x yesterday's; `warDecline` declines then. `winCap` caps a
  dealer's daily win share (raise by `capRaise`); off at 1.
- Option: the one `pickOption` serves on time; otherwise decline. Fees open at `feeOpen` x typical and rise
  `feeRise` an hour for `feeSteps` hours up to `feeMax`; urgent orders use the starter's steep schedule.
