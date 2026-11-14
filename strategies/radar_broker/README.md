# Radar broker

A dispatch system built on [`strategies/all_in`](../all_in/README.md), the leading model of
[`active-models.md`](../../active-models.md): its `Desk` is a subclass of the all-in desk whose quotes surge with the
live balance of our work and our drivers near the pickup, as a ride-hailing broker prices a ride. Issue #300. The
systems it builds on stay as they are.

| File           | Class          | Builds on       | What it decides                                      |
| -------------- | -------------- | --------------- | ---------------------------------------------------- |
| `pricing.py`   | `RadarPricing` | `PriorPricing`  | The all-in price of a quote, times the area's surge  |
| `dispatch.py`  | `Desk`         | the all-in desk | The system: the all-in desk with the pricing above   |
| `lift_only.py` | `Desk`         | the radar desk  | The same system with a surge that never cuts a price |

`RadarPricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `PriorPricing`, with
the constructor `(roster, world_map, level=8, params=None, radar=None)` and a frozen `Params`. `radar` is the desk's
`Offers` ([`strategies/offers`](../offers/README.md)); pricing reads it and never changes it.

## Run it

From the repository root:

```sh
uv run strategies/radar_broker/dispatch.py --level 8 --seed spread-1
uv run strategies/radar_broker/lift_only.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/radar_broker/dispatch.py strategies/all_in/dispatch.py --jobs 4
```

Its weeks are saved with the policy `radar-broker`, and those of `lift_only.py` with `radar-lift`. The `Radar` line at the end of a week counts the quotes surged up
and lowered, and gives the week's mean balance.

## What the weeks show

Played on the fresh seeds `nov-1` to `nov-9`, level 8, on 2026-11-14, against the saved `all_in` weeks of the same
seeds (the all-in system has not changed since they were played, and its `spread-1` week repeats to the cent).
`radar_broker` is the surge both ways; `lift_only` is the same surge with `surge_down = 0`, so it never cuts a price.
The surge both ways was played on the first five seeds only:

| Seed           | `all_in` | `radar_broker` | Difference | `lift_only` | Difference | On time (all in / radar / lift) |
| -------------- | -------- | -------------- | ---------- | ----------- | ---------- | ------------------------------- |
| `nov-1`        | €14,093  | €13,460        | −633       | €14,243     | +150       | 97.7% / 97.7% / 98.0%           |
| `nov-2`        | €19,376  | €17,664        | −1,712     | €18,530     | −846       | 95.3% / 97.0% / 96.1%           |
| `nov-3`        | €12,538  | €12,664        | +126       | €13,017     | +479       | 96.3% / 97.6% / 97.3%           |
| `nov-4`        | €15,852  | €14,732        | −1,120     | €14,238     | −1,614     | 99.7% / 98.8% / 99.1%           |
| `nov-5`        | €11,511  | €11,556        | +45        | €12,462     | +951       | 94.9% / 94.9% / 96.8%           |
| `nov-6`        | €16,988  |                |            | €16,678     | −310       | 98.7% / — / 98.6%               |
| `nov-7`        | €10,007  |                |            | €9,495      | −512       | 96.5% / — / 97.8%               |
| `nov-8`        | €16,743  |                |            | €15,258     | −1,485     | 97.7% / — / 97.6%               |
| `nov-9`        | €14,797  |                |            | €14,238     | −559       | 96.7% / — / 96.3%               |
| Mean of 1 to 5 | €14,674  | €14,015        | −659       | €14,498     | −176       |                                 |
| Mean of 1 to 9 | €14,656  |                |            | €14,240     | −416       |                                 |

Every week of both is ranked, and both win about as many orders as all-in.

- **The surge both ways** loses €659 a week and is ahead on 2 of the 5 seeds.
- **Lift only** loses €416 a week over the nine seeds and is ahead on 3 of them; it is behind on all four of
  `nov-6` to `nov-9`. The standard error of that mean difference is 284, so the loss is 1.5 standard errors: not
  certain, but nothing in the weeks points to a gain. On the first five seeds it made €483 a week more than the surge
  both ways, so the cut where our drivers will be free gave the most margin away.

Neither beats `all_in`. A price that follows our own backlog does not pay here, perhaps because the headroom pricing
already learns each lane's price from its wins and losses, and the fee schedules and direct offers already move our
drivers to the work. Play `all_in`, not these systems.

## The idea

A ride-hailing broker sets each ride's price from two live numbers in the rider's area: the riders waiting and the
cars nearby. A flight tracker shows where each plane will land and when. The desk already has both for its own fleet:

- **The radar.** The direct offers know where each of our drivers will finish our gig, and when: the last delivery
  place, about the drive after the first pickup, and the true place and minute once they deliver. A driver free more
  than 3 hours ago may have gone home and drops off the radar.
- **The supply** of a request: our drivers on the radar who finish within an hour's drive of its first pickup and can
  reach it before its pickup window ends. For them the car is the next gig of their day, which costs only the extra
  time and tickets.
- **The demand** of a request: our gigs that no driver holds yet, with a pickup within the same hour's drive and a
  last pickup minute in the next 18 hours. They wait for the same drivers.

## The surge

The area's balance is `log((demand + 1) / (supply + 1))`. The surge is

```text
surge = exp(0.06 x (balance - mean balance)), within -4.9% and +8.3%
```

where the mean balance is the week's running mean over our quotes (each quote weighs 2%). Measured from that mean, the
surge lifts as many prices as it lowers, so the learned multiplier of headroom pricing, which settles where 45% of the
quotes win, is not pulled along by it. It moves price from where our drivers are idle to where our work piles up:

- **Work piles up near the pickup**: the quote rises. We win fewer of those cars, which our drivers could not move
  cheaply or on time, and earn more on the ones we win.
- **Our drivers will be free near the pickup**: the quote falls a little. We win more of the cars that continue a
  driver's day, which the desk's chain offers then send to that driver.

The surge multiplies the lift of lane-prior pricing (dealer trust, the outage, the delivery place), so it moves the
price and the maximum alike, and the headroom maximum still learns from the quotes at it. Admission is all-in's,
unchanged: it weighs a request at the price without the surge, since whether a car pays is its own question and the
surge only sets what we ask for it. Up to level 3 every quote wins at the list price, so there is no surge.

## Variables

| Variable        | Default | What it sets                                                                     |
| --------------- | ------- | -------------------------------------------------------------------------------- |
| `radar_minutes` | 60      | Work and drivers within this drive of the pickup count for its area              |
| `fresh_minutes` | 180     | A driver free this long ago is off the radar                                     |
| `horizon`       | 1,080   | An open gig counts as demand when its last pickup minute is this close (minutes) |
| `surge_power`   | 0.06    | The power of the area's ratio in the surge                                       |
| `surge_up`      | 0.08    | The largest lift, in logs                                                        |
| `surge_down`    | 0.05    | The largest cut, in logs                                                         |
| `center_weight` | 0.02    | The weight of each quote in the week's mean balance                              |

The defaults are a first guess, not tuned; the weeks above show that they do not pay, and that the cut costs most.
