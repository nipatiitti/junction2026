# sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

## Spread challenge

Our Junction 2026 challenge is [Spread](https://spread.bahnexpress.com/llms.txt), by Bahn. We build a system that does a
car transport dispatcher's job for one simulated week in Finland: it quotes car dealers and pays freelance drivers to
move the cars. The score is the gross margin, and a system is ranked only when at least 90% of its orders arrive on
time.

- Test finals: Saturday 14 November at 14:00 and at 20:00, Helsinki time. Each takes about 19 minutes.
- The final: Sunday 15 November at 08:00, Helsinki time. It takes about 34 minutes and is level 8.
- Read `docs/spread/HANDBOOK.md` first. `RULES.md` and `API.md` are next to it.
- Our team's weeks, rankings and key: https://spread.bahnexpress.com/team

### Setup

The kit reads two variables. Copy `.env.example` to `.env` and put the team key in `SPREAD_KEY`. `.env` is not
committed.

```sh
SPREAD_URL=https://spread.bahnexpress.com
SPREAD_KEY=<the team key>
```

### Play a practice week

```sh
pnpm spread --level 8 --seed spread-1   # a whole practice week; the same seed gives the same week
pnpm spread:reveal <world id>           # write an ended week and its reveal to CSV files
pnpm spread:final                       # play our copy of a test final or of the final
```

`--level` is 1 to 8 (the final is level 8). `--board` plays a ranking run: each ranking world can be played once and
its score stays on the public rankings, so agree on it in the team first. A level 8 week takes about five minutes from
a Claude Code cloud session.

`spread/` holds the organisers' TypeScript kit of 13 November, formatted with Biome. It needs no packages and runs on
Node 22.18 or later. `starter.ts` is the system that we change. `spread.ts` and `types.ts` are the organisers' client:
keep them as they are, so a new kit version is a copy and a `pnpm format`.

### The baseline to beat

The unchanged starter on the seed `spread-1`. It quotes the list price, wins most cars and cannot find drivers for
them in time.

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

### Claude Code cloud environments

Variables and secrets belong to one cloud environment. Every session that starts in that environment gets them. The
`Junction2026` environment has:

- the variable `SPREAD_URL=https://spread.bahnexpress.com`;
- the variable `SPREAD_KEY=proxy-injected`, a placeholder;
- a network secret for the host `spread.bahnexpress.com` that holds the real team key. The session's proxy puts the
  real key on each request, so the key is not stored as plain text.

`pnpm spread` and `pnpm spread:reveal` send their requests through that proxy, so they work with the placeholder. To
use another cloud environment, add the same two variables and the network secret in its settings.

A final is different: it sends events over a WebSocket, and a WebSocket cannot go through the proxy. To play a final
from a cloud session, put the real key in that environment's `SPREAD_KEY` variable. `pnpm spread:final` then connects
without the proxy. On your own computer, `.env` is enough for all three commands.

## Creating a project

If you're seeing this, you've probably already done this step. Congrats!

```sh
# create a new project
npx sv create my-app
```

To recreate this project with the same configuration:

```sh
# recreate this project
pnpm dlx sv@1.3.0 create --template minimal --types ts --add experimental="features:async,remoteFunctions" ai-tools="ide:claude-code,opencode,vscode+delivery:plugin+tools:mcp,svelte-code-writer,svelte-core-bestpractices,svelte-file-editor+mcpSetup:local+optInSkills:none" drizzle="database:sqlite+sqlite:libsql" sveltekit-adapter="adapter:node" tailwindcss="plugins:none" playwright="demo:no" --install pnpm .
```

## Adding features

Add features to your project with `sv add`:

```sh
npx sv add
```

For example, to add Tailwind CSS:

```sh
npx sv add tailwindcss
```

## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

## Building

To create a production version of your app:

```sh
npm run build
```

You can preview the production build with `npm run preview`.

## Code style

[Biome](https://biomejs.dev) lints and formats TypeScript, Svelte, CSS and JSON (config in `biome.json`:
2 spaces, no semicolons, 120 columns, trailing commas).

```sh
pnpm format # format, organise imports and apply safe lint fixes
pnpm lint   # check only, no writes
```

In VS Code, install the recommended Biome extension to format on save.

## Database

SQLite through [Drizzle](https://orm.drizzle.team) 1.0 (RC) and libSQL. Copy `.env.example` to `.env` first.

- Tables live in `src/lib/server/db/schema.ts`, relations in `src/lib/server/db/relations.ts`.
- There are no migration files. After changing the schema, push it straight to the database:

```sh
pnpm db:push   # sync the schema to DATABASE_URL
pnpm db:studio # browse the data
```

`pnpm test:unit` pushes the schema to a throwaway database and queries it.
