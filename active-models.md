# Active models

Which models are worth a practice week on the live server. Read this **before you play anything**: the team holds
eight practice slots and shares one rate limit, so a week spent on a system that is already behind is a week the
leaders do not get. [`AGENTS.md`](AGENTS.md) has the rest of the online rules, one run at a time among them.

## The list

Every model in `strategies/` and the root `dispatch.py`, one practice week each, level 8, seed `spread-1`, played by
`strategies.bench` on 2026-11-14. The leading five by margin, with the root beside them as the week's reference:

| # | model                         | margin    | vs `dispatch.py` | on time |
| - | ----------------------------- | --------- | ---------------- | ------- |
| 1 | `strategies/ceiling`          | €9,831.09 | +€1,767.69       | 97.4%   |
| 2 | `strategies/scarcity_cost`    | €8,884.43 | +€821.03         | 98.6%   |
| 3 | `dispatch.py` (the reference) | €8,063.40 | —                | 98.1%   |
| 4 | `strategies/delivery_urgency` | €7,124.50 | −€938.90         | 97.7%   |
| 5 | `strategies/price_ladder`     | €6,200.04 | −€1,863.36       | 97.3%   |

`strategies/scarcity_urgency` is new and has not been played, so it is not on the list yet; run it with the leaders
rather than instead of them.

## What the numbers are

Margin is the score: the week's gross margin in game euros; a model is ranked only when at least 90% of its orders
arrive on time, and an unranked week does not count at all. The rest of that comparison, in order: `bundling_cheaper`
€6,182.79, `bundling_more` €6,173.59, `ratchet` €5,173.02 — and `ratchet` was at 90.5% on time, one late order from
losing everything — then the starter's `baseline` at −€72,612.51, unranked.

Those nine weeks are committed under `data/scrape/runs/L8/spread-1`, so the numbers can be re-read offline with
`uv run python -m tools.db` and a query against `out/spread.sqlite`.

**One seed proves little.** The bottom three of the five sit within €1k of each other, the ladder family within €26,
and the whole ladder family ran behind the root. Read the order as a guide, not a verdict, and refresh it when a
comparison over more seeds lands.

## How to refresh

Play every model on the same seeds and take the leading five by margin. `$(ls …)` picks up a new folder on its own:

```sh
uv run --env-file .env python -m strategies.bench \
  $(ls dispatch.py strategies/*/dispatch.py strategies/*/baseline.py) \
  --level 8 --seeds spread-1,spread-2 --jobs 6
```

That is one run: ten models, two weeks each at `--jobs 6`. Add seeds as the slots allow, before a ranking round most
of all. Each model's weeks land in `data/scrape/runs` with its own policy, so they stay apart in the database.

To gather many weeks without watching, `uv run python -m tools.sweep` plays the active models on fresh random seeds,
round after round, until stopped ([`tools/README.md`](tools/README.md#play-many-fresh-seeds)). It adds weeks, it does
not read them, so a comparison still needs the run above.
