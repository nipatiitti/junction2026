# Radar broker

A dispatch system built on [`strategies/all_in`](../all_in/README.md), the leading model of
[`active-models.md`](../../active-models.md): its `Desk` is a subclass of the all-in desk whose quotes surge with the
live balance of our work and our drivers near the pickup, as a ride-hailing broker prices a ride. Issue #300. The
systems it builds on stay as they are.

| File          | Class          | Builds on       | What it decides                                     |
| ------------- | -------------- | --------------- | --------------------------------------------------- |
| `pricing.py`  | `RadarPricing` | `PriorPricing`  | The all-in price of a quote, times the area's surge |
| `dispatch.py` | `Desk`         | the all-in desk | The system: the all-in desk with the pricing above  |

`RadarPricing` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `PriorPricing`, with
the constructor `(roster, world_map, level=8, params=None, radar=None)` and a frozen `Params`. `radar` is the desk's
`Offers` ([`strategies/offers`](../offers/README.md)); pricing reads it and never changes it.

## Run it

From the repository root:

```sh
uv run strategies/radar_broker/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/radar_broker/dispatch.py strategies/all_in/dispatch.py --jobs 4
```

Its weeks are saved with the policy `radar-broker`. The `Radar` line at the end of a week counts the quotes surged up
and lowered, and gives the week's mean balance. No online measurement was done for this version.

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

The defaults are a first guess, not tuned. A bench against `all_in` on the same seeds says whether the surge pays.
