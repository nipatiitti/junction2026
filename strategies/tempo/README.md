# Tempo

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk whose admission sizes each area by how fast our gigs book there. Issue #187. Ceiling and the root system stay as
they are.

| File           | Class            | Builds on        | What it decides                                |
| -------------- | ---------------- | ---------------- | ---------------------------------------------- |
| `admission.py` | `TempoAdmission` | `ChainAdmission` | Which requests to take, with each area's tempo |
| `dispatch.py`  | `Desk`           | the ceiling desk | The system: tells admission each gig it posts  |

## Run it

From the repository root:

```sh
uv run strategies/tempo/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/tempo/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `tempo`. Its admission line adds the gigs it timed, the world's share of quick
bookings, and how many requests got more room or less.

## The strategy

Admission (`strategies/admission`) sizes each area's capacity from the drivers who live near it, and tightens it only
after deadline warnings, which come hours late. Level 8 multiplies each town's drivers by a factor of its own, and the
driver list does not show who works. How fast a driver takes our gigs there does, from the first hour of the week.

1. **Quick or slow.** The desk tells admission each gig it posts, with its first pickup. A gig booked within `quick`
   = 30 minutes of its post is quick; one still open after that, or expired, is slow.
2. **The world's share** of quick gigs is shrunk to `world_start` = 0.7 with `world_prior` = 10 gigs.
3. **An area's tempo** is the share of quick gigs with a pickup within `pool` = 30 road minutes, shrunk to the
   world's with `area_prior` = 6 gigs, over the world's share, kept between `low` = 0.6 and `high` = 1.5.
4. **The capacity.** The area holds its usual cars times its tempo: more where drivers take our gigs at once, fewer
   where they wait.

After a restart in the final the desk rebuilds its orders but not the tempo, which starts again from the prior.

## Offline replay

`analysis.replay`'s quote replay with this desk, each of the week's posts passed to admission as the desk would, on the
ten distinct saved `ceiling` weeks. 55% to 78% of a week's gigs booked within 30 minutes, around the 70% prior. A week
gives 330 to 705 requests more room and 141 to 424 less. Admission takes 65.3% of the requests against 65.5% for
ceiling, and keeps 3,210 of ceiling's 3,233 won orders, with the same on-time share (97.9%), for a margin of €65,287
against €65,680: the areas it narrows gave up €393 of orders that paid. The bench below measures what the wider areas
add.

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), 57% to 70% of a week's gigs book within 30
minutes; 429 to 643 requests a week get more room and 201 to 366 less. Admission takes 65.2% of the requests against
65.4%, and keeps 1,321 of ceiling's 1,327 won orders (98.6% on time), for €30,255 against €30,465.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy `tempo`.

| Seed       |  `ceiling` |    `tempo` | Difference | On time |
| ---------- | ---------: | ---------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |  €9,751.76 |    −€79.33 |   98.4% |
| `spread-2` |  €6,673.95 |  €6,882.53 |   +€208.58 |   97.9% |
| `spread-3` |  €4,312.02 |  €4,312.02 |     ±€0.00 |   99.2% |
| Total      | €20,817.06 | €20,946.31 |   +€129.25 |         |

Ahead of ceiling by €129.25 in total: higher on `spread-2`, lower on `spread-1`, and the same week to the cent on
`spread-3`, where its capacity changes decided nothing. The orders that both won made €339 more. The lead is under 1% on
three seeds: a draw.
