# Scarcity-priced ceiling

A dispatch system that combines the two leading systems of the bench: the quotes of
[`../ceiling/`](../ceiling/README.md) and the scarcity-priced admission of [`../scarcity_cost/`](../scarcity_cost/README.md).
Issue #176.

It is built the way `strategies/ceiling` is: the root `dispatch.py` with its admission and pricing replaced by subclasses
of `Strategy` ([`../strategy.py`](../strategy.py)). Everything else (the loop, posting, fees, bundling, notes, retries,
direct offers, the final) is the root system's, so improvements there reach this system too. The root `dispatch.py` and
the folders of `strategies/` stay as they are.

| File           | Class                    | Builds on                              | What it decides                                                         |
| -------------- | ------------------------ | -------------------------------------- | ----------------------------------------------------------------------- |
| `admission.py` | `ChainScarcityAdmission` | `ChainAdmission` + `ScarcityAdmission` | Which requests to take: scarcity-raised cost, no gate, timed return leg |
| `dispatch.py`  | `Desk`                   | the root `Desk`                        | The system: the root desk with that admission and `CeilingPricing`      |

The quote is `CeilingPricing` from `strategies/ceiling`, unchanged.

## Run it

From the repository root, like the root `dispatch.py`, with the same options (`--level`, `--seed`, `--board`,
`--final`):

```sh
uv run strategies/scarcity_ceiling/dispatch.py --level 8 --seed spread-1                     # a practice week
uv run python -m strategies.bench strategies/scarcity_ceiling/dispatch.py dispatch.py --jobs 4
```

Its weeks are saved like the root system's (`tools/record.py`), with the policy `scarcity-ceiling`, so they form their
own group in `out/spread.sqlite`.

## What it combines

The two changes meet at one seam: the ceiling's floor is the admission's expected driver cost, and the scarcity
admission changes exactly that number.

- **The ceiling** ([`../ceiling/`](../ceiling/README.md), #64) quotes at most the list price × 1.39, lifted by dealer
  trust and the outage, never below the driver cost × (1 + `risk_premium`), and declines when that floor is above the
  maximum. It also times the return leg: a car counts as one only when one of our transports reaches it in time.
- **The scarcity cost** ([`../scarcity_cost/`](../scarcity_cost/README.md), #148) multiplies the expected fee by
  `1 + risk(pickup)`, with `risk = min(cap, safety × quotas per driver a day)`: how contested the town is over the
  whole market, which our own waiting cars cannot see. It drops the hard capacity gate, so a contested town is paid
  for rather than refused.

So here the scarcity premium raises the ceiling's floor: a contested town is quoted higher, and a request whose
scarcity-raised cost does not fit under the (possibly lifted) maximum is declined. That is the thing to watch: the two
changes overlap on the decline decision, so their gains need not add up. The bench below says what they do.

`ChainScarcityAdmission` is the two strategies combined, not a copy of either: the two changes sit in different methods
of the shared admission, and the class inherits from `ChainAdmission` and `ScarcityAdmission` at once (see the module
docstring in `admission.py`).

## The variables

`CeilingPricing` keeps its params (`max_markup`, `risk_premium`, …) in
[`../ceiling/pricing.py`](../ceiling/pricing.py). `ChainScarcityAdmission`'s `Params` is the sum of the two it combines:
the return-leg thresholds of `strategies/ceiling` (`near`, `wait`, `back`, `spare`) and the scarcity term of
`strategies/scarcity_cost` (`safety`, `cap`), each with its own folder's default.

## Ablation

The two parents are the ablation: benching `strategies/ceiling` on the same seeds shows the quote and the return leg
alone, and `strategies/scarcity_cost` shows the scarcity cost and the gate change alone.

## Bench

Level 8, seeds `spread-1` to `spread-5`, all four systems in one run
(`uv run python -m strategies.bench strategies/scarcity_ceiling/dispatch.py dispatch.py strategies/ceiling/dispatch.py strategies/scarcity_cost/dispatch.py --jobs 2`).
Every week is saved in `data/scrape/runs/L8/` under its own policy.

| Seed      | scarcity_ceiling |        ceiling |  scarcity_cost |           root |
| --------- | ---------------: | -------------: | -------------: | -------------: |
| spread-1  |        €8,423.51 |      €9,831.09 |      €8,884.43 |      €8,063.40 |
| spread-2  |        €6,135.52 |      €6,673.95 |      €6,921.35 |      €6,155.98 |
| spread-3  |        €3,173.78 |      €4,312.02 |      €3,404.74 |      €3,390.99 |
| spread-4  |        €8,323.34 |      €8,147.90 |      €7,838.25 |      €7,982.92 |
| spread-5  |        €5,327.33 |      €5,621.42 |      €5,899.53 |      €6,251.68 |
| **Total** |   **€31,383.48** | **€34,586.38** | **€32,948.30** | **€31,844.97** |

Orders won and the share on time over the five weeks:

| System             | Orders | On time |
| ------------------ | -----: | ------: |
| `scarcity_ceiling` |  1,402 |   98.1% |
| `ceiling`          |  1,602 |   97.7% |
| `scarcity_cost`    |  1,577 |   98.0% |
| `dispatch.py`      |  1,703 |   97.5% |

**The combination does not beat either parent, and it is about €460 behind the root.** It is higher than `ceiling` on
1 of the 5 seeds, and higher than `scarcity_cost` on 1 of the 5, so the result is not one seed's accident. The reason is
the overlap the two changes share: the scarcity term raises the expected driver cost, and the ceiling's admission
declines every request whose cost plus the risk premium does not fit under the maximum. The two levers compound into
**fewer cars** rather than higher prices — it wins 1,402 orders against 1,703 for the root and 1,602 for `ceiling` —
and the scarcity premium only pays off where the maximum is lifted (dealer trust, the outage), which is too rarely.
The quote, the half that `scarcity_cost` left to the ladder, stays the ceiling's, so the scarcity premium mostly
turns into declines.

A tuned version (a smaller `risk_premium` in the quote, or a smaller `safety` in the admission, so the two do not
double-count) may recover some of it; that is the follow-up. As it stands, `ceiling` or `scarcity_cost` alone is the
better system.
