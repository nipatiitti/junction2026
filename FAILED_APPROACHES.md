# Approaches that did not help

A short record of approaches we measured and would **not repeat without a new reason**. Read this before spending
another online week on a hypothesis that merely rearranges timing, retries, or bundling.

Scope: these are negative experiments against the system named in each row, not a proof that every version of an idea
is bad. Most bundle experiments used six fresh shared seeds at level 8 in **normal mode**. A result of combining two
changes says something about that combination, not its individual components. Fresh seeds avoid selecting only on
`spread-1`/`spread-5`; small panels still leave material seed noise, so read significance, not just order.

## The bundle-timing family (#306)

All three start from the unchanged leading `all_in`, and keep the original admission, pricing and dawn-fee rules. The
**mean margin per week** is over the same six `tour-r1`/`tour-r2` seeds. Every variant ranked on all six seeds except
where stated, so their differences are not explained simply by the 90% on-time minimum.

| Change | Intent | Outcome vs `all_in` | Read it as |
|---|---|---|---|
| `return_legs`: cheapest-insertion chain routing, immediate partners only | More/better compound posts | Mean **€11,232.15**, **−€1,103.11** | Better route ordering did not make up for the underlying demand/margin structure. Do not assume a more elegant chain planner is worth more. |
| `solo_chain`: ordinary cheap solo for 45 min, then one withdraw-and-recompose attempt if unbooked | Get a cheap first booking, without losing the later chain option | Mean **€11,829.91**, **−€505.35** | Closest to tying but still below `all_in`. This is not free upside: retrying solo costs booking opportunities. Do not repeat without a different partner or hazard model. |
| `informed_chain`: the same fallback, but wait 45 or 60 min in dense city/time bins fitted from past arrivals | Prefer longer holds only where a later partner was likely | Mean **€11,321.34**, **−€1,013.92** | Arrival-density priors are not economic proof of a good route. The extra waiting lost both volume and margin. Dense cities do not automatically make long waits profitable. |

Control: **`all_in` mean margin €12,335.26/week** across the same six seeds. The full CSV is
`out/bundle-experiments-306.csv`; results are a non-committed saved output because `/out` is gitignored.

## Different knobs, also already measured

| Change | Why it was considered | What happened | Conclusion to avoid re-testing it unchanged |
| --- | --- | --- | --- |
| `--fast-mode` on `all_in` (#281) | Fewer requests per week | On one fresh seed, normal: **318 orders, €11,163.99**, fast: **291 orders, €8,359.45**. Fast saved 266 calls but lost **€2,804.54 (-25.1%)** and reduced on-time. | Do not score, rank, prune, or adopt using fast-mode weeks. Latency and handling order materially affect margin. Normal mode is the evaluation baseline; optimise speed separately from strategy results. |
| Admission `capacity_per_driver` 0.10 → 0.15 | Accept more cars when driver supply is tight | Across its five-seed comparison: margin only **+€351.69 total** versus unchanged root, with similar on-time. | About +€70/week, inside seed noise. Not a meaningful "unrestricted capacity" lever. |
| Admission `cost_base` 1.15 → 1.05 | Assume drivers will cost less and increase order volume | Root **€31,844.97** vs cost variant **€26,952.34** over five seeds: **−€4,892.63**, plus worse on-time. Combining it with relaxed capacity also lost margin (**−€4,644.85**). | Higher volume from an underpriced expected driver cost is not the same thing as profitable volume. Don't lower the buffer to gain orders. |
| Waiting for a bundle generally (`bundling_more`, `bundling_cheaper`) | Better driver economics by composing cars together | Earlier variants stayed within noise of their base system despite starving of candidates later. Recent `chain_opt` variants have not shown that merely optimising insertion rescues them. | Blanket/non-urgent waiting remains unproven; it does not rescue a weaker admission or pricing policy. Test one small trigger at a time. |

## Do not over-read this

These results **do not say "chains don't work."** The `all_in` bundle-fee selection was evaluated separately and was
one of the few changes with a demonstrated positive effect: about **+€349/week on 17/22 measured weeks**. In
particular, changing how a bundle is **priced** and changing how much **waiting** it takes are different assertions.

Useful follow-ups should come with a distinct mechanism or better attribution: route-margin versus driver-duration,
actual booking hazard at the time of posting, and the cost of extra waiting. A cheap opening fee, a win-rate change,
capacity easing and a chain-fee discount are not the same experiment. If a variant merely makes a cheap job or chain
take longer, insist on margin improvement after late refunds and undelivered costs, not just a larger order count.

When extending this file, add the **seed panel, control, mean margin, on-time/ranked and a link to the result file or
issue**. Shelved-first passes exist too — `SHELVED.md` is the exclusion list from the earlier roster tournament.
