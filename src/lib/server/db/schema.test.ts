import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, test } from 'node:test'
import { drizzle } from 'drizzle-orm/libsql'
import { relations } from './relations.ts'
import { task } from './schema.ts'

const dir = mkdtempSync(join(tmpdir(), 'db-test-'))
const url = `file:${join(dir, 'test.db')}`
after(() => rmSync(dir, { recursive: true, force: true }))

test('drizzle-kit push creates the schema and it can be queried', async () => {
  execFileSync('pnpm', ['exec', 'drizzle-kit', 'push', '--force'], {
    env: { ...process.env, DATABASE_URL: url },
    stdio: 'pipe',
  })

  const db = drizzle({ connection: { url }, relations })
  await db.insert(task).values({ title: 'Ship it' })

  const rows = await db.query.task.findMany()
  assert.equal(rows.length, 1)
  assert.equal(rows[0].title, 'Ship it')
  assert.equal(rows[0].priority, 1)
  assert.match(rows[0].id, /^[0-9a-f-]{36}$/)
})
