# Test final, 15 November 2026, 01:00

The public leaderboard of the 01:00 test final, recorded over time while the final ran, to see how the leading teams
(Juhus, HackandSeek) gain orders and margin through the week.

- **Team on the leaderboard:** `blip_blip_2`.
- **What is recorded:** every message of `GET /v1/leaderboard` (one every 2 seconds, all 236 teams), from world minute
  2140 (Tuesday 11:40) to the end. The recording started 7 minutes after the final did, so Monday and Tuesday morning
  are missing.
- **Cost:** none on our key. The feed is public and outside the rate limits.

## Files

| File                    | What it holds                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `leaderboard.jsonl.gz`  | Every recorded message, one JSON object per line, oldest first; `now` is the world minute  |
| `leaderboard.json`      | The last recorded message                                                                  |
| `record_leaderboard.sh` | The recorder: `sh record_leaderboard.sh` appends to the two files until the feed has ended |

Read the recording with `gzip.open("leaderboard.jsonl.gz", "rt")` and `json.loads` on each line.
