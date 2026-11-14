# City/time informed hold (E3)

An experimental variant of [`all_in`](../all_in/README.md) and of [`solo_chain`](../solo_chain/README.md) with the
same single cheap-solo-then-chain fallback, but **the time allowed for a future compatible car depends on measured
city/time arrival densities** rather than always being 45 minutes.

For a non-batch order with six or more hours of pickup slack, when its *delivery town* typically sees many follow-on
cars at the current day/hour:

- **at least 0.5 expected cars in 60 minutes** → wait **60 minutes**;
- **at least 0.25 expected cars in 45 minutes** → wait **45 minutes**;
- below those → no extra hold, and the normal all_in solo path continues.

After the timer, if the solo remains unbooked the desk makes one withdraw-and-recompose attempt, never accepting an
infeasible chain or withdrawing a booked gig. Individual pickup windows, route feasibility and the safe posting
cutoff always take precedence over demand priors.

The statistic is deliberately modest: `expected = arrival_rate[city][weekday][hour] * wait_minutes / 60`, using each
city's mean request arrivals per week at that day/hour. It is not a replacement for the bundler's actual delivery
window and offer matching; it only chooses the small wait to try. The city's delivery town is used because that is
where another car could be ready as soon as we deliver the first one.

## Fit the priors offline

```sh
uv run --env-file .env python -m strategies.informed_chain.priors_fit --db out/spread.sqlite
```

No server access is needed: one full `dispatch` week per seed in `out/spread.sqlite` is used so duplicate plays of
the same seeded demand do not get counted repeatedly. `priors.json` is committed with the strategy.

## Play

From a separate working tree:

```sh
uv run strategies/informed_chain/dispatch.py --level 8 --seed tour-r1-d0cceb91
```

Saved weeks use policy `informed-chain`. This is experiment E3, not a replacement for `all_in`.
