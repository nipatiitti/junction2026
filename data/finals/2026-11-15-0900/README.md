# The final, 15 November 2026, 09:00

The public leaderboard of the final, recorded over time while it ran.

- **Team on the leaderboard:** `blib_blib`. **World:** `f32ae7eb769f720d69249`. **Commit played:** `67a2a596`
  (strategy `lean` with its defaults, the ones of
  [the orthogonal-array search](../../../src/strategies/lean/README.md#the-orthogonal-array-search-of-the-defaults-15-november-389)).
  The week itself is in `data/scrape/runs/L8/final/f32ae7eb769f720d69249/`.
- **Command:** `pnpm dispatch --final`.
- **Result:** margin €21,744.80, revenue €49,488.92, 484 orders, 96.1% on time, **2nd of 58 ranked teams** (236
  listed).
- **The leaders:**

  | Rank | Team         | Margin     | Revenue    | Orders | On time | Margin share |
  | ---- | ------------ | ---------- | ---------- | ------ | ------- | ------------ |
  | 1    | `juhus`      | €22,930.87 | €53,034.55 | 474    | 97.7%   | 43.2%        |
  | 2    | `blib_blib`  | €21,744.80 | €49,488.92 | 484    | 96.1%   | 43.9%        |
  | 3    | `progresful` | €21,111.65 | €50,757.76 | 493    | 97.0%   | 41.6%        |
  | 4    | `seekers`    | €19,974.72 | €47,912.92 | 432    | 95.4%   | 41.7%        |
  | 5    | `mathnet1`   | €19,965.41 | €55,310.00 | 512    | 94.7%   | 36.1%        |

  Juhus won 10 orders fewer than we did, at €112 an order against our €102, and kept about the same share of the
  revenue as margin.
- **What is recorded:** 1,130 messages of `GET /v1/leaderboard`: 99 before the start (status `scheduled`), then
  1,031 from world minute 8 to the end at minute 14280, all 236 teams in each, with no gap longer than 41 world
  minutes.
- **Cost:** none on our key. The feed is public and outside the rate limits.

## Files

| File                    | What it holds                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------ |
| `leaderboard.jsonl.gz`  | Every recorded message, one JSON value per line, oldest first; `now` is the world minute   |
| `leaderboard.json`      | The last message, with status `ended`: the final ranking                                   |
| `record_leaderboard.sh` | The recorder: `sh record_leaderboard.sh` appends to the two files until the feed has ended |

Read the recording with `gzip.open("leaderboard.jsonl.gz", "rt")` and `json.loads` on each line. Some lines are a
bare number, not a message: skip the lines that do not start with `{`.
