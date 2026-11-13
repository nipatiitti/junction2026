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

The system is Python, run with [uv](https://docs.astral.sh/uv/) on Python 3.15. `uv sync` installs Python and the
packages. If it cannot find Python 3.15, update uv first (`uv self update`).

The kit reads two variables. Copy `.env.example` to `.env` and put the team key in `SPREAD_KEY`. `.env` is not
committed.

```sh
SPREAD_URL=https://spread.bahnexpress.com
SPREAD_KEY=<the team key>
```

### Play a practice week

```sh
uv run --env-file .env dispatch.py --level 8 --seed spread-1   # a whole practice week with our system
uv run --env-file .env spread-starter --level 8 --seed spread-1 # the same week with the organisers' unchanged starter
uv run --env-file .env spread-reveal-csv <world id>             # write an ended week and its reveal to CSV files
uv run --env-file .env dispatch.py --final                      # play our copy of a test final or of the final
```

Leave out `--env-file .env` where the two variables are already set, as in a Claude Code cloud session.

`--level` is 1 to 8 (the final is level 8). The same seed gives the same week, so compare two versions of the system
on the same seeds. `--board` plays a ranking run: each ranking world can be played once and its score stays on the
public rankings, so agree on it in the team first.

- `dispatch.py` is our system. It starts as a copy of the organisers' starter, formatted with ruff.
- `vendor/` holds the organisers' Python kit of 13 November as a wheel. uv installs it as the package `spread`: the
  API client, its types and the unchanged starter. To take a new kit version, replace the wheel and run `uv lock`.
- `tests/` holds fast tests that need no network: `uv run pytest`.

### The baseline to beat

The unchanged starter on the seed `spread-1`. It quotes the list price, wins most cars and cannot find drivers for
them in time.

| Level | Margin      | Orders won | On time | Ranked |
| ----- | ----------- | ---------- | ------- | ------ |
| 6     | -€1,172.51  | 555        | 95.9%   | yes    |
| 7     | -€50,442.49 | 817        | 52.3%   | no     |
| 8     | -€72,612.51 | 949        | 45.5%   | no     |

We measured these with the organisers' TypeScript starter, before we chose Python. They match the handbook to the
cent, and the handbook says that both starters play alike. The Python starter has not been run against the server
yet.

### Claude Code cloud environments

Variables belong to one cloud environment. Every session that starts in that environment gets them. Each environment
that works on this repository needs both variables in its settings:

- `SPREAD_URL=https://spread.bahnexpress.com`
- `SPREAD_KEY`, the real team key. The Python client connects straight to the server, so a placeholder with a network
  secret does not work.

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
