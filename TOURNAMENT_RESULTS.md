# Tournament results (issue #186)

Level 8 practice weeks. Margin counts only when the week is ranked (90%+ of orders on time).
Strategy code sits in the agents' worktrees under `.claude/worktrees/` (branch `worktree-agent-<id>`), not on main.
Best ranked so far is marked **bold**.

## Reference: bidprice (on main, PR #162 merged)

| Variant | Seed | Margin | Orders | On time | Ranked | Fees paid |
| --- | --- | --- | --- | --- | --- | --- |
| defaults (comfortHours=0) | spread-1 | €10,003 | 487 | 89.1% | no | |
| defaults | spread-2 | €6,385 | 395 | 94.4% | yes | |
| defaults | spread-3 | €4,161 | 263 | 91.3% | yes | |
| costScale=1.3 | spread-1 | €9,749 | 257 | 97.3% | yes | |
| costScale=1.3 | spread-2 | €6,386 | 163 | 98.2% | yes | |
| costScale=1.3 | spread-3 | €1,314 | 65 | 96.9% | yes | |
| comfortHours=6 | spread-1 | €9,818 | 475 | 90.5% | yes | |
| **comfortHours=9** | spread-1 | **€9,923** | 467 | 92.1% | yes | 1.15 × typical |
| comfortHours=9,costScale=1.1 | spread-1 | €9,336 | 329 | 93.6% | yes | |
| comfortHours=9,feeSolver=false | spread-1 | €6,230 | 434 | 96.5% | yes | 1.29 × typical |
| comfortHours=12,costScale=1.2 | spread-1 | €7,449 | 216 | 96.8% | yes | 1.06 × typical |
| comfortHours=9,minValueCents=1500 | spread-1 | €2,402 | 53 | 94.3% | yes | 1.06 × typical |

Reading: the fee solver is worth about €3,700 a week (1.15 against 1.29 × typical). Fewer orders book cheaper.

## Round 1: eight independent strategies, first versions, spread-1

| Strategy | Idea | Margin | Orders | On time | Ranked | Worktree |
| --- | --- | --- | --- | --- | --- | --- |
| whale | trust farming on the big dealers | €5,730 | 347 | 93.4% | yes | agent-a3c2a57c85bf79bfd |
| thompson | monotone Thompson bandit on price | €6,443 | 375 | 89.3% | no | agent-a3331a61cd95c95e1 |
| shadow | competitor level filter | €5,674 | 434 | 85.9% | no | agent-ae5d44904715e542d |
| haggle | per-dealer feedback ladder | €4,056 | 442 | 87.8% | no | agent-af8d616e604bc3fb8 |
| plainmark | three markups, flat fee | €3,185 | 406 | 89.2% | no | agent-a43a5dde7d880e03f |
| cherry | score requests, take the best | −€1,599 | 520 | 69.4% | no | agent-aaad2363cfd2203f3 |
| skinflint | lowest driver fees, direct offers | −€1,837 | 494 | 70.4% | no | agent-acdc5c0352936a3e8 |
| dejavu | remembered thresholds per seed (overfit) | −€6,802 | 616 | 72.7% | no | agent-a8ece401cdd6e0678 |

Reading: seven of eight fail on on-time share, not on price: too many orders for the fee schedules they post.
Next: a shared base (`PricedStrategy`) that does admission, capacity brake, gig posting and rescue, so a strategy is
only a pricing function; then the pricing ideas go on it.

## Tools

- Offline arena (`src/arena.ts`, worktree agent-a33dd3ad8983d4fef): runs in 1 s a week but is not believable yet
  (bidprice 94 orders against 330-490 real). Not used for ranking.

## Shared base (`src/strategies/base/`, branch `tournament`)

`PricedStrategy` does admission, a capacity brake, gig posting, rescue ticks and trackers; a strategy is `price(ctx)`.

| Strategy | Seed | Margin | Orders | On time | Ranked |
| --- | --- | --- | --- | --- | --- |
| flat (20 lines) | spread-1 | €7,251 | 315 | 95.9% | yes |
| flat:comfortHours=6 | spread-1 | €6,836 | 336 | 96.7% | yes |

## Round 1: second versions (each agent's own retune), spread-1

| Strategy | Margin | Orders | On time | Ranked | Note |
| --- | --- | --- | --- | --- | --- |
| haggle | €6,310 | 347 | 94.2% | yes | target win rate 0.3; learned levels reached 1.92 × list pooled, D01 2.06, D02 2.03, D04 at the 2.2 cap |
| whale | €5,730 | 347 | 93.4% | yes | D01 reached trust 20 |
| plainmark | €3,185 | 406 | 89.2% | no | |
| dejavu | −€8,410 | 630 | 70.3% | no | its table was never recognised (`table=none`) |

Reading: haggle's levels say trusted dealers accept about 2 × list late in the week. Price, not volume, is the room.
| thompson (second version, added late) | €6,197 | 295 | 93.9% | yes | minSlack=240, costMult 1.35; about €21 an order |

## bidprice parameter search, round 1 (30 candidates, spread-1)

Full table: scratchpad `tune1.log`; state in `out/tune-*.json`. Best four, all ranked:

| # | Margin | On time | Params (others default) |
| --- | --- | --- | --- |
| 8 | **€11,866** | 92.8% | minValueCents=126 lateTrust=2 costScale=1.09 lateTarget=0.0282 comfortHours=6 topLeadHours=11.8 feeFloor=1.03 topRatio=1.28 staleHours=2.2 |
| 16 | €11,833 | 95.3% | war=decline minValueCents=284 lateTrust=0 costScale=1.16 lateTarget=0.0372 comfortHours=6 topLeadHours=9.49 feeFloor=0.908 topRatio=1.46 staleHours=3.29 |
| 27 | €11,459 | 96.7% | war=decline minValueCents=149 lateTrust=2 costScale=1.17 lateTarget=0.0499 comfortHours=9 topLeadHours=7.75 feeFloor=1.01 topRatio=1.58 staleHours=1.43 |
| 29 | €10,917 | 94.2% | minValueCents=461 lateTrust=0 costScale=1.19 lateTarget=0.0517 comfortHours=6 topLeadHours=4.02 feeFloor=0.939 topRatio=1.49 staleHours=3.92 |

Reading: every candidate with costScale under 1.0 is unranked or poor; the best four have costScale 1.09-1.19.

## Round 2: pricing ideas on the shared base, spread-1

| Strategy | Idea | Margin | Orders | On time | Ranked | Worktree |
| --- | --- | --- | --- | --- | --- | --- |
| groundhog | remembered thresholds per request from 101 saved weeks (overfit) | €8,041 | 246 | 98.4% | yes | agent-a7195e6497d349307 |
| surge | price rises with open-gig load and tight slack | €8,055 | 294 | 98.3% | yes | agent-a1fa50087a2340117 |
| surge (lower base, second try) | | €7,536 | 284 | 97.9% | yes | |
| tide (first) | weekday schedule + win-rate controller | €6,315 | 348 | 95.4% | yes | agent-a60cba8f6c005efc7 |
| tide (higher prices) | | €7,475 | 246 | 97.2% | yes | |
| gambit (first) | per-dealer belief filter with bluffs | €7,063 | 331 | 95.5% | yes | agent-ac111cb9bc4fa5622 |
| gambit (charge per driver slot) | | €7,485 | 242 | 97.9% | yes | |
| isotone (first) | monotone Thompson bandit on a price grid | €7,373 | 291 | 96.9% | yes | agent-ac6a56d2bfe8e95b1 |
| isotone (more volume) | | €6,604 | 338 | 96.2% | yes | |
| squeeze (first) | logistic price curve over dealer trust and size | €7,765 | 338 | 96.2% | yes | agent-a332186ba04cae9ec |
| squeeze (higher curve: 1.16 to 1.72) | | €8,021 | 317 | 97.5% | yes | |
| menu (winValue 0.04) | whole-menu design across options | €7,451 | 260 | 97.3% | yes | agent-a1f97c28ce854c758 |
| menu (winValue 0.12) | | €7,318 | 292 | 97.6% | yes | |
| atlas (target win 0.55) | price level per delivery town and region | €7,314 | 344 | 97.1% | yes | agent-a27b818feccbf29b9 |
| atlas (target win 0.25) | | €6,912 | 221 | 98.2% | yes | |

Reading: on the base every idea is ranked at 95%+ with spare capacity; all sit at €7-8k because the base pays drivers
on the ramp (about 1.29 × typical). The fee solver is being added to the base.

## bidprice parameter search, final round (spread-1 + spread-9): TARGET REACHED ON spread-9

| # | spread-1 | spread-9 | Mean | On time (mean) | Params |
| --- | --- | --- | --- | --- | --- |
| 16 | €11,833 | **€16,148** (97.4%) | €13,990 | 96.4% | war=decline minValueCents=284 lateTrust=0 costScale=1.16 lateTarget=0.0372 comfortHours=6 topLeadHours=9.49 feeFloor=0.908 topRatio=1.46 staleHours=3.29 |
| 8 | €11,866 | €15,574 (97.8%) | €13,720 | 95.3% | minValueCents=126 lateTrust=2 costScale=1.09 lateTarget=0.0282 comfortHours=6 topLeadHours=11.8 feeFloor=1.03 topRatio=1.28 staleHours=2.2 |
| 29 | €10,917 | €15,589 (97.5%) | €13,253 | 95.8% | minValueCents=461 lateTrust=0 costScale=1.19 lateTarget=0.0517 comfortHours=6 topLeadHours=4.02 feeFloor=0.939 topRatio=1.49 staleHours=3.92 |
| 27 | €11,459 | €13,171 (97.6%) | €12,315 | 97.1% | war=decline ... costScale=1.17 comfortHours=9 |

Best params file: `src/strategies/bidprice/tuned-16.json` (uncommitted). Play it:
`pnpm dispatch --strategy bidprice --params src/strategies/bidprice/tuned-16.json --level 8 --seed spread-9`.
The €16,148 week is world `w4b7ba7402a1f40c18e73`, saved under `data/scrape/runs/L8/spread-9/`.

## Base with the fee solver (branch `tournament`), spread-1

| Strategy | Margin | Orders | On time | Fees paid | Before the solver |
| --- | --- | --- | --- | --- | --- |
| flat | €9,199 | 319 | 95.6% | 1.16 × typical | €7,251 |
| squeeze | €9,509 | 321 | 95.6% | 1.17 | €8,021 |
| groundhog | €8,909 | 254 | 96.9% | 1.15 | €8,041 |
| surge | €8,870 | 269 | 97.0% | 1.13 | €8,055 |

## recall: tuned bidprice + remembered thresholds (overfit to practice seeds), spread-1

Worktree agent-a1fd7ff208016e814, branch `feat/recall-memory`. Falls back to plain bidprice on an unknown week.

| Params | Margin | Orders | On time |
| --- | --- | --- | --- |
| winShade 0.98, lossShade 0.97, minMargin 0.08 | €13,612 | 478 | 94.4% |
| winShade 0.99, lossShade 0.985 | €13,515 | 464 | 93.1% |
| lossShade 0.96, minMargin 0.05 (now default) | **€14,301** | 486 | 94.0% |

### recall after refreshing its memory (136 weeks of spread-1, 23 of spread-9), on branch `tournament`

| Params | Seed | Margin | Orders | On time | Fees paid |
| --- | --- | --- | --- | --- | --- |
| defaults | spread-9 | **€17,482** | 467 | 95.7% | 1.09 × typical |
| lossShade=0.95,minMargin=0.03 | spread-9 | €17,367 | 473 | 94.5% | 1.09 |
| defaults | spread-1 | €13,425 | 506 | 92.3% | 1.13 |
| lossShade=0.95,minMargin=0.03 | spread-1 | €11,765 | 525 | 91.8% | 1.15 |

Reading: on spread-1 more orders (506-525) cost on-time share and margin; fewer, fatter orders is the direction.

### recall with higher margin floors, spread-1

| Params | Margin | Orders | On time | Fees paid |
| --- | --- | --- | --- | --- |
| minMargin=0.12,lossShade=0.98,winShade=1 | **€14,826** | 470 | 94.5% | 1.11 × typical |
| minMargin=0.2 | €14,625 | 403 | 94.3% | 1.08 |
| minMargin=0.12 | €13,302 | 454 | 93.4% | 1.13 |
| minMargin=0.1,comfortHours=9 | €12,787 | 432 | 93.5% | 1.12 |

## Second bidprice search (24 candidates; spread-1, spread-9, spread-4), plain bidprice, no memory

| # | spread-1 | spread-9 | spread-4 | Mean | Params file |
| --- | --- | --- | --- | --- | --- |
| 6 | €12,934 (94.7%) | €15,240 (97.9%) | €11,987 (93.8%) | **€13,387** | `src/strategies/bidprice/tuned-6b.json` |
| 3 | €12,132 (96.6%) | €16,122 (98.6%) | €11,262 (95.7%) | €13,172 | costScale=1.19 feeFloor=1.01 topRatio=1.55 topFee=1.95 ... |
| 18 | €12,040 (93.5%) | €15,767 (96.7%) | €11,655 (95.0%) | €13,154 | costScale=1.22 feeFloor=0.89 topRatio=1.3 ... |
| 11 | €12,243 (92.5%) | €17,177 (98.1%) | €9,517 (93.3%) | €12,979 | costScale=1.13 comfortHours=4 ... |

#6: war=decline minValueCents=152 lateTrust=0 costScale=1.2 etaMu=0.01 lateTarget=0.0506 comfortHours=6 topFee=2.09
topLeadHours=11.8 feeFloor=0.961 topRatio=1.27 urgentTop=2.14 staleHours=2.76 dropStep=0.191 climbStep=0.132.
This one does not memorise seeds, so it is the candidate for the real final.

## recall on the second search's params: BOTH SEEDS OVER €15k

`T` = lossShade=0.98,winShade=1. `6b` = bidprice params of `tuned-6b.json`; otherwise `tuned-16.json`.

| Params | Seed | Margin | Orders | On time | Fees paid |
| --- | --- | --- | --- | --- | --- |
| **6b, minMargin=0.12, T** (saved as `src/strategies/recall/champion.json`) | spread-1 | **€15,618** | 439 | 92.9% | 1.12 × typical |
| **6b, minMargin=0.12, T** | spread-9 | **€19,399** | 405 | 96.8% | 1.06 |
| minMargin=0.12, T | spread-9 | €19,188 | 462 | 96.3% | 1.08 |
| minMargin=0.2, T | spread-9 | €18,989 | 408 | 97.3% | 1.05 |
| 6b, minMargin=0.2, T | spread-1 | €14,208 | 375 | 92.0% | 1.10 |
| minMargin=0.3, T | spread-1 | €14,208 | 367 | 95.9% | 1.09 |
| minMargin=0.16, T | spread-1 | €13,778 | 419 | 93.1% | 1.12 |
| minMargin=0.2, T | spread-1 | €13,575 | 400 | 93.5% | 1.13 |

Play the champion: `pnpm bench recall:src/strategies/recall/champion.json --level 8 --seeds spread-1,spread-9`.
Note: the same params vary by about ±€1,000 between runs (minMargin=0.2 gave €14,625 and €13,575 on spread-1).

## Champion (`recall:src/strategies/recall/champion.json`) on six seeds, all ranked

| Seed | Margin | Orders | On time | Best saved week before tonight | Plain bidprice `tuned-6b` (no memory) |
| --- | --- | --- | --- | --- | --- |
| spread-9 | **€20,297** | 424 | 96.5% | €13,716 | €15,240 |
| spread-1 | €14,851 (€15,618 in the earlier run) | 414 | 92.8% | €11,167 | €12,934 |
| spread-4 | €14,134 | 345 | 93.0% | €9,785 | €11,987 |
| spread-2 | €10,243 | 274 | 97.1% | €8,439 | €8,608 |
| spread-5 | €8,375 | 289 | 92.7% | €7,365 | not played |
| spread-3 | €4,636 | 181 | 94.5% | €4,498 | €3,585 |
| mean | €12,090 | | | €9,162 | |

Reading: recall is overfit by design (it remembers each practice seed's requests) and adds €1,000-5,000 a seed over
plain bidprice. For the secret final only plain bidprice counts: `tuned-6b.json`, mean €13,387 on spread-1/9/4.

## Fee memory for recall (worktree agent-a5e0f9707af984b5f, not merged): inconclusive

Fees per gig do repeat across weeks of a seed (one gig's booked ratio varies 0.168 across weeks on spread-1 against
0.421 between gigs; median lowest on-time booking 0.86 × typical). Opening remembered gigs at that lowest ratio:

| Params | Seed | Margin | Orders | On time | Fees paid |
| --- | --- | --- | --- | --- | --- |
| champion + feeMemory=true | spread-1 | €14,529 | 442 | 92.3% | 1.10 × typical (1.12 without) |

Reading: fees fell a little, margin is inside the ±€1,000 run noise, on-time slipped 0.5 points. Kept aside; worth
another try with feeShade about 1.10 and the remembered fee fed into the quote's cost.

## Champion, three relearn-and-replay passes (memory rebuilt from every saved week before each pass)

| Pass | Seed | Margin | Orders | On time |
| --- | --- | --- | --- | --- |
| 1 | spread-1 | €14,882.04 | 409 | 92.7% |
| 1 | spread-2 | €11,487.72 | 310 | 97.4% |
| 1 | spread-3 | €5,003.47 | 194 | 94.8% |
| 1 | spread-4 | €13,111.06 | 354 | 91.5% |
| 1 | spread-5 | €8,193.31 | 294 | 90.5% |
| 1 | spread-9 | €20,124.99 | 433 | 97.0% |
| 2 | spread-1 | €14,196.31 | 413 | 93.2% |
| 2 | spread-2 | €10,268.55 | 290 | 95.9% |
| 2 | spread-3 | €5,347.68 | 212 | 93.4% |
| 2 | spread-4 | €16,436.66 | 412 | 93.0% |
| 2 | spread-5 | €8,300.73 | 309 | 93.5% |
| 2 | spread-9 | €19,898.10 | 425 | 95.8% |
| 3 | spread-1 | €14,196.31 | 413 | 93.2% |
| 3 | spread-2 | €12,076.15 | 325 | 97.2% |
| 3 | spread-3 | €4,857.43 | 211 | 91.5% |
| 3 | spread-4 | €12,141.10 | 360 | 91.1% |
| 3 | spread-5 | €9,764.63 | 337 | 93.2% |
| 3 | spread-9 | €22,166.93 | 450 | 96.4% |

Pass 3 gave the best single week so far: **€22,167 on spread-9** (450 orders, 96.4% on time).
The same memory and params replay to the cent (spread-1 passes 2 and 3 are identical), so a practice world is
deterministic given our actions; the run-to-run differences come from the memory changing between runs.

## Search over recall's own params (24 candidates; spread-1, spread-4, spread-9)

| # | spread-1 | spread-4 | spread-9 | Mean | On time | Params (over the champion) |
| --- | --- | --- | --- | --- | --- | --- |
| 11 | €14,710 | €14,890 | €20,174 | **€16,591** | 93.7% | minValueCents=130 costScale=1.18 lateTarget=0.0335 comfortHours=5 winShade=1.01 lossShade=0.957 outShade=0.955 minMargin=0.121 (`src/strategies/recall/champion2.json`) |
| 2 | €14,651 | €16,172 | €18,316 | €16,379 | 95.6% | minValueCents=216 lateTarget=0.0339 comfortHours=5 winShade=0.999 lossShade=0.973 outShade=0.914 minMargin=0.219 |
| 14 | €14,722 | €14,419 | €19,787 | €16,309 | 96.1% | minValueCents=144 costScale=1.3 lateTarget=0.0324 comfortHours=5 winShade=1.02 lossShade=0.963 outShade=0.98 minMargin=0.0931 |
| 8 | €14,810 | €15,006 | €17,493 | €15,770 | 95.7% | costScale=1.23 comfortHours=8 rescue=false ... |
| 0 (champion) | €14,196 | €12,141 | (not played) | | | |

## Round 3 (ideas on top of recall)

### prophet: plan the whole remembered week in advance (worktree agent-a49c80de9509a77f4): worse, discarded for now

| Version | Seed | Margin | Orders | On time | Bar (champion2) |
| --- | --- | --- | --- | --- | --- |
| plan capped at 430 orders | spread-1 | €11,598 | 270 | 94.8% | €14,710 |
| plan capped at 430 orders | spread-9 | €16,953 | 308 | 95.8% | €20,174 |

Reading: only 270-308 of the 430 planned requests were won, and declining the rest threw away about 100 orders
recall would have won. An uncapped plan is committed there but not played: the agent's further online runs were
refused by the permission classifier, so I left them unplayed.

### late memory: decline the requests that go late week after week (merged into `tournament`): NEW BEST

About half of the late orders on spread-1 and spread-4 fall on the same requests every week (pickups in far-north
towns such as Joensuu, Rovaniemi, Kemi, Kokkola; under 12 h of slack; evening wins), and those lose money on average.

| Params | Seed | Margin | Orders | On time | Before (champion2) |
| --- | --- | --- | --- | --- | --- |
| champion2 + lateMemory | spread-1 | **€16,820** | 420 | 97.9% | €14,710 at 92.4% |
| champion2 + lateMemory | spread-4 | **€18,940** | 419 | 96.9% | €14,890 at 92.7% |
| champion2 + lateMemory | spread-9 | €20,875 | 437 | 97.0% | €20,174 at 95.9% |

## New champion on six seeds: `recall:src/strategies/recall/champion2.json` with late memory (default on), all ranked

| Seed | Margin | Orders | On time | Declined by late memory | Best saved before tonight |
| --- | --- | --- | --- | --- | --- |
| spread-9 | **€21,252** | 443 | 96.4% | 7 | €13,716 |
| spread-4 | **€19,988** | 461 | 96.5% | 20 | €9,785 |
| spread-1 | **€16,805** | 429 | 96.7% | 83 | €11,167 |
| spread-2 | €12,883 | 350 | 98.3% | 22 | €8,439 |
| spread-5 | €10,492 | 339 | 95.6% | 21 | €7,365 |
| spread-3 | €5,653 | 201 | 97.0% | 0 | €4,498 |
| **mean** | **€14,512** | | 96.8% | | €9,162 |

### cartographer: sharper memory and a probing strategy (worktree agent-ae566d4f8c1da8dcf): no gain, not merged

Findings worth keeping: the single-threshold model misclassifies only 2.3% of 109,000 observations; trust is 1% an
order capped at 25 (best fit of a grid); no competitor undercut shows in the data; errors grow late in the week
(11.9% on Friday) and at trust 25 (12.4%), so the replayed trust probably drifts from the server's.
A probe week (€13,739) narrowed brackets only from 0.130 to 0.127; champion2 on a robust-bracket memory: €14,597.

## Fourth search: recall with late memory (24 candidates; spread-1, spread-4, spread-9, spread-2), all ranked

| # | spread-1 | spread-4 | spread-9 | spread-2 | Mean | Params over champion2 |
| --- | --- | --- | --- | --- | --- | --- |
| 16 | **€18,776** (94.2%) | €17,573 (93.7%) | €20,901 (93.6%) | **€14,446** (96.4%) | **€17,924** | minValueCents=87 costScale=1.12 lateTarget=0.0578 feeFloor=0.952 topRatio=1.21 winShade=1 lossShade=0.976 outShade=0.971 minMargin=0.057 lateShareMax=0.289 lateMinWeeks=2 (`champion3.json`) |
| 21 | €16,090 (98.0%) | €19,258 (96.2%) | **€22,827** (97.8%) | €11,923 (96.4%) | €17,524 | minValueCents=192 costScale=1.22 lateTarget=0.0449 comfortHours=6 feeFloor=0.96 topRatio=1.25 winShade=1.02 lossShade=0.941 outShade=0.964 minMargin=0.0851 lateShareMax=0.273 (`champion3-safe.json`) |
| 0 (champion2 + late memory) | €16,805 | €18,542 | €21,252 | €12,883 | €17,370 | |
| 12 | €18,343 (93.0%) | €16,665 (93.2%) | €21,270 (93.8%) | | | comfortHours=3 ... |

Play: `pnpm bench recall:src/strategies/recall/champion3.json --level 8 --seeds spread-1,spread-4,spread-9,spread-2`.

## champion3 on all six seeds: MEAN OVER €15k, every week ranked

| Seed | Margin | On time | Best saved before tonight |
| --- | --- | --- | --- |
| spread-9 | €20,901 | 93.6% | €13,716 |
| spread-1 | €18,776 | 94.2% | €11,167 |
| spread-4 | €17,573 | 93.7% | €9,785 |
| spread-2 | €14,446 | 96.4% | €8,439 |
| spread-5 | €12,236 | 95.5% | €7,365 |
| spread-3 | €8,112 | 95.2% | €4,498 |
| **mean** | **€15,341** | 94.8% | €9,162 |

## General lateness rule on plain bidprice (branch `feat/late-risk`, not merged; no memory, usable in the final)

| Params (over `tuned-6b.json`) | spread-1 | spread-4 |
| --- | --- | --- |
| baseline | €12,934 (94.7%) | €11,987 (93.8%) |
| lateRisk, lateRiskMax=0.15 | €12,749 (95.6%) | €12,513 (96.7%) |
| lateRisk, lateRiskMax=0.1 | €12,007 (95.1%) | €11,883 (96.3%) |
| lateRisk, lateRiskMax=0.4, lateRiskCents=3000 | €12,904 (94.3%) | €11,896 (93.8%) |

Reading: lateRiskMax=0.15 is about level on margin (+€170 mean) and 2 points safer on time. Worth having for the
final as insurance against the 90% cliff, not as a margin gain.

## champion3, three relearn-and-replay passes on six seeds (memory and late memory rebuilt before each pass)

| Pass | Seed | Margin | Orders | On time | Ranked |
| --- | --- | --- | --- | --- | --- |
| 1 | spread-1 | €19,342.80 | 536 | 95.7% | yes |
| 1 | spread-2 | €14,947.62 | 461 | 97.6% | yes |
| 1 | spread-3 | €7,139.89 | 316 | 94.3% | yes |
| 1 | spread-4 | €17,374.40 | 474 | 93.2% | yes |
| 1 | spread-5 | €13,109.56 | 423 | 95.0% | yes |
| 1 | spread-9 | €22,755.19 | 538 | 93.5% | yes |
| 2 | spread-1 | €18,322.73 | 523 | 93.1% | yes |
| 2 | spread-2 | €14,407.95 | 462 | 95.7% | yes |
| 2 | spread-3 | €8,899.08 | 343 | 97.7% | yes |
| 2 | spread-4 | €18,010.28 | 530 | 92.6% | yes |
| 2 | spread-5 | €10,367.71 | 426 | 92.3% | yes |
| 2 | spread-9 | €22,839.32 | 570 | 93.0% | yes |
| 3 | spread-1 | €17,851.52 | 530 | 93.0% | yes |
| 3 | spread-2 | €15,629.38 | 477 | 96.0% | yes |
| 3 | spread-3 | €9,065.38 | 329 | 98.2% | yes |
| 3 | spread-4 | €15,077.07 | 440 | 89.8% | no |
| 3 | spread-5 | €13,493.99 | 461 | 93.9% | yes |
| 3 | spread-9 | €24,450.74 | 559 | 96.6% | yes |

Six-seed means: pass 1 €15,778, pass 2 €15,474, pass 3 €15,928 (counting the unranked week's margin).
New single-week highs: **€24,451 on spread-9** (96.6%), **€19,343 on spread-1** (95.7%), €15,629 on spread-2, €13,494 on spread-5, €9,065 on spread-3.
Warning: pass 3 on spread-4 ended at 89.8% on time, UNRANKED. champion3 runs near the 90% line (four other weeks at 92.3-93.2%); champion3-safe is the answer to that.

## champion3-safe on six seeds: lower margin, far from the 90% line

| Seed | Margin | Orders | On time |
| --- | --- | --- | --- |
| spread-9 | €21,823 | 435 | 97.9% |
| spread-4 | €18,660 | 424 | 97.4% |
| spread-1 | €15,871 | 395 | 98.0% |
| spread-2 | €13,079 | 342 | 98.2% |
| spread-5 | €10,509 | 303 | 97.0% |
| spread-3 | €6,035 | 216 | 98.1% |
| **mean** | **€14,330** | | 97.8% |

## Where things stand

- Highest margin: `recall:src/strategies/recall/champion3.json`, six-seed mean €15,300-15,900, one week of 19 unranked.
- Safest high margin: `recall:src/strategies/recall/champion3-safe.json`, mean €14,330 at 97-98% on time.
- For the secret final (no memory): `bidprice:src/strategies/bidprice/tuned-6b.json`, optionally with the lateness
  rule of branch `feat/late-risk` (`lateRisk=true,lateRiskMax=0.15`).
- All code is on the local branch `tournament` (not pushed, no PR). Agent worktrees are under `.claude/worktrees/`.

## Per-seed searches on the two weakest seeds (cut short when the laptop's battery ran out)

28 candidates each; 18 weeks of spread-3 and 16 of spread-5 were played before the stop. Best ranked so far:

| Seed | Margin | On time | Params file | champion2 defaults in the same search |
| --- | --- | --- | --- | --- |
| spread-3 | €8,689 | 94.8% | `src/strategies/recall/champion-spread-3.json` | €5,359 |
| spread-5 | €12,743 | 94.7% | `src/strategies/recall/champion-spread-5.json` | €10,863 |

Neither beats champion3's best week on its seed (spread-3 €9,065, spread-5 €13,494). The searches can be resumed with
`pnpm tune --resume out/tune-20261114-033820.json` (spread-3) and `out/tune-20261114-033823.json` (spread-5).

## Leaderboard key, level 8, ranking round "Saturday 00:00" (season 4)

Ranking worlds are secret seeds, so recall's memory cannot apply; the entry is plain bidprice with
`src/strategies/bidprice/board.json` (= `tuned-6b.json` + lateRisk=true, lateRiskMax=0.15).

| Run | Margin | Orders | On time | Ranked | World |
| --- | --- | --- | --- | --- | --- |
| 1 of 5 | €10,871 | 323 | 96.0% | yes | wee84cb83fdf11d1dd12b |

For scale, run 1 of the round's leaders: freya €17,211 (453 orders), skadi €17,292 (480), razors €16,535, ppo
€16,318; the top total over five runs is €85,925. Our run 1 sits around 35th-40th of 62 ranked teams.
Runs 2-5 are held until the general strategy wins more orders: each is one-shot and stays public.
