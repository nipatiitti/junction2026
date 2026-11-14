# Eighty

A dispatch system built on [`strategies/headroom`](../headroom/README.md) that puts the changes that each beat the
headroom desk into one desk, then tunes their variables on five seeds. Issue #254: the goal is €80,000 of margin over
the level-8 practice seeds `spread-1` to `spread-5`, every week ranked. The systems it builds on stay as they are.

| Part      | Class            | From                                     | What it decides                                    |
| --------- | ---------------- | ---------------------------------------- | -------------------------------------------------- |
| fees      | `SoftTopPlanner` | [`soft_top`](../soft_top/README.md)      | The dawn fee schedule, topped at 2 × the lane fee  |
| admission | `SameDayAdmission` | [`same_day`](../same_day/README.md)    | The fastest option that still pays                 |
| pricing   | `PriorPricing`   | [`lane_prior`](../lane_prior/README.md)  | The headroom price, lifted by the delivery place   |

## Run it

From the repository root:

```sh
uv run strategies/eighty/dispatch.py --level 8 --seed spread-1
uv run --env-file .env python -m strategies.bench strategies/eighty/dispatch.py --seeds spread-1..spread-5 --jobs 4
```

Its weeks are saved with the policy `eighty`.

## The variables

`PARAMS` in `dispatch.py` holds the values this system plays with, by part, over the defaults of each part's class.
Two environment variables change them for one run, so a bench can try a variant without a new file:

| Variable        | What it does                                                                                       |
| --------------- | -------------------------------------------------------------------------------------------------- |
| `EIGHTY_PARAMS` | JSON with a key per part (`admission`, `pricing`, `fees`, `lane`, `bundler`, `offers`) naming the fields of its `Params` to change, for example `{"fees": {"top": 1.7}}` |
| `EIGHTY_TAG`    | Names the variant: its weeks are saved with the policy `eighty-<tag>`                              |
| `EIGHTY_LOG`    | A folder: each week's output, with the strategies' summaries, is also written to `<tag>-<seed>.log` |

The desk sets admission's `price_factor` and `min_margin` itself before each quote, so changing those two does
nothing.

## Bench

Level 8, seeds `spread-1` to `spread-5`, four weeks at a time. Every week is saved under `data/scrape/runs/L8/`.

| Version | `spread-1` | `spread-2` | `spread-3` | `spread-4` | `spread-5` | Total | On time |
| ------- | ---------: | ---------: | ---------: | ---------: | ---------: | ----: | ------: |
| v1: the three classes, their defaults | €12,587 | €10,062 | €5,305 | €13,454 | €7,337 | €48,745 | 97.4% |
