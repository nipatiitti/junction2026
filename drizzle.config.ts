import { defineConfig } from 'drizzle-kit'

if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not set')

// Push flow: `pnpm db:push` syncs the schema straight to the database, no migration files.
export default defineConfig({
  schema: './src/lib/server/db/schema.ts',
  dialect: 'sqlite',
  dbCredentials: { url: process.env.DATABASE_URL },
  verbose: true,
})
