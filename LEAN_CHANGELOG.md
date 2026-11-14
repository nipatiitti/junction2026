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
