# Outage-region harvest

A dispatch system built on [`strategies/headroom`](../headroom/README.md). Its admission reserves driver capacity for
requests touching the region flagged by the existing outage detector, and its pricing sets the opening backup markup.
Headroom and the systems it builds on stay as they are.

| File           | Class             | Builds on           | What it decides                                   |
| -------------- | ----------------- | ------------------- | ------------------------------------------------- |
| `admission.py` | `OutageAdmission` | `LaneCostAdmission` | Which requests may use an outage area's capacity  |
| `pricing.py`   | `OutagePricing`   | `HeadroomPricing`   | The opening outage markup, learned as in headroom |
| `dispatch.py`  | `Desk`            | the headroom desk   | The system, with one outage flag shared by both   |

Both strategies are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) through their base classes,
with frozen `Params` dataclasses. The desk passes its pricing model to admission, so there is only one outage detector.

## Run it

From the repository root:

```sh
uv run strategies/outage_harvest/dispatch.py --level 8 --seed spread-1
```

Its weeks are saved with the policy `outage-harvest`. No online benchmark has been run for this system.

## The strategy

The detector is unchanged from [`strategies/pricing`](../pricing/README.md): a run of wins flags one region for the
current day. The region is its town and the places within 80 km. This system acts on that flag only from 08:00 until
18:00; it does not predict an outage before the detector fires.

1. **Reserve half of shared areas.** With `region_reserve = 0.5`, a request outside the region whose pickup is within
   the admission area (60 road minutes by default) of any region place can use only half the area's usual capacity.
   Both `capacity_per_driver` and `min_capacity` are halved. A request with any leg's pickup or delivery in the region
   can use the full headroom capacity, including the reserved half. The reserve therefore concentrates supply without
   increasing the area's total capacity.
2. **Decline low-margin outside work.** An outside request sharing those drivers must also leave `outside_margin`,
   25% of its price by default. The usual driver-cost and option checks still apply.
3. **Quote the backup premium.** `OutagePricing` starts ceiling's existing outage uplift at `1 + outage_markup`, or
   1.30 by default. The uplift raises both the learned price and its maximum. Outcomes move it with the base rule,
   between 1.0 and 1.5. As in the base pricing, a quote receives this uplift when its first pickup is in the region.
4. **Release at the end of the outage.** At 18:00, on another day, or if pricing's outage flag is absent, admission
   uses the unmodified headroom capacity and margin. There is no reserve to carry over. Outside an active flag the
   system makes the same admission and pricing decisions as headroom.

Requests already held before the flag are not cancelled. A false-positive flag can consequently reserve space that
region requests never use and decline profitable outside work, stranding drivers until the 18:00 release. The 50%
reserve is a policy default, not a fitted or performance-tested value.

## The variables

`OutageParams` in `admission.py` extends the lead-cost admission's frozen parameters. `OutagePricingParams` in
`pricing.py` extends headroom's.

| Variable         | Default | What it does                                                       |
| ---------------- | ------- | ------------------------------------------------------------------ |
| `region_reserve` | 0.5     | The share of a shared area's capacity reserved for region requests |
| `outside_margin` | 0.25    | The minimum price share left by an outside request sharing drivers |
| `outage_markup`  | 0.3     | The opening backup markup before the base uplift learns            |
