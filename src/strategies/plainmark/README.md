# plainmark

A market-stall trader's strategy: three markups and one fee multiple, no learning, no models.

- Quote every option that `canServe` says we can deliver on time, at list price × the option's markup.
- Raise that by `trustStep` for each on-time order the dealer already has from us (up to `trustCap`); a late
  order halves the count, as the world does. Decline when no option can be served.
- Gigs use the starter's stops and audience, with our own fees: `feeOpen` × the typical fee, flat for
  `flatHours`, then `feeRise` more each hour up to `feeMax`. After the deadline warning: `urgentOpen`, rising by
  `urgentRise` each half hour up to `urgentMax`.

Params: `markupSameDay` 1.28, `markupNextDay` 1.3, `markupWithin3Days` 1.32, `trustStep` 0.01, `trustCap` 25,
`feeOpen` 0.95, `flatHours` 2, `feeRise` 0.1, `feeMax` 1.5, `urgentOpen` 1.5, `urgentRise` 0.25, `urgentMax` 2.5.
