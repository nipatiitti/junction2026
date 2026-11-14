# tide

The week has a shape and the price follows it. Monday nobody trusts us, by Thursday the big dealers do, and Friday
orders are dear to deliver with no time left to recover a late one. A price is the base markup per option
(`sameDay`, `nextDay`, `within3`) × a weekday schedule (`mon` .. `fri`, `wkd`) × a global level × a trust premium
(`trustStep` per trust point up to `trustCap`) × `friPremium` for options whose deadline is Friday from `friHour` on
or the weekend. The level is a PI controller on log price: the win rate of the last `window` quotes against a target
that falls from `targetMon` to `targetFri`, with gains `kp`, `ki`, the integral clamped at `iMax` and the level at
`levelMin`..`levelMax`. On the price-war day (today's win rate under `warRatio` × target after `warMin` quotes) the
controller freezes, so it does not wind up, and prices are × `warCut`: below 1 follows the war down to keep winning
and building trust (the default, since margin at 0.85 × still clears cost), 1 sits the day out at normal prices.

Run: `pnpm bench tide --level 8 --seeds spread-1`.
