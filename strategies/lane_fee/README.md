# Lane fee

A dispatch system built on [`strategies/lead_cost`](../lead_cost/README.md): its `Desk` is a subclass of the
lead-cost desk that counts every driver cost and every fee from the lane's typical fee, not from the request's own.
Issue #200. The systems it builds on stay as they are.

| File          | Class               | Builds on           | What it decides                                              |
| ------------- | ------------------- | ------------------- | ------------------------------------------------------------ |
| `lane.py`     | `LaneFee`           | `Strategy`          | The typical fee of a lane, without the noise of one request  |
| `lane.py`     | `LaneCostAdmission` | `LeadCostAdmission` | The lead-cost admission, with its driver cost on the lane fee |
| `lane.py`     | `LaneFeePlanner`    | `DawnFeePlanner`    | The dawn schedule, with every fee on the lane fee            |
| `fit.py`      |                     |                     | Fits the lane fees on the saved weeks, into `lanes.json`     |
| `lanes.json`  |                     |                     | The fitted lane fees                                         |
| `dispatch.py` | `Desk`              | the lead-cost desk  | The system: the lead-cost desk with the three classes above  |

All three classes are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the constructor
`(roster, world_map, level=8, params=None)`; `LaneFee` has a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/lane_fee/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/lane_fee/dispatch.py strategies/lead_cost/dispatch.py --jobs 2
uv run python -m strategies.lane_fee.fit     # fits lanes.json from out/spread.sqlite
```

Its weeks are saved with the policy `lane-fee`.

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
3. **Fees.** `LaneFeePlanner` is the dawn fee planner whose opening fee, hold fee, dawn ladder and top fee are
   multiples of the lane fee. After a change of plan (`order_changed`) the fee is that of the new lane; the
   request's own typical fee, which is for the old trip, then counts for nothing.

The desk builds one `LaneFee` and gives it to both.

## The variables

`Params` in `lane.py`, exported as `LaneFeeParams`.

| Variable | Default | What it does                                                                      |
| -------- | ------- | --------------------------------------------------------------------------------- |
| `own`    | 1.0     | The request's own typical fee counts as this many requests of its lane            |
| `line`   | 1.5     | The line over the road minutes counts as this many requests of the lane           |

`lanes.json` holds each lane's mean log typical fee and its number of requests, the line (`base`, `per_minute`),
and the two spreads that give `line`: a request around its lane (`noise`) and a lane around the line (`spread`).
Run `fit.py` again when weeks on new seeds are saved, and commit the new `lanes.json`.
