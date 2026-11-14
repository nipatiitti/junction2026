# Learned driver cost

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk whose admission corrects its driver cost with the week's own bookings. Issue #187. Ceiling and the root system
stay as they are.

| File           | Class                  | Builds on        | What it decides                                      |
| -------------- | ---------------------- | ---------------- | ---------------------------------------------------- |
| `admission.py` | `LearnedCostAdmission` | `ChainAdmission` | Which requests to take, with the driver cost learned |
| `dispatch.py`  | `Desk`                 | the ceiling desk | The system: tells admission each booked fee          |

## Run it

From the repository root:

```sh
uv run strategies/learned_cost/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/learned_cost/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `learned-cost`. Its admission line adds the bookings it learned from, the world's
correction, and how many estimates the correction lowered and raised.

## The strategy

Admission's driver cost (`strategies/admission`) is the typical fee × 1.15 at levels 7 and 8, scaled by the drivers
the roster puts near the pickup and the delivery, the hour, private addresses, the note and a return leg. Level 8
multiplies each town's drivers by a factor of its own, new in every world, so the roster misleads: the same estimate
is too high in some towns and too low in others. Ceiling uses that cost twice: admission declines a request whose
cost × 1.10 is above the maximum, and pricing never quotes under it.

1. **Each booking teaches.** When a driver books a gig of one order at a known fee, the desk tells admission. The
   ratio is the fee over the cost that admission expected for those cars (a bundle's fee is shared, so it is left out).
2. **The world's correction** is the mean ratio, shrunk to 1 (the base estimate) with `world_prior` = 10 bookings.
3. **A place's correction** is the mean ratio of the bookings at pickups within `pool` = 20 road minutes, shrunk to
   the world's with `town_prior` = 4 bookings, and kept between `low` = 0.6 and `high` = 1.6.
4. **The cost** is the base estimate times the place's correction, so admission and the price floor both follow it.

After a restart in the final the desk rebuilds its orders but not the corrections, which start again at 1.

## Offline replay

`analysis.replay`'s quote replay with this desk, and each booking of the week's gigs passed to admission as the desk
would, on the ten distinct saved `ceiling` weeks. The world's correction ends between 0.97 and 1.06: on average the base
estimate is about right. But by place the correction lowers most estimates (528 to 959 lowered and 16 to 198 raised a
week): the cars whose gigs book dear are few and concentrated. Admission takes 68.6% of the requests against 65.5% for
ceiling. Of the orders that the weeks won, it keeps 3,219 of ceiling's 3,233, with the same on-time share (97.9%), and
their margin is €65,542 against €65,680. The requests it takes in addition were not won in those weeks, so the replay
cannot tell what they earn; the bench below does.

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), the world's correction ends between 0.98 and
1.04, and the place corrections lower 514 to 954 estimates a week and raise 16 to 433. Admission takes 69.6% of the
requests against 65.4%, and keeps 1,321 of ceiling's 1,327 won orders (98.6% on time), for €30,258 against €30,465.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy
`learned-cost`.

| Seed       |  `ceiling` | `learned_cost` | Difference | On time |
| ---------- | ---------: | -------------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |      €9,774.16 |    −€56.93 |   98.3% |
| `spread-2` |  €6,673.95 |      €6,333.25 |   −€340.70 |   98.8% |
| `spread-3` |  €4,312.02 |      €4,297.94 |    −€14.08 |   99.2% |
| Total      | €20,817.06 |     €20,405.35 |   −€411.71 |         |

Behind ceiling on all three seeds, by €411.71 in total. It won 1,022 orders against 952. The 117 orders that only it won
earned €1,553, €13 each; the 47 that only ceiling won had earned €1,150, €24 each. On the 905 orders that both won it
made €799 less: a lower cost also lowers ceiling's price floor, so those cars sold cheaper (1.359 × the list price
against 1.373).
