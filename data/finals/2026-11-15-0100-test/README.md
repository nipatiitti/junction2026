# Test final, 15 November 2026, 01:00

The public leaderboard of the 01:00 test final, recorded over time while the final ran, to see how the leading teams
(Juhus, HackandSeek) gain orders and margin through the week.

- **Team on the leaderboard:** `blip_blip_2`. **World:** `fe37edac2bc2e31e218fb`. **Commit played:** `ad715366`
  (strategy `lean` with its defaults). The week itself is in `data/scrape/runs/L8/final/fe37edac2bc2e31e218fb/`.
- **Result:** margin €12,875.33, revenue €32,949.25, 364 orders, 97.5% on time, ranked 6th of 41 ranked teams (236
  listed).
- **The leaders:** HackandSeek won with €14,111.66 and 445 orders. Juhus won the most orders (488) and the most
  revenue (€41,955.30) but kept 31.7% of it as margin, against our 39.1%, and came 3rd with €13,287.75 and 94.1% on
  time.
- **What is recorded:** 815 messages of `GET /v1/leaderboard` (one every 2 seconds, all 236 teams), from world minute
  2140 (Tuesday 11:40) to the end at minute 14280, with no gap longer than 42 world minutes. The recording started 7
  minutes after the final did, so Monday and Tuesday morning are missing.
- **Cost:** none on our key. The feed is public and outside the rate limits.

## Files

| File                    | What it holds                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `leaderboard.jsonl.gz`  | Every recorded message, one JSON object per line, oldest first; `now` is the world minute  |
| `leaderboard.json`      | The last message, with status `ended`: the final ranking                                   |
| `record_leaderboard.sh` | The recorder: `sh record_leaderboard.sh` appends to the two files until the feed has ended |

Read the recording with `gzip.open("leaderboard.jsonl.gz", "rt")` and `json.loads` on each line.
