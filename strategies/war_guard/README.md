# War guard

A dispatch system built on [`strategies/ceiling`](../ceiling/README.md): its `Desk` is a subclass of the ceiling
desk with admission and pricing that know the two days level 8 does not announce, the price war and the outage.
Issue #187. Ceiling and the root system stay as they are.

| File           | Class               | Builds on        | What it decides                                                   |
| -------------- | ------------------- | ---------------- | ----------------------------------------------------------------- |
| `pricing.py`   | `WarGuardPricing`   | `CeilingPricing` | Forgets the war's lessons for its lanes; the outage starts at 1.3 |
| `admission.py` | `WarGuardAdmission` | `ChainAdmission` | More room in the outage region; optionally a war-day margin       |
| `dispatch.py`  | `Desk`              | the ceiling desk | The system: tells admission the war price and the outage          |

## Run it

From the repository root:

```sh
uv run strategies/war_guard/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/war_guard/dispatch.py strategies/ceiling/dispatch.py --jobs 2
```

Its weeks are saved with the policy `war-guard`. The pricing line adds the day the war was flagged and how many of
its outcomes were taken back; the admission line counts the war day's and the outage's verdicts.

## The strategy

Ceiling pricing (through `strategies/pricing`) flags both days from our wins and losses.

1. **The war's lessons for the lanes.** The war is flagged only once the world's multiplier has fallen 0.15 in logs
   below the day's opening, with losses on 6 pickups. Until then every war loss also lowers its pickup's, delivery's
   and dealer's offset by 0.75% in logs. At 18:00 ceiling sets the world's multiplier back to the day's opening, but
   the offsets stay down, so the next days quote those lanes and dealers lower for a war that is over. Here, when the
   war is flagged, the day's outcomes give back what they moved on the offsets, as the outage detector already does
   for its region. The world's multiplier still follows the war, and goes back at 18:00.
2. **The outage's boost.** Dealers in the outage region turn to a backup about 30% dearer than the competitor, so the
   boost starts at `outage_boost` = 1.3 (ceiling: 1.2), and learns up to 1.5 as before.
3. **Room in the outage.** Each area in the outage region holds `outage_capacity` = 1.5 times its usual cars, so more
   of those dearer requests are taken.
4. **The war-day margin, off.** With `war_margin` set, admission checks the margin at the war price and takes a
   request only with that share of it left. It is `None` by default, for the reason below.

## Offline replay

`analysis.replay`'s quote replay with this desk on the ten distinct saved `ceiling` weeks.

- The first version of this folder declined war-day requests below a 30% margin at the war price: 1,108 of the
  1,247 war-day requests of the ten weeks. The 230 orders it gave up had earned €15 each in those weeks, against €20
  for an average order: thinner, but paid, because ceiling's driver cost floor keeps the war day's prices above
  cost. Kept margin fell from €65,680 to €62,144, and every margin tried lost money: €64,385 at 0%, €64,281 at 10%,
  €63,337 at 15% and €62,849 at 20%. So the war-day margin is off, and the war rule is now the offsets' undo.
- As it is, the war is flagged in 9 of the 10 weeks, on Wednesday to Friday, and 11 to 87 of the day's outcomes are
  taken back. The same orders are kept (3,232 of 3,233, €65,676). The outage takes 0 to 60 requests a week. What the
  undo and the outage earn depends on quotes the weeks did not make, so the bench below measures them.

On the five distinct saved `scarcity-ceiling` weeks, which ceiling pricing quoted over another admission (seeds
`spread-1` to `spread-5`; the two `spread-1` weeks are the same week), the war is flagged in all five, on Wednesday to
Friday, and 12 to 38 of the day's outcomes are taken back. The same 1,327 orders are kept. The outage takes 0 to 49
requests a week.

## Bench

`strategies.bench` on 2026-11-14 at level 8, in one run with `ceiling` and the root `dispatch.py` (€17,610.37 in total)
on the same seeds. Every week was ranked. The weeks are saved under `data/scrape/runs/L8/` with the policy `war-guard`.

| Seed       |  `ceiling` | `war_guard` | Difference | On time |
| ---------- | ---------: | ----------: | ---------: | ------: |
| `spread-1` |  €9,831.09 |  €10,223.10 |   +€392.01 |   98.5% |
| `spread-2` |  €6,673.95 |   €6,511.15 |   −€162.80 |   96.5% |
| `spread-3` |  €4,312.02 |   €4,358.12 |    +€46.10 |   99.2% |
| Total      | €20,817.06 |  €21,092.37 |   +€275.31 |         |

Ahead of ceiling by €275.31 in total, on two of the three seeds. Matched by order id with ceiling's weeks, it won nearly
the same cars (23 orders that ceiling did not, and 33 fewer), and the orders that both won made €215 more; 96 of its
orders lost money against 102 for ceiling. On `spread-2` its on-time share fell to 96.5%, and late refunds over the
three weeks were €554 against €407. The lead is under 1.5% on three seeds, too small to tell from the week's own noise.
