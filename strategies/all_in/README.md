# All in

A dispatch system built on [`strategies/soft_top`](../soft_top/README.md): its `Desk` is a subclass of the soft-top
desk that plays every strategy of issue #200 that held over 22 weeks, with the fee variables that the same 22 weeks
moved. Issue #200. The systems it builds on stay as they are.

| File           | Class            | Builds on           | What it decides                                                |
| -------------- | ---------------- | ------------------- | -------------------------------------------------------------- |
| `admission.py` | `AllInAdmission` | `FluGuardAdmission` | The flu guard, with the variables of same-day quoting          |
| `fees.py`      | `AllInPlanner`   | `SoftTopPlanner`    | The soft-top schedule with a lower top, dawn fee and patience  |
| `dispatch.py`  | `Desk`           | the soft-top desk   | The system: those two, the lane-prior pricing, bundles on dawn |

Both classes are subclasses of `Strategy` ([`strategies/strategy.py`](../strategy.py)) with the constructor
`(roster, world_map, level=8, params=None)` and a frozen `Params`.

| Strategy of the desk | Folder                                              | What it adds to the headroom desk                          |
| -------------------- | --------------------------------------------------- | ---------------------------------------------------------- |
| `AllInPlanner`       | this folder, on [`soft_top`](../soft_top/README.md) | A top fee of 1.7, a dawn fee of 1.05, one hour of patience |
| `PriorPricing`       | [`lane_prior`](../lane_prior/README.md)             | A lift for each dear delivery place                        |
| `AllInAdmission`     | [`same_day`](../same_day/README.md)                 | The fastest option that still pays                         |
|                      | [`flu_guard`](../flu_guard/README.md)               | A guard against the week's flu day                         |
| `Desk.post_due`      | this folder                                         | The dawn schedule for a bundle of several orders too       |

## Run it

From the repository root:

```sh
uv run strategies/all_in/dispatch.py --level 8 --seed spread-1
uv run python -m strategies.bench strategies/all_in/dispatch.py strategies/soft_top/dispatch.py --jobs 4
```

Its weeks are saved with the policy `all-in`.

## How it was chosen

Three weeks could not rank the systems of issue #200 (`strategies/headroom/README.md`), so everything here was
compared on the same 22 weeks, `spread-1` to `spread-22` at level 8, each version against the same base on every seed.

1. **The base**: the soft-top desk with the lane priors, same-day quoting and the flu guard together (policy `k-all`)
   made €11,529 a week on average, against €11,272 for `soft_top` alone and €11,277 with the flu guard only,
   and all of its 22 weeks are ranked.
2. **One change at a time** on that base, 22 weeks each. The standard error is that of the mean difference over the
   seeds: a difference under twice it is within what chance gives.

| Change to the base                                   | Policy        | Mean week | Against the base | Standard error | Better on |
| ---------------------------------------------------- | ------------- | --------- | ---------------- | -------------- | --------- |
| A bundle's fees on the dawn schedule                 | `r-bundles`   | €11,878   | +349             | 76             | 17 of 22  |
| The fee at the last dawn 1.05, not 1.15              | `r-dawn105`   | €11,749   | +220             | 182            | 13 of 22  |
| The one raise to the hold fee after 1 hour, not 2    | `r-pat1`      | €11,731   | +202             | 136            | 12 of 22  |
| A top fee of 1.7, not 2.0                            | `r-top17`     | €11,683   | +154             | 146            | 13 of 22  |
| A top fee of 2.5                                     | `r-top25`     | €11,339   | -190             | 122            | 7 of 22   |
| The fee at the last dawn 1.30                        | `r-dawn130`   | €11,452   | -77              | 145            | 8 of 22   |
| A hold fee of 1.1, not 1.0                           | `r-hold110`   | €11,439   | -90              | 99             | 11 of 22  |
| The sprint ladder opens at 1.0, not 1.1              | `r-sprint100` | €11,522   | -7               | 197            | 14 of 22  |
| Room for half the unbooked orders in an area         | `q-cap10`     | €11,358   | -171             | 158            | 9 of 22   |
| Prices aim at 40% of the quotes, 45% at the maximum  | `q-low40`     | €11,463   | -66              | 165            | 12 of 22  |
| Prices aim at 50% of the quotes, 55% at the maximum  | `q-high50`    | €11,422   | -107             | 187            | 12 of 22  |
| A risk premium of 15% on the driver cost, not 10%    | `q-prem15`    | €11,308   | -221             | 178            | 6 of 22   |
| Every driver cost 8% higher                          | `q-108`       | €10,650   | -879             | 241            | 3 of 22   |
| Every driver cost 16% higher                         | `q-116`       | €9,456    | -2,073           | 395            | 2 of 22   |
| Driver costs up to 8% lower while gigs book cheaply  | `p-92`        | €11,236   | -293             | 249            | 10 of 22  |
| Driver costs up to 14% lower while gigs book cheaply | `p-86`        | €10,910   | -619             | 384            | 9 of 22   |

3. **What went in**: the four changes of the first four lines. Together they made €738 a week more than the base
   (standard error 180; more on 17 of the 22 seeds). Only the bundles are clear of chance on their own
   (4.6 standard errors). The other three each point the same way as their opposite (a top of 2.5, a dawn fee of 1.30)
   points down, so they went in together.
4. **What the table says besides.** Admission is where it should be: every driver cost 8% higher loses €879 a week,
   and costs up to 8% lower while gigs book cheaply lose €293. The win share is flat between 40% and 50% of the
   quotes. A higher fee at any point of the schedule (the top, the dawn, the hold) loses money.

## The strategy

1. **Fees** (`AllInPlanner`): the soft-top schedule with a top fee of 1.7 times the lane fee, 1.05 at the last dawn
   and the one raise to the hold fee an hour after the post.
2. **Bundles** (`Desk.post_due`): a gig with the cars of several orders gets the same dawn schedule. The root desk
   plans it with the schedule of `strategies/fees`, which rises to 1.38 times the typical fee within 3 hours and to its
   top at 22:00 the evening before.
3. **Pricing** (`PriorPricing`): headroom pricing with the lift for dear delivery places.
4. **Admission** (`AllInAdmission`): the flu guard on Friday and on the flu day, the fastest option that still pays,
   and the cost of a car to collect today on the sprint ladder.

## The variables

`Params` in `fees.py`, exported as `AllInFeeParams`, next to those of `strategies/dawn_fees`:

| Variable   | Default | What it does                                       |
| ---------- | ------- | -------------------------------------------------- |
| `top`      | 1.7     | The top fee over the lane fee                      |
| `dawn`     | 1.05    | The fee at the last dawn                           |
| `patience` | 1 hour  | How long the opening fee stays before the hold fee |

`Params` in `admission.py`, exported as `AllInParams`, is the sum of `FluGuardParams` and `SameDayParams`.

## A series of 22 weeks

Level 8, one week on each seed, saved under the policies `soft-top`, `flu-guard` and `all-in`:

| Seed         | `soft_top`     | `flu_guard`    | `all_in`       | Orders | On time |
| ------------ | -------------- | -------------- | -------------- | ------ | ------- |
| `spread-1`   | €13,297.12     | €13,115.78     | €13,591.71     | 369    | 99.2%   |
| `spread-2`   | €9,816.59      | €9,816.59      | €10,096.16     | 300    | 98.3%   |
| `spread-3`   | €5,297.53      | €5,297.53      | €5,825.61      | 239    | 98.3%   |
| `spread-4`   | €13,658.73     | €13,658.73     | €13,293.34     | 362    | 97.2%   |
| `spread-5`   | €7,161.91      | €7,438.73      | €7,922.44      | 283    | 95.8%   |
| `spread-6`   | €8,593.70      | €8,000.67      | €8,421.45      | 250    | 98.4%   |
| `spread-7`   | €10,709.46     | €10,709.46     | €13,299.12     | 314    | 99.7%   |
| `spread-8`   | €13,130.54     | €13,130.54     | €13,036.57     | 359    | 97.5%   |
| `spread-9`   | €14,054.62     | €14,054.62     | €16,048.08     | 319    | 99.1%   |
| `spread-10`  | €11,327.90     | €11,327.90     | €11,047.65     | 303    | 96.4%   |
| `spread-11`  | €9,276.08      | €9,276.08      | €10,164.49     | 285    | 97.5%   |
| `spread-12`  | €12,531.29     | €12,531.29     | €14,809.17     | 383    | 93.7%   |
| `spread-13`  | €9,952.94      | €9,952.94      | €11,011.03     | 269    | 97.8%   |
| `spread-14`  | €9,055.44      | €9,055.44      | €9,893.72      | 284    | 98.6%   |
| `spread-15`  | €9,920.60      | €10,418.71     | €10,508.12     | 305    | 98.0%   |
| `spread-16`  | €15,360.98     | €15,360.98     | €17,012.04     | 387    | 95.9%   |
| `spread-17`  | €13,268.32     | €13,268.32     | €14,035.52     | 333    | 98.8%   |
| `spread-18`  | €11,949.95     | €11,277.31     | €14,097.57     | 346    | 97.4%   |
| `spread-19`  | €14,720.82     | €14,355.02     | €17,328.38     | 360    | 98.3%   |
| `spread-20`  | €13,251.67     | €13,279.21     | €14,197.48     | 319    | 98.1%   |
| `spread-21`  | €10,588.55     | €11,693.15     | €10,604.20     | 335    | 91.0%   |
| `spread-22`  | €11,069.83     | €11,069.83     | €13,642.36     | 346    | 97.7%   |
| **Mean**     | **€11,272.48** | **€11,276.76** | **€12,267.56** | 320    |         |
| Over €12,000 | 9 of 22        | 9 of 22        | 12 of 22       |        |         |
| Ranked       | 21 of 22       | 22 of 22       | 22 of 22       |        |         |

`all_in` makes €12,268 in the mean week, €995 more than `soft_top` (standard error 211; more on 18 of the 22
seeds), and its weeks run from €5,826 to €17,328. 12 of the 22 weeks are over €12,000. Its lowest
on-time share is 91.0%.

**The world decides more than the system.** A week's margin follows the price level of its world: where the orders won
went at 1.34 times the list price (`spread-3`) the best system makes about €5,300, and where they went at 1.6 times it
makes €14,000 to €17,000. For comparison, in the level 8 ranking round "Saturday 09:00" the leading team's five weeks
made €10,735 to €20,883.
