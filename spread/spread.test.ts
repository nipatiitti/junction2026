import assert from 'node:assert/strict'
import { test } from 'node:test'
import { Client, SpreadError } from './spread.ts'

// Port 9 is the discard port: a request that slipped past the client's checks would fail as unreachable.
const offline = { url: 'http://127.0.0.1:9', key: 'test-key' }

test('the client does not start without a team key', () => {
  const saved = process.env.SPREAD_KEY
  delete process.env.SPREAD_KEY
  try {
    assert.throws(() => new Client({ url: offline.url }), /SPREAD_KEY is not set/)
  } finally {
    if (saved !== undefined) process.env.SPREAD_KEY = saved
  }
})

test('the client refuses an address that is not a URL', () => {
  assert.throws(() => new Client({ ...offline, url: 'spread.bahnexpress.com' }), /SPREAD_URL is/)
})

test('the client refuses a number with a fraction before it sends anything', async () => {
  const world = new Client(offline).world('w-test')
  const quote = { type: 'quote' as const, requestId: 'R00001', prices: { next_day: 12345.5 } }
  await assert.rejects(world.act([quote]), (error: unknown) => {
    assert.ok(error instanceof SpreadError)
    assert.match(error.message, /12345\.5 is not a whole number/)
    assert.equal(error.field, '[0].prices.next_day')
    return true
  })
})
