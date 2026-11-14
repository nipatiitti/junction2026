# Active models

Which models are worth a practice week on the live server. Read this **before you play anything**: the team holds
eight practice slots and shares one rate limit, so a week spent on a system that is already behind is a week the
leaders do not get. [`AGENTS.md`](AGENTS.md) has the rest of the online rules, one run at a time among them.

## The list

The systems of issue #200 and the root `dispatch.py`, one practice week each, level 8, seed `spread-1`, played by
`strategies.bench` on 2026-11-14. The leading five by margin, with the root beside them as the week's reference:

| #   | model                         | margin     | vs `dispatch.py` | on time |
| --- | ----------------------------- | ---------- | ---------------- | ------- |
| 1   | `strategies/all_in`           | €13,591.71 | +€5,528.31       | 99.2%   |
| 2   | `strategies/soft_top`         | €13,297.12 | +€5,233.72       | 98.9%   |
| 3   | `strategies/flu_guard`        | €13,115.78 | +€5,052.38       | 98.9%   |
| 4   | `strategies/headroom`         | €12,670.71 | +€4,607.31       | 99.2%   |
| 5   | `strategies/same_day`         | €12,283.73 | +€4,220.33       | 98.4%   |
| —   | `dispatch.py` (the reference) | €8,063.40  | —                | 98.1%   |

`strategies/all_in` is the one to play: over `spread-1` to `spread-22` it makes €12,268 in the mean week, with all 22
weeks ranked, against €11,272 for `soft_top` (21 ranked) and €11,277 for `flu_guard`;
[`strategies/all_in/README.md`](strategies/all_in/README.md) has every week. `strategies/lane_prior` made €12,170.85 on
`spread-1`. All of them stand on the `strategies/headroom` desk; `strategies/ceiling`, the leader before them, made
€9,831.09 on `spread-1`.

The systems that main gained since the last comparison of every model (`scarcity_urgency`, the seven of issue #187,
the city and dealer ladders, `max_margin`, `tight_margin`, `low_opening`) have not been played against these; run
them with the leaders rather than instead of them. Play at most four weeks at once (`--jobs 4`): the team shares eight
slots.

## What the numbers are

Margin is the score: the week's gross margin in game euros; a model is ranked only when at least 90% of its orders
arrive on time, and an unranked week does not count at all. The earlier comparison of every model, in order after the
root: `ceiling` €9,831.09 and `scarcity_cost` €8,884.43 ahead of it, then `delivery_urgency` €7,124.50, `price_ladder`
€6,200.04, `bundling_cheaper` €6,182.79, `bundling_more` €6,173.59, `ratchet` €5,173.02 — and `ratchet` was at 90.5% on time, one late order from
losing everything — then the starter's `baseline` at −€72,612.51, unranked.

Those weeks, and the ones of the list above, are committed under `data/scrape/runs/L8/spread-1`, so the numbers can be re-read offline with
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

To play several of the systems built on `ceiling` in one system, and find the best mix of them,
`uv run python -m strategies.tournament` plays them in rounds ([`strategies/tournament/README.md`](strategies/tournament/README.md)).
It reads the saved weeks it can, and `--plan` shows what it would play; name the layers worth a week with `--layers`.
