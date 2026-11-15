# Lean changelog

`lean` exists twice: the TypeScript version (`src/strategies/lean/`, on the harness in `src/harness/` and the ops in
`src/ops/`) and its Python port (`strategies/lean/`). Both must decide the same way, so every change to either one gets
an entry here, newest first, in the same PR as the change. [`AGENTS.md`](AGENTS.md#lean-two-versions-in-step) has the
rule.

Each entry says:

- **Date** and the **PR** (and its issue).
- **Version changed**: TypeScript, Python, or both.
- **What changed**: the behaviour or the params, in a sentence or two, and the measured result if there is one.
- **In step**: `yes` when both versions have the change and play the same week, or the issue that brings the other
  version up to date.

## How to check that they are in step

Both versions play the same week action for action when they are in step, on the offline simulator as on the server.
With the simulator running (`pnpm sim --port 8787`), play one seed with each and compare the `End` and `lean:` lines,
which must be identical:

```sh
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim SPREAD_RECORD=0 node src/dispatch.ts --level 8 --seed spread-1
SPREAD_URL=http://localhost:8787 SPREAD_KEY=sim SPREAD_RECORD=0 uv run strategies/lean/dispatch.py --level 8 --seed spread-1
```

For a closer look, set `SPREAD_JOURNAL_DIR` to a different folder for each and compare their journals line by line:
every quote, post, withdrawal and reprice should be the same.

## Entries

### 2026-11-15: the room for late orders, and the volume settings as defaults (issue #381)

- **Version changed**: TypeScript.
- **What changed**: new param `room` (3.5). From Friday 21:00 the strategy compares the late chances of its orders
  without a driver with the late orders the week can still take under the 90% minimum, and while the room is too
  small it raises the fees of the single gigs at risk, on Saturday and Monday. In 174 of 188 saved weeks it does
  nothing. On `confirm-7` (90.1% on time before) the week ended at 91.8%, for €687. New defaults `taxFade` 1 (was 0)
  and `pairShare` 0.5 (was 0): the volume settings, +€430 to +€860 a week over the defaults before.
  `src/strategies/lean/volume.json` is gone.
- **In step**: no. Issue #329 brings the Python version up to date.

### 2026-11-15: the squeeze (PR #368, issue #367)

- **Version changed**: TypeScript.
- **What changed**: new defaults `urgentTop` 1.6 (was 2), `lateTop` 1.3 (was 1.7) and `chainDays` 5 (chains on
  Friday too; was Monday to Thursday): +€488 to +€671 a week on 30 fresh server seeds. New params that are off:
  `taxFade` (no load charge on Friday, half on Thursday) and `pairShare` (a request that would ride in a chain with
  open cars we hold is priced by that chain's saving), which together make another €430 to €860 a week with 80 more
  orders and are in `src/strategies/lean/volume.json`, at a risk to the delivery minimum; and `longCost`,
  `chainStart` with `chainRamp`, `value` (the value table is back, fitted again), `guard` and `rescue`, which all
  lost. The tables: [`src/strategies/lean/README.md`](src/strategies/lean/README.md#the-squeeze-15-november-367).
- **In step**: no (#329). The Python version has none of these params and keeps the old tops and chain days.

### 2026-11-15: shared outcomes on (issue #360)

- **Version changed**: TypeScript.
- **What changed**: `sharedOutcome` is true by default. On today's defaults, 20 server seeds: +€305 ± 203 a week,
  ahead on 13 of 20, with 22 fewer orders at a price 2.6% higher; about +€366 ± 147 with the 15 seeds of #358. The
  table: [`src/strategies/lean/README.md`](src/strategies/lean/README.md#shared-outcomes-on-todays-defaults-15-november-360).
- **In step**: no (#329). The Python version does not have `sharedOutcome`.

### 2026-11-15: the chain model (issue #351)

- **Version changed**: TypeScript.
- **What changed**: `chainModel` (true) gives each chain the fee level from 0.85 to 1.3 that earns the most by its
  chance to book (`chain.json`, fitted by `analysis.chain_model`), ranks the chains by what they earn a car and
  posts none that earns nothing; `chainTries` (3, was always 1) lets the cars of a failed chain join two more. 20
  server seeds: +€1,126 a week, 71% of the chains book where 53% did. New params that are off: `chainFit`,
  `chainOpen`, `chainAlone`, `chainSpread` and `chainOffers` with `chainOfferSpread` (direct offers of an open
  chain, which lost €372 a week). The tables:
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#the-chain-model-a-fee-for-each-chain-by-its-chance-to-book-351).
- **In step**: no (#329). The Python version has neither the model nor the params, so it posts other chains at
  other fees.

### 2026-11-14: shared learning of a lost request (PR #358, issue #357)

- **Version changed**: TypeScript.
- **What changed**: `sharedOutcome` averages a lost request's shared demand updates over its quoted options instead
  of applying them once per option, while each option effect still learns separately. False keeps the old path. On 40
  fresh paired simulator seeds, `sharedOutcome=true,costLevel=1` gained €549.67 ± €122.80 (SE) a week over the false
  control, paired 95% CI +€301.29 to +€798.06; both had every week ranked. On 15 fresh paired server seeds, shared
  learning alone gained €447.06 ± €213.10 (SE), ahead on 10 of 15, paired 95% CI −€10.00 to +€904.11, all 15 ranked;
  `costLevel=1` was €283.57 behind shared learning alone. The default remains false. Details and raw CSVs:
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#shared-demand-outcomes-14-november-experimental).
- **In step**: no (#329). The Python version does not have `sharedOutcome`; the fee and supply changes above are also
  still outstanding there.

### 2026-11-15: no raises over the weekend (issue #347)

- **Version changed**: TypeScript.
- **What changed**: a gig whose last pickup is on the Monday after the weekend keeps its opening fee over the
  weekend and raises on that Monday from 06:00 (`rest`, true; false is the schedule before). The raises of the
  weekend reached 2 bookings a week, and Monday's first drivers took 1.54 × typical. The server check is in
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#no-raises-over-the-weekend-15-november-347).
- **In step**: no (#329). The Python version raises over the weekend.

### 2026-11-15: supply and demand (PR #342)

- **Version changed**: TypeScript.
- **What changed**: `noise` is the dealers' measured scale (0.11, was 0.28), and a charge on the cost says what an
  order costs the others: `taxLoad` 0.47 × the orders per driver that the week is heading for × the order's cost
  (`tax` and `taxEuros`, both 0, are a fixed share and a flat amount). Ten server seeds: +€972 ± 386 a week, 74 more
  orders. The fit and the table:
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#supply-and-demand-15-november).
- **In step**: no (#329). The Python version still has `noise` 0.28 and no charge.

### 2026-11-14: documentation formatting (PR #344, issue #343)

- **Version changed**: both (documentation only).
- **What changed**: Biome formatting in `src/strategies/lean/README.md` and `strategies/lean/README.md`. No decisions
  or params changed.
- **In step**: no code changed; the existing port status is unchanged (#329).

### 2026-11-14: straightening (PR #330, issue #335)

- **Version changed**: TypeScript.
- **What changed**: state rebuilt from the events and the journal; one rule for when a chain may be open, and a
  bounded chain search; one cost level (`costLevel` 0.98, the order model's mean is 1, the supply learns what the
  model leaves); one fee schedule timed by the drivers' planning and one urgent climb, in waking minutes; constants
  named or made params; `overhead`, `minMargin`, `spread` and `chainHours` removed. Results:
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#straightening-14-november-night-335).
- **In step**: no (#329). `strategies/lean/order.json` is on purpose not the copy of the TypeScript file now: the
  new file's `meanCost` is the model's mean, which the Python code would read as a cost 8% higher. Copy it when the
  Python code has `costLevel`.

### 2026-11-14: clean-up and the fixes of the open problems (issue #320)

- **Version changed**: TypeScript.
- **What changed**: the cost weights of `order.json` are fitted again on 11,108 server orders (both copies of the
  file, so the Python version prices by them too); only chains that book are posted and a car waits only for such a
  chain; `chainPatience` 1; a gig whose raises are over opens at `lateOpen` 1.25 × typical; the early fee's unit
  mix-up (#327) is fixed; the dead params and `offers.ts` are removed. Details and results:
  [`src/strategies/lean/README.md`](src/strategies/lean/README.md#clean-up-and-the-fixes-of-the-open-problems-14-november-night-320).
- **In step**: no. The Python version has the new `order.json` and the old code; #329 brings it up to date.

### 2026-11-14: Python port (PR #326, issue #323)

- **Version changed**: Python (new).
- **What changed**: `strategies/lean/` ports the TypeScript `lean` with the defaults of commit `4887cc09`, its harness
  and its ops. It played seven simulator seeds and the six roster tournament seeds on the server action for action as
  the TypeScript version: €15,093 a week on the tournament seeds, +€2,758 over `all_in`. Its deliberate differences are
  in [`strategies/lean/README.md`](strategies/lean/README.md#what-differs-from-the-typescript); none changes a
  decision.
- **In step**: yes. Open: #327, a unit mix-up in the early fee of `stepped()`, kept in both versions until it is fixed
  in both.

Changes to the TypeScript `lean` before the port are in
[`src/strategies/lean/README.md`](src/strategies/lean/README.md).
