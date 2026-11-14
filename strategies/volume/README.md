# Volume

A dispatch system built on [`strategies/all_in`](../all_in/README.md): its `Desk` is a subclass of the all-in desk
that quotes every option of a request that pays its own driver cost, and counts a remote pickup's driver cost as the
saved weeks paid it. Issue #304; [`docs/volume-gap.md`](../../docs/volume-gap.md) has the analysis behind it.
`all_in` and the systems under it stay as they are.

| File           | Class             | Builds on        | What it decides                                                        |
| -------------- | ----------------- | ---------------- | ---------------------------------------------------------------------- |
| `admission.py` | `VolumeAdmission` | `AllInAdmission` | The option menu, and a remote pickup's driver cost                     |
| `pricing.py`   | `VolumePricing`   | `PriorPricing`   | Each option's price over its own driver cost, and the menu's win share |
| `dispatch.py`  | `Desk`            | the all-in desk  | The system: those two, with each option's cost passed to pricing       |

## Run it

From the repository root:

```sh
uv run strategies/volume/dispatch.py --level 8 --seed spread-1
```

Offline, against the simulator (`sim/README.md`), with nothing saved:

```sh
node sim/server.ts --port 8787
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim SPREAD_RECORD=0 uv run strategies/volume/dispatch.py --level 8 --seed nov-1
```

Its weeks are saved with the policy `volume`. The `Option menu` line at the end of a week counts the quotes with
added options and the won orders that took one.

## The strategy

1. **The option menu** (`VolumeAdmission.menu`). `all_in` quotes one option per request, the one admission picks,
   though about 500 requests a week offer two or three. Here an accepted request also gets every other option that
   passes admission's own tests at its own driver cost (`lead_cost`): the slack beyond the drive (the flu guard's
   options stay off) and the minimum margin at the highest price we would quote. The dealer takes the quoted option
   with the most headroom over its limit, so each option is one more chance to win at the same price.
2. **Prices per option** (`VolumePricing.price`). Each option gets ceiling pricing's price for its own list price,
   between its own driver cost × 1.1 and the maximum, not over the cost of admission's pick. A faster option is never
   cheaper than a slower one.
3. **The menu's win share.** A quote with more than one option aims at 50% of its quotes, not 45%. At 45% the learned
   price would take the extra wins back as a higher price.
4. **Remote pickups** (`scarce_pickup` 0.4, not 0.8). The lead-cost admission raises a pickup's cost by
   `scarce_pickup × e^(−supply / 15)` where few drivers live near it. The saved weeks paid 0.68 of the expected cost at
   a supply of 5–15, below the rest on 26 of 27 seeds; with 0.4 the realised cost is flat across supply.

## On the simulator

Paired against `all_in` on the same seeds, level 8, on 14 November. "Corrected" is the simulator with the
competitor's answer that `docs/volume-gap.md` measured (`SIM_PARAMS` with `compHi` 0.70, `compF`
`[0.065, 0.057, 0.027, 0, -0.022, -0.065, -0.101]`, `latePenalty` 0.025); "stock" is `sim/params.json`.

On 30 fresh seeds (`sweep-*`, the 21st to 50th pack), after the choice below:

| Simulator | `all_in` | `volume` | Difference       | Better on | Orders    | On time       |
| --------- | -------- | -------- | ---------------- | --------- | --------- | ------------- |
| Corrected | €13,485  | €15,267  | +€1,782 (se 210) | 29 of 30  | 338 → 375 | 96.9% → 97.0% |
| Stock     | €13,945  | €15,349  | +€1,404 (se 234) | 26 of 30  | 345 → 379 | 96.9% → 96.9% |

About 35 more orders a week, at a slightly higher margin per order (€39.9 → €40.7 on the corrected simulator).

The choice was made on 30 other seeds (`nov-1` to `nov-10` and the first 20 `sweep-*` packs). There this system
made +€1,509 a week against `all_in` on the corrected simulator (better on 27 of 30) and +€665 on the stock one
(21 of 30). What each change adds to the week, with the rest of the system in place:

| Change                                                          | Corrected | Stock   | Kept |
| --------------------------------------------------------------- | --------- | ------- | ---- |
| The option menu                                                 | +€1,150   | +€631   | yes  |
| The menu aiming at 50%, not 45%                                 | +€357     | +€224   | yes  |
| The menu aiming at 50%, not 55% (6–10 orders fewer)             | +€71      | +€1     | yes  |
| The remote-pickup cost                                          | +€282     | +€273   | yes  |
| Long lanes (list €60 or more) aiming at 50%, 55% at the maximum | −€747     | −€572   | no   |
| Room for 3 waiting cars of a long lane, not 2                   | −€31      | +€98    | no   |
| A win at the driver cost floor teaches nothing                  | +€60      | not run | no   |
| The menu on long lanes only, not on every lane                  | −€386     | not run | no   |

The long-lane win share lost on both, as `q-high50` did on the server (`docs/volume-gap.md`). The room and the floor
rule are within noise, and with the floor rule one week fell to 89.4% on time.

## Before the final

This system has not been played on the server. The simulator runs about €2,500 a week high and is too gentle on
overload, and its dealers take any quoted option under its limit, a rule fitted almost only on single-option quotes.
On the server, `strategies/option_menu` (slower options only, on the older `ceiling` desk, at a 45% win share) lost
€1,226 over three seeds. A paired run against `all_in` on a few fresh seeds on the server should decide it, and check
the on-time share.

## The variables

`Params` in `admission.py`, exported as `VolumeParams`: the all-in admission's, with `scarce_pickup` 0.4 and `menu`
True. `Params` in `pricing.py`, exported as `VolumePricingParams`: lane-prior pricing's, with `menu_target_win` 0.50.
A subclass of the `Desk` can set its class attributes `admission_params` and `pricing_params` to play other values.
