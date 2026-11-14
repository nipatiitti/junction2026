# Lane fee

The typical fee of a lane without the noise of one request, and the admission and the fee planner that count from it,
for the systems of [`strategies/headroom`](../headroom/README.md) and up. Issue #200. The folders it builds on stay as
they are.

| File         | Class               | Builds on           | What it decides                                               |
| ------------ | ------------------- | ------------------- | ------------------------------------------------------------- |
| `lane.py`    | `LaneFee`           | `Strategy`          | The typical fee of a lane, without the noise of one request   |
| `lane.py`    | `LaneCostAdmission` | `LeadCostAdmission` | The lead-cost admission, with its driver cost on the lane fee |
| `lane.py`    | `LaneFeePlanner`    | `DawnFeePlanner`    | The dawn fee schedule, with every fee on the lane fee         |
| `fit.py`     |                     |                     | Fits the lane fees on the saved weeks, into `lanes.json`      |
| `lanes.json` |                     |                     | The fitted lane fees                                          |

All three classes are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the constructor
`(roster, world_map, level=8, params=None)`; `LaneFee` has a frozen `Params`. A desk builds one `LaneFee` and gives it
to the other two, as the headroom desk does:

```python
self.lane = LaneFee(roster, world_map, level)
self.admission = LaneCostAdmission(roster, world_map, level, lane=self.lane)
self.fees = LaneFeePlanner(roster, world_map, level, lane=self.lane)
```

```sh
uv run python -m strategies.lane_fee.fit     # fits lanes.json from out/spread.sqlite
```

## What the saved weeks show

The handbook says the typical fee of a request is the cost of its work to a typical driver, scaled, with "a noise for
each request". Every strategy so far reads that number as the truth: admission's driver cost is the typical fee times
a factor, and every gig opens at 0.9 times it.

- **The noise is large.** Over the 12,411 distinct requests of the saved level 7 and 8 weeks, a request's typical
  fee differs from the mean of its lane (same pickup and delivery place) with a log standard deviation of 0.127:
  one request in five is more than 13% off. The list price of a lane has no such noise.
- **The lane's fee is the same in every world.** The mean log ratio of a world's typical fees to the lanes' means is
  between −0.012 and −0.002 on each of 12 seeds. A private address, a premium or electric car changes nothing in it,
  and a trade-in's typical fee is that of its first car's lane.
- **Drivers do not follow the noise.** Of the saved gigs that opened at 0.9 times their request's typical fee, 35%
  booked at the opening fee when that typical fee was more than 15% under its lane's, and 70% when it was more than
  5% over. The orders cost 0.96 times the lane fee in the first group and 1.09 to 1.17 times in the second: where
  the noise is high we overpay, and where it is low the gig waits for a raise.
- **Admission is misled the same way.** A request whose typical fee is 10% or more above its list price was mostly
  declined for its cost, but such orders cost 1.12 to 1.16 times their typical fee, against 1.23 to 1.36 times for
  the requests whose typical fee looks cheap.

## The strategy

1. **The lane fee.** `LaneFee.typical(pickup, delivery, own)` is a weighted mean, in logs, of three numbers: the
   mean of the lane's requests in the saved weeks (weight: their count), a straight line over the lane's road
   minutes for a lane with few requests (weight `line`, 1.5), and the request's own typical fee (weight `own`, 1).
   A lane with 30 saved requests is the saved mean to 92%.
2. **Admission.** `LaneCostAdmission` is the lead-cost admission whose table multiplies the lane fee instead of the
   request's typical fee. A request with a low typical fee is no longer taken as cheap, and one with a high typical
   fee is no longer declined for it.
3. **Fees.** `LaneFeePlanner` is the dawn fee planner whose opening fee, hold fee, dawn ladder, sprint ladder and
   top fee are multiples of the lane fee. After a change of plan (`order_changed`) the fee is that of the new lane; the
   request's own typical fee, which is for the old trip, then counts for nothing.

## The variables

`Params` in `lane.py`, exported as `LaneFeeParams`.

| Variable | Default | What it does                                                            |
| -------- | ------- | ----------------------------------------------------------------------- |
| `own`    | 1.0     | The request's own typical fee counts as this many requests of its lane  |
| `line`   | 1.5     | The line over the road minutes counts as this many requests of the lane |

`lanes.json` holds each lane's mean log typical fee and its number of requests, the line (`base`, `per_minute`),
and the two spreads that give `line`: a request around its lane (`noise`) and a lane around the line (`spread`).
Run `fit.py` again when weeks on new seeds are saved, and commit the new `lanes.json`.

## Played

Level 8, each week saved in `data/scrape/runs` under the policy named. All have the lead-cost admission and dawn
fees; the first pair differs only in the lane fee.

| What was played                                       | Policy       | `spread-1` | `spread-2` | `spread-4` |
| ----------------------------------------------------- | ------------ | ---------- | ---------- | ---------- |
| Headroom pricing, without the lane fee                | `x-cap`      | €11,839.45 |            |            |
| The same with the lane fee                            | `x-cap-lane` | €12,346.00 |            |            |
| Ceiling pricing with the lane fee                     | `a-lane`     | €11,815.71 |            |            |
| The same with the cost table measured under dawn fees | `lane-fee`   | €13,352.62 | €8,718.53  | €8,642.74  |

With the lane fee, the driver fees of the week fell from 1.05 to 1.00 times the requests' typical fees while it won
about as many orders (389 against 395). The last line is why the systems keep the first cost table of
`strategies/lead_cost`: the cheaper table won 450 orders on `spread-1` and made the most of any week there, and on
`spread-4` it won more cars than drivers could move on time (93.9% on time) and made €4,400 less than the headroom
system.
