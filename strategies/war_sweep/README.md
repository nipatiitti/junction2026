# War sweep

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Its `WarSweepPricing` looks for level 8's
unannounced price war during the working day, temporarily caps quotes low enough to compete, and then removes the war
day's lessons. The rest of the desk is headroom's, including its admission capacity. Issue #252. Headroom and the root
system stay as they are.

| File          | Class             | Builds on         | What it decides                                      |
| ------------- | ----------------- | ----------------- | ---------------------------------------------------- |
| `pricing.py`  | `WarSweepPricing` | `HeadroomPricing` | Detects the war, caps its quotes and restores prices |
| `dispatch.py` | `Desk`            | the headroom desk | The same desk with war-sweep pricing                 |

## Run it

From the repository root:

```sh
uv run strategies/war_sweep/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `war-sweep`. The pricing summary reports a detected war, its win-share signal, the
number of capped quotes and the restore. No online weeks were played for this change.

## Detector

Only a Monday-to-Friday quote arriving from 08:00 (inclusive) to 18:00 (exclusive) can feed the detector. It uses
outcomes of quotes that could ordinarily win on price: quotes in the outage region and losses at the driver-cost floor
are excluded, because the outage has its own rule and a floor loss says the cost was too high rather than the learned
price. The detector has all of these conditions:

1. At least `war_losses` = 8 losses occur in the last `war_window` = 12 eligible outcomes of the day.
2. Today's eligible win share is at least `war_share_drop` = 0.20 below the pooled win share of earlier weekdays.
3. Those earlier weekdays supply at least `war_history` = 30 eligible outcomes.

Consequently Monday cannot be flagged: it has no earlier weekday to compare with. The existing headroom caller also
keeps one war a week and keeps it off the outage day. On a day that is not flagged, quoting and learning are exactly
headroom's.

**False positives are possible.** A busy day with no outage can produce an unlucky cluster of losses and a low win
share without a competitor price war. The system then lowers its margin until 18:00 on that day. Raising the loss,
window, history or share-drop thresholds makes detection more conservative.

## Cap, capacity and restore

- While flagged, every quote is capped at list price × (1 + `war_markup`), with `war_markup` = 0.10 by default: 1.10
  times list. Dealer trust and the outage boost do not lift this temporary cap. Headroom's driver cost plus risk
  premium remains the floor; an option whose floor exceeds the cap is not priced, so the sweep never sells below it.
- Admission is unchanged. It checks whether the expected driver cost fits under the temporary cap and applies the
  same pickup-area capacity, on-time tightening and return-leg rules as headroom. There is no extra volume allowance.
- At detection, all of the day's learning is restored to its state before the first working-hours outcome: the world
  multiplier, pickup, delivery and dealer offsets, and headroom's moving maximum. Later war outcomes cannot lower it
  again. At 18:00, or the first later request, normal headroom pricing resumes with that restored state.

The detector, cap and restore thresholds are fields of the frozen `Params` dataclass in `pricing.py`, exported as
`WarSweepParams`.
