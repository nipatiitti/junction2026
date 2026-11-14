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

## Holdout: practice seeds no config was tuned on (no memory exists for them)

| Seed | bidprice `board.json` | Orders | On time | recall params `champion3-safe` without memory |
| --- | --- | --- | --- | --- |
| spread-6 | €8,003 | 199 | 97.0% | €9,175 (97.7%) |
| spread-7 | €11,245 | 306 | 94.4% | €9,612 (90.7%) |
| spread-8 | €12,215 | 316 | 97.8% | €12,660 (97.1%) |
| spread-10 | €9,993 | 289 | 91.7% | €8,590 (90.8%) |
| mean | €10,364 | | | €10,009 |

Reading: on unseen worlds the general strategy is a €10-11k system (ranking run 1: €10,871). It quotes 48-64% of
requests and wins about half of those: 200-320 orders, where the ranking leaders win 430-480 at 96-99% on time.

## General search of plain bidprice on spread-6, 7, 8, 10, 2 (24 candidates around `board.json`): no robust gain

| # | spread-6 | spread-7 | spread-8 | spread-10 | spread-2 | Mean |
| --- | --- | --- | --- | --- | --- | --- |
| 11 | €10,716 (96.9%) | €9,358 (88.5%, UNRANKED) | €13,090 (97.2%) | €10,821 (92.4%) | €11,043 (95.4%) | €11,006 |
| `board.json` | €8,003 | €11,245 (94.4%) | €12,215 | €9,993 | €8,608 (tuned-6b) | about €10,000, all ranked |

#11: war=follow minValueCents=85 lateTrust=5 costScale=1.21 lateRiskMax=0.4 lateTarget=0.0263 comfortHours=3
topLeadHours=7.89 feeFloor=0.92 topRatio=1.29 staleHours=3.55. The two trustValue=0.5 candidates (a trust discount)
did worse: €9,331 and €8,934. Params are not the lever on unseen worlds.

## Generalising what the overfit strategy fits to: results on untested seeds

`recall` with its highest-margin params but no memory (the seeds are new to it), and the cross-world threshold model:

| Seed | `board.json` (general baseline) | recall `champion3`, no memory | bidprice + threshold model |
| --- | --- | --- | --- |
| spread-6 | €8,003 (97.0%) | €10,167 (97.7%) | €7,566 (99.0%) |
| spread-7 | €11,245 (94.4%) | €8,705 (87.1%, UNRANKED) | €10,356 (94.8%) |
| spread-8 | €12,215 (97.8%) | €11,656 (94.9%) | €11,044 (96.2%) |
| spread-10 | €9,993 (91.7%) | €9,501 (91.3%) | €9,835 (94.5%) |
| mean | **€10,364** | €10,007, one week unranked | €9,700 |

What each part of the overfit strategy turned into:

| recall fits to | General version | Result |
| --- | --- | --- |
| each request's price threshold | cross-world model (delivery and pickup town, list over typical fee, premium, private address) | removes 15-28% of the scatter offline, but €660 a week WORSE online: discarded |
| the same, per dealer | a dealer level learned inside the week | no signal: between-dealer variance is at chance level on all six seeds, the online version removes at most 0.9%. Not built. The 0.9-2.2 × list dealer levels of `haggle` were trust plus noise. |
| requests that go late every week | lateness rule from slack and drivers within 100 km of the pickup | margin level, on-time +2 points: kept, in `board.json` |
| params tuned on rich seeds | search on other seeds | no robust gain |

Conclusion: recall's €5,000-10,000 a week over plain bidprice comes from knowing each request's own threshold, and
that part is noise from one world to the next: it does not generalise. On unseen worlds we are a €10-11k system.
The ranking leaders make €16-17k there with 430-480 orders at 96-99% on time, against our 200-320 orders; we quote
only 48-64% of requests. The open question is how they serve 40% more orders on time, not how they price.

## Decline audit of plain bidprice on spread-8 (1,033 requests; merged: decline log, `war: follow` in `board.json`)

| Reason for no quote | Requests | Others' margin per request per week | Verdict |
| --- | --- | --- | --- |
| quoted | 663 | €12.01 | |
| expected value under `minValueCents` | 199 | €3.49 (about €700 a week at most) | small |
| `lateRisk` | 61 | €2.60, 14.8% late | right |
| `canServe` (slack too short) | 43 | nobody won them | right |
| war-day rule | 38 | €9.85, 2.9% late | wrong: now follows the war day |
| no price covers cost | 29 | −€0.30 | right |

Lost quotes: of 341 lost requests, 155 were won by another system; our price was a median 8.3% above the highest
price it got accepted (same_day 10.5%). Win rate by day: Mon 46%, Tue 38%, Wed 54%, Thu 41% (war), Fri 58%.

| Week | Margin | Orders | On time |
| --- | --- | --- | --- |
| spread-8, `war: follow` | €12,300 (+€85) | 328 | 97.6% |
| spread-6, `war: follow` | €8,064 (+€61) | 209 | 96.7% |

Reading: no single large leak. The volume gap to the leaders is not in admission; it is price level (about 8% high
where we lose) and what volume costs us in drivers and lateness.

## Stacking small gains on untested seeds (plain bidprice, `board.json` with `war: follow` as the baseline)

| Variant | spread-6 | spread-7 | spread-8 | spread-10 | Mean | All ranked |
| --- | --- | --- | --- | --- | --- | --- |
| baseline, `war: follow` | €8,194 | €10,286 (93.0%) | €12,300 | €8,828 (91.8%) | €9,902 | yes |
| baseline, `war: decline` (earlier batch) | €8,003 | €11,245 (94.4%) | €12,215 | €9,993 (91.7%) | €10,364 | yes |
| A: minValueCents=60 | €7,996 | €11,266 (92.8%) | €12,996 | €10,637 (91.6%) | **€10,724** | yes |
| B: costScale=1.12 | €8,225 | €8,677 (89.7%) | €11,039 | €8,470 | €9,103 | no |
| A+B | €9,288 | €7,878 (89.1%) | €12,618 | €9,037 | €9,705 | no |

Reading: quoting low-value requests is worth +€822 a week at the same on-time share. Lower prices alone lose money.
Following the war day is −€462 on the four-seed mean (it was +€60-85 on the two seeds first measured): reverted.

Per-driver offers (worktree agent-a08e9da81236043a6, analysis only): a driver's booked fee is not predictable from
distance, rating or experience (R² 0.03); 0.5% of 137,557 direct offers in saved weeks were accepted; 11% of
bookings went to a driver who had seen the gig cheaper and waited (median +€16). Realistic saving €100-250: not built.

| C: minValueCents=60, `war: decline` | €7,781 | €11,670 (95.8%) | €12,263 | €10,204 (91.8%) | €10,479 | yes |
| D: minValueCents=20, `war: decline` | €7,724 | €10,958 (94.7%) | €11,764 | €9,344 (92.7%) | €9,948 | yes |

Reading after the second batch: minValueCents=60 helps in both pairings (+€822 with `war: follow`, +€115 with
`war: decline`); 20 is too low. The war-day rule flips sign between the pairings (−€462, then +€245), so it is
inside the noise of a four-seed mean, about ±€400. `board.json` is now minValueCents=60 with `war: follow`
(the best measured combination, €10,724). Ranking anything smaller than about €400 needs more seeds.

## Round 4: mechanics from the organisers' documents that bidprice did not use

A read of HANDBOOK.md, RULES.md and API.md against our code listed 15 unused or misused mechanics. Four were
built, each behind a flag (default off), and played on the four untested seeds against `board.json`
(spread-6 €7,996, spread-7 €11,266, spread-8 €12,996, spread-10 €10,637; mean €10,724). None is merged.

| Mechanic (flag) | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Verdict | Worktree |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Hold the first post to the day before pickup (`postTiming`) | €8,459 | €9,994 | €11,734 | €9,566 (90.2%) | €9,938 | loss (−€786) | agent-acb1a14448cfaaed9 |
| Cost from drivers near pickup and delivery plus our own orders (`geoCost`) | €9,865 | €6,575 (85.7%, unranked) | €10,290 | €7,389 (88.9%, unranked) | €8,530 | loss: the chain discount fired on 900 of 1,033 requests | agent-abb3d2c797b952017 |
| the same without the chain discount (`geoChain=0`) | €9,704 | €8,215 (87.9%, unranked) | €12,710 | €9,937 | €10,141 | loss; still a broad price cut | |
| Outage detection (`outage`) | €8,238 | €11,035 | €12,754 | €11,498 | €10,881 | +€157, inside noise; fires correctly (spread-8: Helsinki, Wednesday 10:46, 57 of 109 lifted quotes won) | agent-a7819198e3188a746 |
| Charging only over 200 km, release late drivers (`chargeOver200`, `driverLate`) | €8,062 | €10,446 | €12,556 | €11,669 | €10,683 | −€41, noise; `driver_late` happens once in nine weeks | agent-a4c263850d3503cff |

Readings:
- The outage is real and keyed on the pickup place (spread-4: win rate at 1.4+ × list 94% inside the region against
  39% outside), but only 10-36 requests fall in it, so it is worth a few hundred euros at most.
- `geoCost` reached the leaders' volume (416-495 orders) at €16-26 an order with late weeks: volume alone is not
  their edge, they hold price while winning more. Cheaper prices paid on the thin world (spread-6 +€1,700 at 96.5%
  on time) and broke the busy one (spread-7).
- Trust check: our count matches the rules (orders, on-time only, halved on a late one, cap 25).

Not built from the review's list: fewer and later fee raises, offers to our own working drivers, re-quoting before
the response deadline, the bulk order from one yard, flu and snow days, a per-dealer value of speed.

## Study of the public rankings (level 8, round "Saturday 00:00": 373 runs by 75 teams on five secret worlds)

| Group, per world | Margin | Orders | Margin per order | On time |
| --- | --- | --- | --- | --- |
| top 10 | €15,100-17,100 | 399-447 | €36-41 | 95.5-98.1% |
| ranks 21-40 | €11,500-13,400 | 299-338 | €36-41 | 92.2-97.3% |
| bottom 15 | €5,500-6,300 | 217-249 | €23-27 | 94.6-98.1% |
| us, run 1 | €10,871 | 323 | €33.70 | 96.0% |

Margin correlates 0.72-0.81 with orders won, about 0 with on-time share, 0.55-0.66 with margin per order.
The leaders earn the same per order as the mid-table and win about 110 more orders. `house-strong` (the organisers'
system): €12,225-15,491 a run with 301-409 orders. Only summary numbers are public: no quotes, gigs or code.

## Round 5: three attempts at the volume gap (four untested seeds, baseline €10,724; none merged)

| Idea (flag or strategy) | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Cost scale that follows spare driver capacity (`posture`) | €9,258 | €9,741 | €12,308 | €9,328 | €10,159 | loss (−€565); helps only the thin world. Roster size (704/691 against 640/642 drivers) is the only early signal that separates the worlds |
| Build trust faster with big dealers (`trustRush`) | €6,250 | €11,052 | €11,498 | €10,586 | €9,846 | loss (−€880); its stricter admission turned away early orders |
| Hold one price per option whatever the trust (`steady`, on the base) | €4,351 | €3,726 | €6,590 | not played | €4,889 | hypothesis fails: the win rate does not climb through the week, mean trust of quoted dealers never passes 12 |

Trust in our own baseline weeks (analysis/trust_timing.py, worktree agent-af8c2b2d33d476237): 64-78% of requests
arrive while their dealer has under 10 on-time orders, 89-94% under 25; the biggest dealer reaches 10 by hour 36-57
and 25 by hour 57-84; our quote over list rises from 1.39-1.47 at trust 0-4 to 1.73-1.89 at trust 25 with win rates
of 32-40% and 47-67%; the five biggest dealers were halved by late orders 6, 19, 3 and 16 times a week.

Where this leaves the general system: about €10,700 on unseen worlds. How the leaders win 110 more orders at the same
margin per order is still not explained; holding price for trust is ruled out in its simple form.

## Round 6: the early-week leak and three more mechanics (four untested seeds, baseline €10,724; none merged)

A fresh, unanchored diagnosis (analysis/leaks.py, worktree agent-a4e7d2a09bf63ce59) compared 12 of our weeks request
by request with every other saved week of the same seed: we send no quote on 310 of 1,033 requests (66% of Monday's
and 55% of Tuesday's are quoted, 74-80% later); 98 declined requests a week were won by another system at a median
1.35 × list; 189 lost quotes a week were won elsewhere, ours a median 8.3% higher; we never quote all three options.

| Idea (flag) | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Sweep, first setting: 75% win target at 5% margin until trust 12, then cap at 70% win (`sweep`) | €6,749 | €7,771 (89.0%, unranked) | €7,132 | €9,925 | €7,894 | loss (−€2,830): +30-90 orders at €16-27 an order; trust still collapses from late orders |
| Sweep, mild: 60% at 15% margin until trust 8, late margin 25%, cost scale 1.12, brake 10 | €8,543 (254 orders) | €10,893 (389) | €12,179 (375) | €10,637 (316) | €10,563 | neutral (−€161): more orders on three seeds, on-time level or better, margin per order about €29 |
| Quote instead of declining for value, and add every servable option (`quoteAll`, `allOptions`) | €8,541 | €10,072-10,767 | €12,752 | €10,480 | €10,461-10,635 | noise (−€89 to −€263): the added quotes won 5-6% and the added options were rarely taken |
| Re-quote a few minutes before the response deadline (`requote`) | not played | €10,071 | €12,279 | not played | two-seed −€956 | loss: 104 of 179 re-quotes went up |
| One flat fee per gig with a single late step (`flatFees`) | €4,877 | €9,746 | €9,139 | €8,530 | €8,073 | loss (−€2,651): fees paid rose to 1.14-1.16 × typical, orders fell 25-39% |

Readings:
- The requests we decline are not winnable at a profitable price in the week we are in: quoted at honest cost plus
  12% they won 5-6%. That other systems won them in other weeks reflects those weeks' trust and prices, not a leak.
- Buying early volume with lower prices does not pay back through trust within the week: the stronger the sweep, the
  larger the loss; the mild one breaks even.
- Our climbing fee schedule saves real money; paying drivers more is not the route to volume.

After six rounds the general system stays at about €10,700 on unseen worlds. Kept changes: `minValueCents` 60 and
the lateness rule (in `board.json`). Small candidates not merged: outage detection (+€157), mild sweep (−€161 with
better on-time share).

## Round 7: gigs with several cars (round trips), the one game mechanic the TypeScript system did not use

Measurement (branch `feat/pairs-measure`, analysis/pairs.py and 16 forked probes on spread-8):

| Seed | Orders won | Round trips (15 km) | Chains | Same yard | Orders that could sit in a pair |
| --- | --- | --- | --- | --- | --- |
| spread-6 | 228 | 22 | 79 | 53 | 175 (77%) |
| spread-7 | 363 | 36 | 125 | 93 | 300 (83%) |
| spread-8 | 348 | 31 | 114 | 82 | 264 (76%) |
| spread-10 | 324 | 21 | 103 | 81 | 256 (79%) |

Upper bounds (opening hours ignored). Forked probes: both round trips booked 17% and 19% under their two single
gigs; of 14 chains, 7 were 11-21% cheaper, 5 dearer, 2 never booked. Estimated €500-1,700 a week in fees and 60-120
fewer gigs a week for the same orders.

Build (`pairs` flag, worktree agent-a97c1abc2ef8aada1, not merged): round trips of two unbooked one-car orders
posted as one gig at 0.85 × the two schedules, split back to single gigs when urgent or unbooked 6 h before the start.

| Version | spread-6 | spread-7 | spread-8 | spread-10 | Mean (baseline €10,724) |
| --- | --- | --- | --- | --- | --- |
| first build (a pair's fee booked on one order) | not played | €10,153 | €12,812 | not played | two-seed −€648 |
| accounting fixed, 25 km | €8,025 | €11,091 | €12,797 | €9,099 | €10,253 (−€471; all of it spread-10) |
| pairKm=40 | | €10,940 | | | |
| pairCostCut=0.08 (cheaper quotes for requests that pair) | | €10,374 | | | |

Pair gigs posted / booked / split back: spread-6 3/3/0, spread-7 18/18/3, spread-8 16/15/1, spread-10 16/12/3.
Paired cars booked at 0.83-0.87 × typical against 1.04-1.08 × for the whole week: about 20% cheaper, as measured.

Reading: the mechanic works and saves what the probes said per pair, but only 7-10% of orders end up paired, so
the week's total does not move yet. It is the first idea that frees driver capacity instead of moving price.

## Round 8: why orders go late, and a safety rule that came out of it

Post-mortem of every late order (analysis/late_causes.py; 28 normal ts-bidprice weeks on the four untested seeds,
8,415 orders, 481 late or undelivered), by first cause:

| Cause | Share (high-volume weeks) | Refunds a week |
| --- | --- | --- |
| no driver booked until close to pickup | 42% (55%) | about €2,030 |
| order changed by the dealer, or snow | 21% (13%) | about €600 |
| booked early, picked up late | 19% (11%) | about €200 |
| booked, then dropped or no-show | 14% (18%) | about €490 |
| picked up in time, delivered late | 3% | about €90 |
| won with too little slack | 0.2% | negligible |

The dominant kind sits open a median of 73 hours, already at 1.8 × typical, and books about 5 hours too late at 2.1 ×.
It is not unseen: it gets views, but from drivers a median of 86 km away. Its pickups have a median of 14 drivers
within 30 km (40 for on-time orders) and legs of about 400 km (140 km). But about ten good orders share those
features for each late one, so no decline rule nets positive on the saved weeks (−€24 to −€1,852 a week).
Pushing fees up earlier (`onTimeOps`) cost about €7,000 on spread-7: discarded.

`unseenRule` (merged, default off): decline a request whose first leg is 400 km or more and whose pickup has fewer
than 10 roster drivers within 30 km.

| Config | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Lowest on-time |
| --- | --- | --- | --- | --- | --- | --- |
| `board.json` (baseline) | €7,996 (96.3%) | €11,266 (92.8%) | €12,996 (97.1%) | €10,637 (91.6%) | €10,724 | 91.6% |
| + `unseenRule` (`board-safe.json`) | €8,554 (97.8%) | €11,472 (95.1%) | €12,130 (97.3%) | €9,660 (94.9%) | €10,454 | **94.9%** |
| + `unseenRule`, costScale=1.12 | €8,920 / 293 orders (95.2%) | €10,203 / 404 (91.6%) | €12,946 / 401 (98.0%) | €8,378 / 350 (90.9%) | €10,112 | 90.9% |
| costScale=1.12 alone (earlier) | €8,225 | €8,677 (89.7%, unranked) | €11,039 | €8,470 | €9,103 | 89.7% |

Readings:
- `unseenRule` costs about €270 a week and lifts the lowest on-time share from 91.6% to 94.9%: the safest general
  config so far, which matters for a single live final where under 90% counts as nothing.
- With the rule, lower prices reach 400 orders on time (spread-8: 401 orders at 98.0%), but total margin does not
  rise: the extra orders bring almost nothing. So on-time capacity was not what stopped volume from paying; the
  marginal orders are simply thin at our prices. The leaders' extra orders must come at full margin.

## Lower fee floors on `board-safe.json` (four untested seeds): worse

| feeFloor | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Fees paid over typical |
| --- | --- | --- | --- | --- | --- | --- |
| 0.96 (`board-safe.json`) | €8,554 | €11,472 | €12,130 | €9,660 | €10,454 | about 1.04-1.08 |
| 0.85 | €9,201 | €10,384 | €10,796 | €7,615 | €9,499 | 1.06, 1.10, 1.07, 1.11 |
| 0.75 | €8,966 | €7,795 | €8,062 | €8,807 | €8,408 | 1.06, 1.19, 1.16, 1.07 |

Reading: opening lower raises what we pay. Gigs that miss the first step age and book after raises. About 1.05 ×
typical is near the floor for single-car gigs with this schedule; only round trips book under it (0.83-0.87 ×).

## Round 9: trust protection, a focused trust discount and chain gigs (#222): built, not played yet

Measured on 12 saved `ts-bidprice` weeks of spread-6, 7, 8 and 10 (three a seed), before building:

- Requests are concentrated: the top dealer sends 25–33% of a week's requests, the top five 55–66%, of 38–40 dealers.
- The top dealer's count reaches 25 on Tuesday or Wednesday and is then halved 2–12 times a week (for example 25, 25,
  9 on spread-6; 16, 12, 24, 9, 14 on spread-8). The second dealer is halved 0–6 times.
- Deliveries land a median 24–28 hours after the win for every option (`within_3_days` a median 78 hours before its
  deadline), so the option does not decide when trust arrives. Favouring fast options to earn trust sooner was
  dropped; the lag went into the bonus as `trustLagHours`.
- `board.json` has `lateTrust: 0`: a late order was priced at its refund alone.

Built behind flags of `bidprice`, all off by default (`src/strategies/bidprice/README.md` has the details):

| Config (over `board.json`) | Idea |
| --- | --- |
| `trust-guard.json` | a late order also costs the trust its halving loses at that dealer (`trustGuard` 1) |
| `trust-focus.json` | the trust bonus only for dealers with 4% of the requests, under a count of 12, for requests a day later |
| `chains.json` | `pairs` with `pairChains`: chains at 0.92 × the two schedules, round trips first |
| `trust-both.json` | the two trust ideas |
| `volume-all.json` | all three |

Offline, a halving at a dealer with 30% of the requests and a count of 25 on Wednesday loses about 91 points over the
rest of the week, 0.75 of an order's price: a late weight of 2.7 against a refund of 0.43 of the price.

Played on 2026-11-14, one bench of 24 weeks (`pnpm bench ... --jobs 6`); margin / orders / on time:

| Config | spread-6 | spread-7 | spread-8 | spread-10 | Mean | Orders | Lowest on-time |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `board.json` (baseline) | €7,996 / 217 / 96.3% | €11,266 / 375 / 92.8% | €12,996 / 345 / 97.1% | €10,637 / 333 / 91.6% | €10,724 | 318 | 91.6% |
| `trust-guard.json` | €8,640 / 225 / 98.7% | €11,406 / 353 / 93.8% | €12,925 / 335 / 97.6% | €11,963 / 317 / 94.6% | **€11,234** | 308 | 93.8% |
| `trust-focus.json` | €8,839 / 266 / 96.6% | €11,248 / 392 / 93.9% | €13,137 / 387 / 96.9% | €9,626 / 337 / 91.1% | €10,712 | 346 | 91.1% |
| `chains.json` | €8,873 / 232 / 97.4% | €11,083 / 375 / 93.3% | €13,505 / 352 / 97.4% | €10,021 / 350 / 91.4% | €10,871 | 327 | 91.4% |
| `trust-both.json` | €9,287 / 257 / 98.8% | €10,402 / 383 / 92.7% | €12,724 / 374 / 98.4% | €11,591 / 322 / 94.7% | €11,001 | 334 | 92.7% |
| `volume-all.json` | €9,309 / 262 / 98.9% | €11,847 / 390 / 93.8% | €11,450 / 366 / 96.2% | €10,818 / 342 / 93.6% | €10,856 | 340 | 93.6% |

Readings (a four-seed mean moves about ±€400):
- `trustGuard` is the one gain: +€510 on the mean with 10 fewer orders, and the lowest on-time share up from 91.6% to
  93.8%. It weighed 180–305 gigs a week at a late weight of 1.8–2.8.
- The focused discount wins 28 more orders a week for the same margin (−€12): the bought orders are thin, as before.
- Chains book (41–49 of 54–90 posted a week, at 0.92–0.98 × typical) but move the mean only +€147, inside the noise.
- The ideas do not add up: both trust ideas +€277, all three +€132.
- The baseline replayed to the euro on all four seeds, so the merged code decides as before with the flags off.

## Params switched inside a week (#233): stopped early

`src/strategies/phased/` plays `bidprice` with one params file until `phaseHour` and another after it;
`uv run python -m analysis.phases` splits a saved week's margin by the hour each order was won. Nine configs were
started on spread-6, 7, 8 and 10 and stopped after spread-6 and part of spread-7, so nothing here is a result yet.
Known so far: `board.json` switched to itself replays the baseline to the euro (€7,996 on spread-6), and the config
"guard until hour 48, then `board.json`" never turned the guard off, because `board.json` has no `trustGuard` key.
