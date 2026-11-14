# Test final, 14 November 2026, 14:00

Our run of the 14:00 test final with the TypeScript harness, kept for the after-action analysis.

- **World:** `f3d1d8961dc4ca1899d73`. **Commit played:** `c8d5338c`.
- **Command:** `pnpm dispatch --final --set target=0.6` (strategy `lean`, chains on, every other param at its default).
- **Result:** margin €890.13, revenue €4,185.67, 69 orders, 100% on time, ranked 42nd of 55 ranked teams (217 listed).
- **Shape of the test final:** it ran from 14:00 to 14:18. Monday to Wednesday (614 requests) had passed before the
  world opened; the 417 requests of Thursday and Friday were the only ones a team could quote.
- **Harness:** all 417 requests quoted, at most 3 simulated minutes after arrival; no rebuild, no strategy fault, no
  refused action.
- **Pricing:** we won 71 of 417 quotes (17%). Our median quote was 1.42 × list on Thursday and 1.57 × on Friday; our
  winning quotes had medians of 1.15 × and 1.34 ×. The top ten teams won 135 to 167 orders.

## Files

| File | What it holds |
|---|---|
| `console.log` | What the run printed: the score at each midnight, the end, the strategy's summary line |
| `journal.jsonl` | Every action we sent (417 quotes, 75 posts, 5 withdraws) with the server's answer, the minute and the last event seen |
| `leaderboard.json` | The last message of `GET /v1/leaderboard`, fetched at 14:22 after the final had ended |
| `practice-rankings-L8.json` | `GET /v1/leaderboards/practice?level=8`, fetched at 14:22 |
| `pre-final-practice-bench.csv` | The practice bench played at 13:55 on seed `rnd-43f95900`: `target=0.6` and `target=1` |

The week itself (events, snapshot, driver list, score, reveal) is in
`data/scrape/runs/L8/final/f3d1d8961dc4ca1899d73/`, and the two practice weeks of the bench are in
`data/scrape/runs/L8/rnd-43f95900/`.
