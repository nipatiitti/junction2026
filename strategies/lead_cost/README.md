# Lead-cost admission

Admission whose driver cost comes from a request's lead times, for the systems of
[`strategies/headroom`](../headroom/README.md) and up. Issue #200. `strategies/admission`, `strategies/ceiling` and
the root system stay as they are.

| File           | Class               | Builds on        | What it decides                                             |
| -------------- | ------------------- | ---------------- | ----------------------------------------------------------- |
| `admission.py` | `LeadCostAdmission` | `ChainAdmission` | Which requests to take, at which option, and what they cost |
| `fit.py`       |                     |                  | Measures the cost table on the saved weeks                  |

`LeadCostAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `ChainAdmission`,
with the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`. A desk built on the
ceiling desk uses it in place of `ChainAdmission`. `LaneCostAdmission` of `strategies/lane_fee` is this admission on
the lane fee, and every system from `headroom` up plays with it.

```sh
uv run python -m strategies.lead_cost.fit                                  # the cost table, from out/spread.sqlite
uv run python -m strategies.lead_cost.fit --policy lane-fee,headroom       # the same, from the weeks of other systems
```

## What the saved weeks show

Admission's driver cost (`strategies/admission`) is the typical fee × 1.15, scaled by the drivers near both ends, the
hour, private addresses and the note. It does not know how long the car can wait. `fit.py` measures what the 9,139
delivered one-order orders of the 31 saved weeks that used the fee schedule of `strategies/fees` really cost (driver
fees, failed visits, waiting, release fees and late refunds), over their typical fee, by the hours from the post to
the order's `lastPickupAt` and to the car's ready time, at dealer sites:

| Hours to the last pickup | Ready within 3 hours | Ready within 8 hours | Ready later  |
| ------------------------ | -------------------- | -------------------- | ------------ |
| under 8                  | 2.41 (50 orders)     |                      |              |
| 8 to 14                  | 1.77 (139)           |                      |              |
| 14 to 24                 | 1.44 (99)            |                      | 1.06 (423)   |
| 24 to 36                 | 1.25 (1,989)         | 1.10 (74)            | 1.03 (2,212) |
| 36 to 60                 | 1.25 (31)            |                      | 1.05 (1,093) |
| 60 or more               | 1.20 (1,195)         | 1.06 (16)            | 1.13 (864)   |

A car that must be collected within 14 hours costs about twice its typical fee and lost money: −0.07 to −0.88 of its
typical fee. A car ready the next day costs 1.03. A private pickup costs 1.3 times a dealer site's in the same cell
when the car is ready 3 hours or more after the post, and a private delivery 1.1 times. After the table, the cost
still rises where no driver lives near the pickup (+43% in the scarcest class) and near the delivery (+8%), for a
drive under 30 minutes (+14%) and for a premium car (+11%).

## The strategy

1. **The cost of an option.** For each option of a request that leaves time for the drive, the cost is the typical
   fee × the table's cell. The row is the hours from the dealer's decision (`respondBy`) to the option's last
   pickup: its deadline less the drive, cut to the pickup site's stated hours, or the end of a private seller's
   slot. The column is the hours to the car's ready time.
2. **What is added.** × 1.05 to 1.30 for a private pickup, × 1.03 to 1.10 for a private delivery, × (1 + 0.8 ×
   scarcity) at the pickup and × (1 + 0.3 × scarcity) at the delivery, where scarcity is `exp(−supply / 15)` as in
   `strategies/admission`, × 1.12 for a drive under 30 minutes, × 1.10 for a premium car, × 1.05 for a risky note,
   × 0.95 for a timed return leg.
3. **The option.** Admission quotes the option that leaves the most margin: its list price × the price we would
   quote, less its cost. `same_day` is 8% dearer than `next_day` on the list, so a car ready tomorrow is quoted
   `same_day` (cost 1.03), and a car ready now, in the morning, `next_day` (cost 1.25, against 1.77 or more today).
4. **Decline what does not pay.** As in the ceiling system: when the cost plus the risk premium is above the highest
   price we would quote, the request gets ten times its list price. The area's capacity, the tightening by our
   on-time share and the timed return leg are unchanged.

5. **Room in an area.** An area holds 0.20 unbooked orders for each driver weight near it, and at least 2: twice
   the figures of `strategies/admission`. Under dawn fees a gig waits for its morning on purpose, so an order
   without a driver yet is not a sign that the area is full. In the first week with the old figures, Oulu alone was
   refused about 18 times with one order waiting.

### The table under dawn fees

The table above was measured under the fee schedule of `strategies/fees`. Under the dawn schedule a car with a night
to wait costs less. From the 4,404 orders of the 15 weeks played with dawn fees before the refit (`fit.py --policy
y-sprint,y-sprint-low,y-sprint-high,y-base,x-cap-lane,x-cap-lane-town`):

| Hours to the last pickup | Ready within 3 hours | Ready within 8 hours | Ready later  |
| ------------------------ | -------------------- | -------------------- | ------------ |
| 14 to 24                 | 1.26 (14 orders)     |                      | 1.04 (298)   |
| 24 to 36                 | 1.16 (747)           | 0.94 (27)            | 0.99 (1,445) |
| 36 to 60                 | 1.13 (16)            |                      | 0.97 (534)   |
| 60 or more               | 0.92 (652)           | 0.77 (12)            | 0.95 (367)   |

`Params.cost` still holds the first table. Played with these rows instead (2.40 and 1.77 kept for the cars to
collect within 14 hours, which those weeks hardly took, and 1.10, 1.00 and 0.97 in the last row), the headroom system
made €194 more on `spread-1`, €324 less on `spread-2` and €1,549 less on `spread-4`: €1,679 less over the three
weeks. A cheaper table takes more cars, and on `spread-4` more than drivers could move on time (95.9% on time against
97.7%). The first table is too high for a car with a night to wait, and that margin of safety is worth more than the
cars it turns away.

## The variables

`Params` in `admission.py`, exported as `LeadCostParams`, next to those of `strategies/ceiling` and
`strategies/admission`.

| Variable              | Default                   | What it does                                                       |
| --------------------- | ------------------------- | ------------------------------------------------------------------ |
| `last_pickup_hours`   | 8, 14, 24, 36, 60         | The upper ends of the rows of `cost`; the last row is open         |
| `ready_hours`         | 3, 8                      | The upper ends of its columns; the last column is open             |
| `cost`                | the table under dawn fees | The driver cost over the typical fee, at a dealer site             |
| `private_pickup`      | 1.05, 1.30, 1.30          | What a private pickup multiplies it by, for each column            |
| `private_delivery`    | 1.03, 1.10, 1.10          | The same for a private delivery                                    |
| `scarce_pickup`       | 0.8                       | The share added where no driver lives near the pickup              |
| `scarce_delivery`     | 0.3                       | The share added where none lives near the delivery                 |
| `short_drive`         | 30 minutes                | A drive under this is `short_cost` dearer over its typical fee     |
| `short_cost`          | 1.12                      |                                                                    |
| `premium_cost`        | 1.10                      | A premium car                                                      |
| `note_cost`           | 1.05                      | A note that asks for something a driver can miss                   |
| `return_leg`          | 0.95                      | A timed return leg of one of our transports                        |
| `slower_win`          | 1.0                       | The weight of an option's margin when the request has a faster one |
| `capacity_per_driver` | 0.20                      | Unbooked orders an area holds for each driver weight near it       |
| `min_capacity`        | 2.0                       | The least an area holds                                            |

## Played

Level 8, seed `spread-1`, each week saved in `data/scrape/runs` under the policy named. `dawn-fees` is the ceiling desk
with `DawnFeePlanner`; the others add this admission to it.

| What was played                                                      | Policy      | Margin     | Orders | On time |
| -------------------------------------------------------------------- | ----------- | ---------- | ------ | ------- |
| The ceiling desk with dawn fees                                      | `dawn-fees` | €9,923.03  | 372    | 97.6%   |
| With this admission, the first table and the capacity of `admission` | `lead-cost` | €11,591.16 | 380    | 98.7%   |
| With the capacity of this folder and the sprint ladder               | `a-lead`    | €11,704.12 | 407    | 98.0%   |

The admission added €1,668 to the week: driver fees fell from 1.09 to 1.04 times the typical fee, late orders from 7
to 4, and the quotes moved from `next_day` (196 to 154 orders) to `same_day` (182 to 229), the day the car is ready.
