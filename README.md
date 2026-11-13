# sv

Everything you need to build a Svelte project, powered by [`sv`](https://github.com/sveltejs/cli).

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
