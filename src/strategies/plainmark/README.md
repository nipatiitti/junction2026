# plainmark

A market-stall trader's strategy: three markups and one fee multiple, no learning, no models.

- Quote every option that `canServe` says we can deliver on time, at list price × the option's markup.
- Raise that by `trustStep` for each on-time order the dealer already has from us (up to `trustCap`); a late
  order halves the count, as the world does. Decline when no option can be served.
- Gigs use the starter's stops and audience, with our own fees: `feeOpen` × the typical fee, flat for
  `flatHours`, then `feeRise` more each hour up to `feeMax`. After the deadline warning: `urgentOpen`, rising by
  `urgentRise` each half hour up to `urgentMax`.

Params: `markupSameDay` 1.42, `markupNextDay` 1.45, `markupWithin3Days` 1.48, `trustStep` 0.01, `trustCap` 25,
`feeOpen` 1.1, `flatHours` 1, `feeRise` 0.15, `feeMax` 1.8, `urgentOpen` 1.8, `urgentRise` 0.25, `urgentMax` 3.
