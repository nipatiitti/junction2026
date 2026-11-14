# Lead-cost admission

A dispatch system built on [`strategies/dawn_fees`](../dawn_fees/README.md): its `Desk` is a subclass of the
dawn-fees desk whose admission takes the driver cost of a request from its lead times. Issue #200. The systems it
builds on stay as they are.

| File           | Class               | Builds on          | What it decides                                              |
| -------------- | ------------------- | ------------------ | ------------------------------------------------------------ |
| `admission.py` | `LeadCostAdmission` | `ChainAdmission`   | Which requests to take, at which option, and what they cost  |
| `fit.py`       |                     |                    | Measures the cost table on the saved weeks                   |
| `dispatch.py`  | `Desk`              | the dawn-fees desk | The system: the dawn-fees desk with the admission above      |

`LeadCostAdmission` is a subclass of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through `ChainAdmission`,
with the same constructor `(roster, world_map, level=8, params=None)` and a frozen `Params`.

## Run it

From the repository root:

```sh
uv run strategies/lead_cost/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/lead_cost/dispatch.py strategies/dawn_fees/dispatch.py --jobs 2
uv run python -m strategies.lead_cost.fit     # the cost table, from out/spread.sqlite
```

Its weeks are saved with the policy `lead-cost`. Its admission lines add how many quotes went to each option.

## What the saved weeks show

Admission's driver cost (`strategies/admission`) is the typical fee × 1.15, scaled by the drivers near both ends, the
hour, private addresses and the note. It does not know how long the car can wait. `fit.py` measures what the 9,139
delivered one-order orders of the 31 saved weeks really cost (driver fees, failed visits, waiting, release fees and
late refunds), over their typical fee, by the hours from the post to the order's `lastPickupAt` and to the car's ready
time, at dealer sites:

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

The table was measured under the fee schedule of `strategies/fees`. Under dawn fees the cars with a night to wait cost
less; run `fit.py` again with `--policy lead-cost,dawn-fees` once those weeks are saved, and update `Params.cost`.

## The variables

`Params` in `admission.py`, exported as `LeadCostParams`, next to those of `strategies/ceiling` and
`strategies/admission`.

| Variable            | Default                  | What it does                                                    |
| ------------------- | ------------------------ | --------------------------------------------------------------- |
| `last_pickup_hours` | 8, 14, 24, 36, 60        | The upper ends of the rows of `cost`; the last row is open      |
| `ready_hours`       | 3, 8                     | The upper ends of its columns; the last column is open          |
| `cost`              | the table above          | The driver cost over the typical fee, at a dealer site          |
| `private_pickup`    | 1.05, 1.30, 1.30         | What a private pickup multiplies it by, for each column         |
| `private_delivery`  | 1.03, 1.10, 1.10         | The same for a private delivery                                 |
| `scarce_pickup`     | 0.8                      | The share added where no driver lives near the pickup           |
| `scarce_delivery`   | 0.3                      | The share added where none lives near the delivery              |
| `short_drive`       | 30 minutes               | A drive under this is `short_cost` dearer over its typical fee  |
| `short_cost`        | 1.12                     |                                                                 |
| `premium_cost`      | 1.10                     | A premium car                                                   |
| `note_cost`         | 1.05                     | A note that asks for something a driver can miss                |
| `return_leg`        | 0.95                     | A timed return leg of one of our transports                     |
