# Trust farming, then harvest

A dispatch system built on [`strategies/headroom`](../headroom/README.md). For a few busy dealers it deliberately
buys dealer trust with discounted, easy orders, then stops discounting and uses headroom's full trust uplift. The
headroom desk and every other system stay unchanged. Issue #246.

| File           | Class                | Builds on           | What it decides                                          |
| -------------- | -------------------- | ------------------- | -------------------------------------------------------- |
| `pricing.py`   | `TrustFarmPricing`   | `HeadroomPricing`   | The farm set and phase, and the discounted farm quote    |
| `admission.py` | `TrustFarmAdmission` | `LaneCostAdmission` | Which farm-phase orders are easy enough to take          |
| `dispatch.py`  | `Desk`               | the headroom desk   | Connects the two strategies and times new gigs' bookings |

Both strategies have the usual constructor and a frozen `Params` dataclass.

## Run it

From the repository root:

```sh
uv run strategies/trust_farm/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `trust-farm`. No online week has been played for this strategy; the defaults below
are design choices, not tuned results or performance claims.

## Trust from our own account

At level 8 a dealer counts up to 25 of our on-time orders and accepts 1% more per counted order. `TrustFarmPricing`
uses headroom's reconstruction from our own ledger:

- an `order_won` event remembers the order's dealer;
- a **revenue** line is initially unsettled; once a later event arrives without a late refund for that order, it counts
  as on time and adds one, capped at 25;
- a **late refund** or **undelivered penalty** instead settles the order as late and halves the dealer's current count
  with integer division.

No external trust value is read. The same reconstructed count drives both the phase decision and ceiling pricing's
existing trust uplift.

## The two phases

Pricing counts requests per dealer and, at each quote, selects the `farm_dealers` = 3 with the most requests so far
(dealer id breaks ties). Only level 8 has the farm phase.

**FARM.** A selected dealer below `farm_target` = 10 counted orders gets a discount through the end of
`farm_until_day` = day 2 (Wednesday; Monday is day 0). Both the learned price and the normal maximum are reduced so the
maximum before trust and outage lifts is lower by `farm_markup` = 0.10 of list price: for example, 1.39 becomes 1.29,
not 1.39 × 0.90. Headroom's expected driver cost plus its 10% risk premium remains the floor. Admission evaluates the
margin at this discounted ceiling, and ceiling pricing declines an option when that floor is above the maximum. A
quote at the deliberate farm cap does not move headroom's normal moving maximum; its outcome still teaches the learned
price.

**HARVEST.** At 10 counted orders the discount and easy-order filter stop. Ceiling pricing applies the full trust
uplift as usual, including when headroom's maximum itself moves. Passing Wednesday also ends farming, as does falling
out of the current busiest-dealer set. Dealers outside that set always behave exactly as headroom.

If a late order halves a selected dealer's count below 10, it automatically returns to FARM only while the Wednesday
cutoff has not passed. After the cutoff it keeps headroom prices rather than buying trust with too little week left to
harvest it.

## The easy-order filter

A discount grows trust only when the order arrives on time, so `TrustFarmAdmission` declines a selected dealer's
farm-phase request unless all three hold:

1. **Short drive.** At most `easy_drive` = 120 road minutes, including both legs of a trade-in.
2. **Fast pickup town.** At least `fast_share` = 50% of our gigs starting there booked within `quick` = 30 minutes.
   A town starts with `fast_prior` = 2 observations' weight, half quick and half slow, so an unseen town is eligible
   and the first orders can produce evidence. A booking, accepted direct offer or expiry resolves a timed gig; waiting
   longer than 30 minutes counts as slow.
3. **No risky note.** The same `risky_note` check as admission rejects notes about manual gearboxes, plates, payment or
   a deadline that a driver can miss.

All other headroom checks remain: area capacity, delivery slack, return legs, the lead-time driver cost and margin.
The easy-order filter applies only during FARM, not to other dealers or the harvest phase.

### Parameters

| Parameter        | File           | Default | Meaning                                                         |
| ---------------- | -------------- | ------- | --------------------------------------------------------------- |
| `farm_dealers`   | `pricing.py`   | 3       | Number of busiest dealers eligible for farming                  |
| `farm_target`    | `pricing.py`   | 10      | Reconstructed on-time count at which harvesting starts          |
| `farm_markup`    | `pricing.py`   | 0.10    | Markup removed from the normal pre-uplift ceiling while farming |
| `farm_until_day` | `pricing.py`   | 2       | Last zero-based day on which farming may run or resume          |
| `easy_drive`     | `admission.py` | 120     | Maximum road minutes of an easy farm request                    |
| `quick`          | `admission.py` | 30      | Minutes after a post within which a booking counts as quick     |
| `fast_share`     | `admission.py` | 0.5     | Minimum quick-booking share at the pickup town                  |
| `fast_prior`     | `admission.py` | 2.0     | Neutral observation weight for a town with little evidence      |

## The risk

The discount is an immediate cost, but trust is monetised only by later orders won from the same dealer. A dealer can
leave the busiest set, send few later requests, deliver too late to grow trust, or reach the target too near the end
of the week. In those cases the reduced margins are never recovered. The neutral fast-town prior can also admit a town
whose first gigs later prove slow. This system makes that trade-off explicit; it does not assume the trust bought will
pay back.
