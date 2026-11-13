# junction2026

Our entry for **Spread** by Bahn at Junction 2026: a system that does a car transport dispatcher's job for one
simulated week in Finland. It quotes prices to dealers and posts gigs to freelance drivers through the Spread API.
Everything about the challenge is linked from <https://spread.bahnexpress.com/llms.txt>.

## Challenge docs

Short versions of the Spread challenge documents (rules, handbook, API, judging) are in [`docs/`](docs/README.md).

## Stack

Plain TypeScript on Node 22.18+ (no build step: Node runs `.ts` files directly), pnpm, Biome, and `node --test`.
Code lives in `src/`; tests sit next to the code as `*.test.ts`.

```sh
pnpm install
pnpm check   # type check
pnpm lint    # lint and format check, no writes
pnpm format  # format, organise imports and apply safe lint fixes
pnpm test    # all tests
node --test src/path/to/file.test.ts   # one test file
```

In VS Code, install the recommended Biome extension to format on save.

## Working in parallel

Four of us work at once, each with our own agent. Every change goes issue → branch (or worktree) → PR, as described
in `AGENTS.md`.
