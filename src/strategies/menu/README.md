# menu

Prices a request's options as one menu, like a wine list where the second-cheapest bottle sells best. The dealer
has one hidden threshold per request: `median` × region (`capital` / `other`) × trust (`trustStep` per on-time
order up to `trustCap`) × a learned world level × a lognormal draw (`sigma`). Faster options sell at `nextRatio`
and `sameRatio` above slower ones. Among options under threshold the dealer takes the fastest with a probability
that falls with its premium over the cheapest (99.5% at 0, 74% at +10%, 49% at +20%, 12% at +50%). On the first
`price` call for a request we search a grid (`gridLo`..`gridHi` by `gridStep`, or leave an option out) for the menu
with the highest expected profit over `draws` threshold points, cache it, and return each option's part. A won
request adds `winValue` × list (future trust); same_day costs `sameDayRisk` × list more. `onOutcome` moves the world
level by `eta` × (won − predicted win chance), kept within `levelLo`..`levelHi`.
