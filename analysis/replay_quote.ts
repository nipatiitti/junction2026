/** Replays the quote models on the level 8 quote probes, offline, against a fixed multiplier on the list price.
 *
 *     node analysis/replay_quote.ts [out/spread.sqlite]
 *
 * Each probed request is one where we know the flip: the highest price that wins it, at trust 0. In each world the
 * requests come in arrival order; the model quotes the first option, wins when its price is at or under the flip,
 * and learns from the answer as it would live. A car costs 0.8, 1.0 or 1.21 times the typical fee. The table gives
 * the profit a request (euros), the share won, and finding 13's best fixed multiplier for comparison. */
import { DatabaseSync } from 'node:sqlite'
import {
  bestQuote,
  createQuoteState,
  type Option,
  observe,
  type QuoteOptions,
  quoteParams,
  recordQuote,
} from '../src/models/quote/index.ts'
import type { DeskEvent, PriceRequest } from '../vendor/spread-typescript/types.ts'

type Probe = {
  seed: string
  request_id: string
  option: Option
  dealer_id: string
  arrived_at: number
  delivery_place: string
  list_price_cents: number
  reference_fee_cents: number
  flip_cents: number
}

const db = new DatabaseSync(process.argv[2] ?? 'out/spread.sqlite', { readOnly: true })
const rows = db
  .prepare(
    `select seed, request_id, option, dealer_id, arrived_at, delivery_place, list_price_cents, reference_fee_cents,
            flip_cents
     from probes where level = 8 and flip_cents is not null and monotone = 1 and error is null
       and option = json_extract(options, '$[0]')
     order by seed, arrived_at, request_id`,
  )
  .all() as Probe[]
const near: Record<string, Record<string, number>> = {}
for (const { seed, place, n } of db
  .prepare(
    `select w.seed seed, t.place place, max(t.drivers_near) n from town_days t join weeks w on w.id = t.week_id
     where t.level = 8 group by 1, 2`,
  )
  .all() as { seed: string; place: string; n: number }[]) {
  near[seed] ??= {}
  near[seed][place] = n
}
const worlds = Map.groupBy(rows, (r) => r.seed)

/** Euros a request and the share won, for one way of pricing, over every probed request. */
function play(variant: QuoteOptions, cost: number): [number, number] {
  const params = quoteParams(variant)
  let profit = 0
  let won = 0
  for (const [seed, probes] of worlds) {
    const state = createQuoteState(near[seed] ?? {})
    let seq = 0
    for (const r of probes) {
      const request = toRequest(r)
      const at = r.arrived_at
      observe(state, { seq: seq++, at, kind: 'price_request', request }, params)
      const decision = bestQuote(request, { [r.option]: cost * r.reference_fee_cents }, state, params, at)
      recordQuote(state, request, decision.prices, params)
      const price = decision.prices[r.option] ?? Number.POSITIVE_INFINITY
      const win = !decision.decline && price <= r.flip_cents
      const answer: DeskEvent = win
        ? { seq: seq++, at: request.respondBy, kind: 'order_won', order: toOrder(request, r.option, price) }
        : { seq: seq++, at: request.respondBy, kind: 'order_lost', requestId: request.id }
      observe(state, answer, params)
      if (win) {
        profit += price - cost * r.reference_fee_cents
        won += 1
      }
    }
  }
  return [profit / rows.length / 100, won / rows.length]
}

/** The fixed multiplier `m` on the list price. */
function fixed(m: number, cost: number): [number, number] {
  let profit = 0
  let won = 0
  for (const r of rows) {
    const price = Math.round(m * r.list_price_cents)
    if (price <= r.flip_cents) {
      profit += price - cost * r.reference_fee_cents
      won += 1
    }
  }
  return [profit / rows.length / 100, won / rows.length]
}

function toRequest(r: Probe): PriceRequest {
  const place = (placeId: string) => ({ placeId, privateAddress: false, window: { from: 0, to: 0 }, hours: null })
  const car = { premium: false, electric: false, chargePercent: null }
  return {
    id: `${r.seed}/${r.request_id}`,
    dealerId: r.dealer_id,
    batchId: null,
    arrivedAt: r.arrived_at,
    respondBy: r.arrived_at + 15,
    legs: [{ car, pickup: place(''), delivery: place(r.delivery_place) }],
    options: [{ kind: r.option, deadline: 0, listPriceCents: r.list_price_cents }],
    referenceFeeCents: r.reference_fee_cents,
    note: null,
  }
}

function toOrder(request: PriceRequest, option: Option, priceCents: number) {
  const { id, dealerId, legs } = request
  return {
    id,
    dealerId,
    option,
    priceCents,
    deadline: 0,
    legs,
    status: 'waiting' as const,
    deliveredAt: [],
    lastPickupAt: 0,
  }
}

const cell = ([euros, share]: [number, number]) =>
  `€${euros.toFixed(2).padStart(6)} ${(100 * share).toFixed(0).padStart(3)}%`
const variants: [string, QuoteOptions][] = [
  ['bestQuote, trust value off', { trustValue: 0 }],
  ['bestQuote (default flags)', {}],
  ['bestQuote, no lane, no ladder', { trustValue: 0, flags: { lane: false, ladder: false } }],
  ['bestQuote, cold start', { trustValue: 0, cold: true }],
  ['50% learner (pricing: median)', { trustValue: 0, flags: { pricing: 'median' } }],
]
const costs = [0.8, 1.0, 1.21]
console.log(`${rows.length} probed requests in ${worlds.size} worlds, first option, trust 0, Monday and Tuesday`)
console.log(`${'car cost × typical fee'.padEnd(32)}${costs.map((c) => `${c.toFixed(2)}`.padStart(14)).join('')}`)
const line = (name: string, f: (cost: number) => [number, number]) =>
  console.log(`${name.padEnd(32)}${costs.map((c) => cell(f(c)).padStart(14)).join('')}`)
line('fixed 1.26 × list', (c) => fixed(1.26, c))
line('best fixed multiplier (hindsight)', (c) => {
  const grid = Array.from({ length: 81 }, (_, i) => 1 + i / 100)
  return grid.map((m) => fixed(m, c)).reduce((a, b) => (b[0] > a[0] ? b : a))
})
for (const [name, variant] of variants) line(name, (c) => play(variant, c))
line('every quote at its flip', (c) => {
  const kept = rows.map((r) => Math.max(0, r.flip_cents - c * r.reference_fee_cents))
  return [kept.reduce((a, b) => a + b, 0) / rows.length / 100, kept.filter((k) => k > 0).length / rows.length]
})
const started = performance.now()
const params = quoteParams()
const state = createQuoteState()
const request = toRequest(rows[0])
const n = 2000
for (let i = 0; i < n; i++) bestQuote(request, { [rows[0].option]: request.referenceFeeCents }, state, params)
console.log(`bestQuote takes ${((performance.now() - started) / n).toFixed(3)} ms a request`)
