# Scarcity-priced admission

A folder that builds on the shared strategies, the way [`../baseline/`](../baseline/README.md) and
[`../price_ladder/`](../price_ladder/README.md) do: its own copy of the dispatcher and one `Strategy` subclass, so
the root `dispatch.py` and `strategies/admission` stay as they are. Issue #148.

| File           | What it holds                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------------ |
| `dispatch.py`  | A copy of the root `dispatch.py` that admits with the strategy below                                         |
| `admission.py` | `ScarcityAdmission`: the admission of `strategies/admission`, with the town's scarcity priced in and no gate |

## Run it

From the repository root, like the root `dispatch.py`:

```sh
uv run strategies/scarcity_cost/dispatch.py --level 8 --seed spread-1                       # a practice week
uv run python -m strategies.bench strategies/scarcity_cost/dispatch.py dispatch.py --jobs 4 # against the root system
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `scarcity-cost` instead of `dispatch`.

## What it changes

Two parts of the base admission are replaced.

**A scarcity term is added to the expected fee.** The base's expected fee is the typical fee × its supply, hour,
note and return-leg factors × a flat 1.15 at levels 7 and 8 (the shortage everywhere at those levels). Here it is
that estimate × `1 + risk`, with

```
risk(place) = min(cap, safety × quotas(place) / days / drivers(place))
```

- `quotas(place)` is the price requests we have seen whose pickup is that place, from `observe`;
- `days` is the days of the week seen so far, so a rate is projected rather than the raw count;
- `drivers(place)` is the roster's head count living there, loaded once from `world.roster()`;
- `safety` (0.05) stands for drops, no-shows and, in the final, other teams bidding for the same drivers;
- `cap` (0.5) bounds the term.

So it is **quotas per driver per day** — how contested the town is — not our own load: a town we win little of is
still contested, and our won cars cannot see that. On the saved level-8 weeks the towns run from about 1 quota per
driver a day (Hämeenlinna, Seinäjoki, Helsinki) to 11 (Vantaa), so `risk` runs from about 0.05 to the cap. With
`safety = 0` the cost is exactly the base's and the only change left is the gate below.

**The hard capacity gate is gone.** The base declines a request when an area's waiting cars reach `0.10 × supply`.
Here the area's load is never a reason to decline: a contested town has to be paid for, and the quote decides. A
request is declined only when the quote does not cover `expected_cost × (1 + min_margin)`.

**The posted fee is not clamped by the estimate.** `strategies/fees` still plans each gig's schedule up to the
quote's ceiling (the order's price plus half of it), and may pay past `expected_cost`: at some point we go over the
estimate and take the loss on that order rather than leave the car, whose penalty is twice its price and an on-time
share the whole week cannot afford to lose.

## Tuning

`safety` and `cap` are placeholders. The data that would fit them is the random-fee weeks
(`scrape.py --policy explore --fee-shape flat`) and `probe.py fee` rows, which say what fee a driver books at and
whether a contested town raises it; neither is in the plain checkout. The row values above are from `town_days` in
the saved weeks.
