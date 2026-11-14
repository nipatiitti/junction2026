# whale

A casino host who only cares about high rollers. A few dealers send most requests (one about 30%, the top five 61%),
and each on-time order raises what a dealer accepts by about 1%, up to 25 orders; a late one halves the count.

- Counts requests per dealer; once `minRequests` are in, a dealer with `whaleShare` or more of them is a whale.
- Tracks each dealer's trust from `delivered` events (on time +1 up to `trustCap`, late halves it).
- Whales building trust: only options with `whaleSafeHours` of slack beyond the usual 5 h, an easy price
  (`whaleBase`), and drivers paid `whaleBuildFee` times the starter's rising fees, so nothing comes late.
- Whale price over list: `whaleBase + whaleRise * trust + whaleCurve * (trust / trustCap)^2`.
- Small dealers: one fat quote at `smallMult + smallRise * trust` over list, fees `smallFee`.
- Before anyone is known: `unknownMult`. `same_day` gets `sameDayExtra` more.

Params and defaults are in `index.ts` (`DEFAULTS`).
