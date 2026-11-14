# Frozen protocol: Lean `value=1` paired server validation

## Outcome: rejected (issue #371)

The protocol completed on all 30 pairs, after explicit user authorization. Candidate-minus-control margin was
**−€505.76** (SD €1,191.22, SE €217.49, paired 95% CI **−€950.57 to −€60.95**), ahead 9/30. Candidate and control
ranked 29/30 and 30/30; the candidate-only unranked week was `vt1-fd40776b` at 86.05% on time. Mean on-time difference
was −1.09 points and the minimum candidate share was 86.05%. Mean late refunds were €913.64 candidate against €613.25
control. This fails every acceptance condition. Keep `value=0`; do not tune or repeat doses on the `vt1-*` holdout. Raw
data is `value-server.csv` and the saved `vt1-*` worlds, with statistics and replay commands in `README.md`.

## Status and scope

The candidate adds `value.ts` and `value.json` to current TypeScript Lean and wires the `value` charge into
`src/strategies/lean/index.ts`. The default `value=0` is unchanged current main (`3babed0d`). The candidate is only
`lean:value=1`. No stronger setting is part of this protocol. No ranking run or final is requested or authorized.

Offline findings already observed, and not to be presented as server evidence:

- Experimental ten-pair batch from the decision-algorithm branch: +€521.48/week, all ten pairs ranked.
- Frozen current-main 40-seed screen: +€680.93, paired 95% CI +€232.46 to +€1,129.39, 40/40 ranked.
- Untouched candidate on 40 fresh validation seeds: +€387.35, paired 95% CI +€7.55 to +€767.15, 40/40 ranked,
  minimum candidate on-time share 90.12%, mean paired on-time change −0.848 percentage points.
- Rejected stronger settings: `value=1.25` caused an exploratory unranked week; `value=1.10` gained only +€251.32
  on its own fresh validation and caused an 88.9% unranked week. Neither may replace `value=1` here.

The fresh validation mean is below €500. This protocol is therefore a request to measure the unchanged candidate on
the real server, not a claim that a second improvement is already established.

## Frozen implementation evidence

`sha256sum -c` passed before validation and again afterwards, and remains unchanged now:

```text
12b984795a855b26c166f0e9f25ef5a3c48b1ed25317d4cb55d98ac485c55bb4  src/strategies/lean/index.ts
4abfb099945d7118d982adbf686867c3cde1f6064ae4227d8ee72cae492ef1a0  src/strategies/lean/value.ts
5edd44bba7105a13290c8399fd7c02ca398c65e317aeabe92d33f413b8e0acb1  src/strategies/lean/value.json
```

TypeScript check: `pnpm check` passed. No tests were written or run under the repository's no-tests policy. Every
comparison used a fresh journal directory to prevent deterministic simulator world IDs from reusing old journals.

## Required online authorization and safety checks

Do not run until the user explicitly authorizes **one online paired benchmark: 30 seeds × two policies = 60 practice
weeks**. `active-models.md` was read; Lean is not present in `SHELVED.md`. Before starting, also verify that no other
online run is active. Keep recording enabled. Use `--jobs 3`, not more than four as suggested by `active-models.md`.
Do not use `--board` or `--final`. There must be no pruning, substitution, retry-for-score, retuning, or dose change
based on observed results.

## Pre-registered fresh seeds

These 30 names were generated with Node's `crypto.randomBytes` after all tuning stopped. A search found no `vt1-`
collision in saved level-8 metadata.

Seed-list file: `src/strategies/lean/value-server-seeds.txt`
SHA-256: `75bcedd8eae98e1a3f1e981a2886c8ce4284787a4a98e476872d83e03b74e381`

```text
vt1-e0edec63,vt1-9591c003,vt1-ce37806c,vt1-3ed26a78,vt1-0f798553,vt1-405cceee,vt1-7100899e,vt1-8d3c447d,vt1-2a3a7b03,vt1-38383414,vt1-fd40776b,vt1-cb60ea09,vt1-56545637,vt1-e7961857,vt1-434f6f99,vt1-dca0866a,vt1-3090c55b,vt1-c6dd6a4f,vt1-e317700c,vt1-69a93ad4,vt1-8316b690,vt1-ee936487,vt1-38fa184c,vt1-f807de79,vt1-3dc0963e,vt1-c52717eb,vt1-b0881505,vt1-b9c49c39,vt1-f75b67a1,vt1-2bf7f018
```

## Exact command

Run from `/tmp/opencode/junction2026-next-improvement` (or from a clean checkout with exactly this patch applied),
with the normal Spread credentials in `.env`:

```sh
journal=$(mktemp -d)
SPREAD_JOURNAL_DIR="$journal" \
  pnpm bench lean:value=0 lean:value=1 \
  --level 8 --jobs 3 --csv out/lean-value1-server.csv \
  --seeds "$(cat src/strategies/lean/value-server-seeds.txt)"
```

This is a single benchmark invocation, hence one online run. Do not run it concurrently with another online command.
It deliberately does not set `SPREAD_RECORD=0`, so all completed weeks are recorded as required. If the seed-list file
is unavailable after copying the worktree, use the literal list above rather than creating new seeds.

## Required report

Report all 30 seed-specific `value=1 − value=0` margin differences, the mean difference, sample SD and SE, and a
Student-t paired 95% CI with 29 degrees of freedom (`t0.975 = 2.045229642`). Also report control and candidate mean
on-time shares, every candidate minimum on-time share, ranked counts, and the number of candidate-only unranked weeks.
Any failed or missing pair invalidates the run unless its full replacement protocol was itself fixed beforehand; do not
select convenient completed seeds.

Pre-registered acceptance rule:

1. mean paired margin gain at least **€500/week**;
2. paired 95% CI excludes zero;
3. no candidate-only unranked weeks;
4. every individual on-time share and the late/refund pattern reviewed because the simulator loses on-time share and
   is unreliable at ranking it.

If the rule fails, report the negative result and do not select stronger values, change seeds, or reuse this holdout
for further tuning. If it passes, propose changing `value` from 0 to 1 and document the raw CSV; do not merge or start
ranking/final runs without separate user approval.
