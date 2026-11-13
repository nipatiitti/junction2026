# Spread docs (short versions)

Short versions of the Bahn "Spread" challenge documents, condensed from
<https://spread.bahnexpress.com/llms.txt> on 13 November 2026. They keep every
number and rule our system depends on and drop the prose.

**Where anything here differs from the originals, the server's `RULES.md` is
correct.** Go to the originals for full detail.

## The challenge in one paragraph

Build a system that does a car-transport dispatcher's job for one simulated
week in Finland. Dealers send price requests; you quote, win some, and pay
freelance drivers (via gigs) to move the cars. Score = gross margin in game
euros. You are ranked only if at least 90% of won orders arrive on time. The
final (one level 8 week) picks the 10 ranked teams with the highest margin; a
jury picks winners from those 10.

## Files

| File                               | Short version of                                  | Original                                                                                                         |
| ---------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| [rules.md](rules.md)               | The full rules                                    | [RULES.md](https://spread.bahnexpress.com/kit/RULES.md)                                                          |
| [handbook.md](handbook.md)         | Setup, levels, kits, events, how the world works  | [HANDBOOK.md](https://spread.bahnexpress.com/kit/HANDBOOK.md)                                                    |
| [api.md](api.md)                   | Routes, actions, limits, errors                   | [API.md](https://spread.bahnexpress.com/kit/API.md), [openapi.json](https://spread.bahnexpress.com/openapi.json) |
| [how-it-works.md](how-it-works.md) | The world in plain words, where margin comes from | [/how](https://spread.bahnexpress.com/how)                                                                       |
| [judging.md](judging.md)           | Schedule, final, jury criteria, submission        | [/judging](https://spread.bahnexpress.com/judging)                                                               |

Read `rules.md` first if you are writing decision logic, `api.md` if you are
writing the client.

## Quick start

```sh
export SPREAD_URL=https://spread.bahnexpress.com
export SPREAD_KEY=<team key from $SPREAD_URL/join>
curl -fsSO $SPREAD_URL/kit/spread-typescript.tar.gz && tar -xzf spread-typescript.tar.gz
cd typescript && bun starter.ts   # or: node starter.ts (Node 22.18+)
```

Team pages: [/team](https://spread.bahnexpress.com/team) (runs, rankings,
submission hash), [/leaderboard](https://spread.bahnexpress.com/leaderboard),
[/viewer/](https://spread.bahnexpress.com/viewer/) (replay of each week).
