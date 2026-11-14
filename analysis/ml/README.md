# Models fitted on the saved weeks

Scripts that turn every saved week and probe into flat files, and fit models of the two hidden sides of Spread on
them. They read the team's data folder (`junction2026-data`: `runs/`, `probe/`, `probe2/`, `probe3/`, `passive/`,
`explore-*`), named `$DATA` below; the big outputs stay there, in `$DATA/ml/`, and are not committed.

| File | What it does |
| --- | --- |
| `build_quotes.py` | Every recorded quote: one row per week, request and quoted option, with what the desk saw and how the dealer knew it at that minute (2.77M rows from 3,909 weeks) |
| `build_flips.py` | Every probe flip, the only exact measurements: `quote_flips.csv` (2,983 dealer limits) and `fee_flips.csv` (2,137 lowest booking fees). The held-out test set; both are committed here |
| `build_spells.py` | Every stretch of time in which an open gig showed one fee, with what the desk saw and whether a driver booked (9.9M rows) |
| `fit_dealer.py` | The dealer model, and its score on the flips |
| `resid.py` | What the dealer model's error on the flips is made of |
| `replay_demand.ts` | The baseline: `lean`'s `Demand` replayed over probe weeks and saved weeks (`baseline_demand.json`) |

```sh
DATA=../junction2026-data && mkdir -p $DATA/ml
python3 analysis/ml/build_quotes.py $DATA/runs/L8 $DATA/explore-win/L8 $DATA/explore-slow/L8 $DATA/explore-flat/L8 \
  $DATA/starter/L8 --map $DATA/runs/map.json --out $DATA/ml/quotes.csv.gz
python3 analysis/ml/build_quotes.py $DATA/probe2/quote/L8 --map $DATA/runs/map.json --out $DATA/ml/probe_week_quotes.csv.gz
python3 analysis/ml/build_flips.py $DATA/probe $DATA/probe2 $DATA/probe3 --context $DATA/passive --out $DATA/ml
python3 analysis/ml/build_spells.py $DATA/runs/L8 --out $DATA/ml/spells.csv.gz
cd $DATA/ml && uv run --python 3.13 --with numpy --with pandas --with scipy --with scikit-learn \
  python <repo>/analysis/ml/fit_dealer.py        # reads quotes.csv.gz, quote_flips.csv, probe_week_quotes.csv.gz
SPREAD_DATA=$DATA node analysis/ml/replay_demand.ts
```

The builders need only the standard library. The fits need numpy, which the project's Python 3.15 cannot load, so
they run on 3.13 with `uv run --python 3.13 --with ...`.

## The dealer model

For one option of one request there is one price under which the dealer buys (every probe flipped once). The model
is `P(win at price ratio r) = sigmoid((mu(x) + level[seed, day] - log r) / scale)`:

- `mu(x)` is what is the same in every world: the option and how many the dealer offers, the two places, the lane,
  the list price, and how the dealer knows us (orders on time, late orders, requests won and lost).
- `level[seed, day]` is the world's level on that day (the competitor's level, its day factor, the price war). Every
  policy that played a seed faced the same level, so in the fit it is one free intercept per seed and day, and the
  different prices that the policies quoted identify the rest. In a live week it is unknown, and `lean` learns it
  from the week's own wins and losses.

Fitted on 2.38M quotes of 306 seeds; the seeds of the probes and 33 more were kept out.

| Measured on | `lean`'s `Demand` | Dealer model with the level learned in the week |
| --- | --- | --- |
| 1,996 flips of `probe2`: RMSE of the predicted limit, in log price | 0.217 | 0.205 |
| the same, median absolute error | 0.124 | 0.121 |
| Single-option quotes of saved weeks: log-loss (0.691 knows nothing) | 0.611 (200 weeks of all seeds) | 0.552 (98 weeks of the 33 held-out seeds) |

What it found:

- **The level is most of what can be known.** Worlds differ by 7% (sd) and a day within its world by 12%.
- **Places, not dealers.** Deliveries to Vantaa, Espoo, Helsinki, Hyvinkää and Porvoo accept 10-17% less; pickups in
  Vantaa and Hyvinkää 9% more; a lane adds 7% (sd) of its own. The 40 dealers differ by under 5%, hours by under 2%.
- **Trust is the rule's 1% an order** (fitted 1.05), and eight late orders cost a dealer 26%.
- **The rest is noise that no feature explains.** With the level known, a request's limit still scatters by 16-20%;
  boosted trees on every feature explain 4% of that. The scatter is one draw per request: the errors of two options
  of one request correlate at 0.6 to 0.9. Next-day limits scatter more (22%) than same-day ones (14%).

`src/strategies/lean/prior.json` is this model's `mu(x)`, for `lean`'s `prior` param.
