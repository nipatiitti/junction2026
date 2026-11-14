# groundhog

A man living the same week again and again, getting it more right each time. **Deliberately overfit to practice
seeds**: a practice week with the same seed and level always sends the same requests (ids, dealers, list prices,
times), so every saved week tells us where each option's threshold lies.

- `node src/strategies/groundhog/learn.ts spread-1 [runs dir ...]` scans every saved week under
  `data/scrape/runs/L8/<seed>/` (reveal for our quotes and outcomes, events for each dealer's trust at the time) and
  writes `memory-<seed>.json`: per request option, the highest winning and lowest losing ratio, each divided by
  `1 + trust / 100`. Quotes over 2.5 × list are ignored; a multi-option request is a loss only if lost outright.
- The strategy loads every memory file, recognises the seed once `matchNeeded` requests match by id, dealer and list
  prices, and quotes each remembered option at `win + pos × (loss − win)`, `win × aboveWin`, `loss × belowLoss`, or a
  flat fallback markup, times `1 + trustPct × trust / 100`. It declines when under cost × `margin`.
- Re-run `learn.ts` after each week: the brackets narrow and the next week quotes closer to each threshold.

Params: `pos` 0.5, `aboveWin` 1.06, `belowLoss` 0.93, `trustPct` 1, `sameDay` 1.42, `nextDay` 1.36, `within3` 1.3,
`margin` 1.15, `matchNeeded` 3. Format only the `.ts` files: `pnpm format` would expand the compact memory JSON.
