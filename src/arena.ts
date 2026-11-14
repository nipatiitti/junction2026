/** The arena: an OFFLINE week that scores strategies in seconds, on saved weeks, without the server.
 *
 * `node src/arena.ts <strategy>[:key=value,...] [more] --seeds spread-1,spread-9 [--level 8]`
 *
 * It drives a real Strategy through the harness's own Desk (with a fake world that accepts every action) and a
 * simple world model. The model, kept simple on purpose:
 * - Requests: the `price_request` events of one saved week of the seed, in time order, with its map and drivers.
 *   The same seed and level give the same requests, so any saved week will do.
 * - Winning: each request option has a hidden threshold (a ratio of the list price). From every saved week of the
 *   seed (quote_facts in the database), it is the midpoint between the highest taken ratio and the lowest lost
 *   ratio, each divided by (1 + dealer trust / 100); 1.29 when there is no data, the edge itself when only one side
 *   is known. In the arena the threshold is that times (1 + the arena's trust for the dealer / 100). Of the options
 *   quoted under their thresholds the dealer takes the fastest. The order is the one a saved week won for that
 *   request and option, else one built from the request.
 * - Driver cost: the strategy's first gig for the order (as posted on the win) books at the first fee step at or
 *   above X times the order's typical fee (quote_facts reference_fee_cents), X lognormal with median 1.15 and sd 0.2,
 *   seeded per order. A schedule that never gets there before the last pickup makes the order late: it costs 25% of
 *   its price plus the top fee. On-time orders raise the dealer's trust by one (up to 25) at their deadline.
 * - Ignored: reprices, withdrawals, direct offers, combined gigs' savings beyond the first gig, changes,
 *   cancellations, failed visits, drops, deadline warnings, notes and rate limits.
 */

import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'
import type {
  Action,
  ActionResult,
  DeskEvent,
  DeskSnapshot,
  DriverProfile,
  Order,
  PostAction,
  PriceRequest,
  World,
  WorldMap,
} from '../vendor/spread-typescript/spread.ts'
import { Desk } from './harness/desk.ts'
import { Guard } from './harness/guard.ts'
import { Journal } from './harness/journal.ts'
import { runFromSpec } from './harness/params.ts'
import { STRATEGIES } from './strategies/index.ts'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const RUNS = path.join(ROOT, 'data', 'scrape', 'runs')
const DB = process.env.ARENA_DB || '/home/nipatiitti/projects/hackathons/junction2026/out/spread.sqlite'
const PRIOR = 1.29
const SPEED = ['same_day', 'next_day', 'standard', 'economy', 'flex'] // fastest first; unknown kinds last

type SeedData = {
  requests: PriceRequest[]
  map: WorldMap
  roster: DriverProfile[]
  endsAt: number
  threshold: Map<string, number> // "<request> <option>" -> ratio at trust 0
  typical: Map<string, number> // "<request> <option>" -> typical fee in cents
  orders: Map<string, Order> // "<request> <option>" -> the order a saved week won
}

const gz = (file: string) => gunzipSync(readFileSync(file)).toString('utf-8')

function load(seed: string, level: number): SeedData {
  const dir = path.join(RUNS, `L${level}`, seed)
  const worlds = readdirSync(dir).sort()
  if (worlds.length === 0) throw new Error(`no saved week for ${seed} at level ${level}`)
  const orders = new Map<string, Order>()
  let requests: PriceRequest[] = []
  let roster: DriverProfile[] = []
  let endsAt = 7 * 24 * 60
  for (const world of worlds) {
    const folder = path.join(dir, world)
    let text: string
    try {
      text = gz(path.join(folder, 'events.jsonl.gz'))
    } catch {
      continue
    }
    const events = text
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as DeskEvent)
    if (requests.length === 0) {
      requests = events.flatMap((e) => (e.kind === 'price_request' ? [e.request] : []))
      roster = JSON.parse(gz(path.join(folder, 'drivers.json.gz')))
      endsAt = (JSON.parse(gz(path.join(folder, 'snapshot.json.gz'))) as DeskSnapshot).endsAt
    }
    for (const e of events) if (e.kind === 'order_won') orders.set(`${e.order.id} ${e.order.option}`, e.order)
  }
  const map = JSON.parse(readFileSync(path.join(RUNS, 'map.json'), 'utf-8')) as WorldMap
  const db = new DatabaseSync(DB, { readOnly: true })
  const rows = db
    .prepare(
      `select q.request_id r, q.option o, q.ratio ratio, q.outcome outcome, q.taken taken,
              coalesce(q.dealer_trust, 0) trust, q.reference_fee_cents fee
       from quote_facts q join weeks w on w.id = q.week_id where w.seed = ? and w.level = ?`,
    )
    .all(seed, level) as {
    r: string
    o: string
    ratio: number | null
    outcome: string
    taken: number
    trust: number
    fee: number | null
  }[]
  db.close()
  const hi = new Map<string, number>()
  const lo = new Map<string, number>()
  const typical = new Map<string, number>()
  for (const row of rows) {
    const key = `${row.r} ${row.o}`
    if (row.fee) typical.set(key, row.fee)
    if (row.ratio === null) continue
    const base = row.ratio / (1 + Math.min(25, row.trust) / 100)
    if (row.taken === 1) hi.set(key, Math.max(hi.get(key) ?? 0, base))
    else if (row.outcome === 'lost') lo.set(key, Math.min(lo.get(key) ?? Infinity, base))
  }
  const threshold = new Map<string, number>()
  for (const key of new Set([...hi.keys(), ...lo.keys()])) {
    const h = hi.get(key)
    const l = lo.get(key)
    threshold.set(key, h !== undefined && l !== undefined && l > h ? (h + l) / 2 : (h ?? Math.min(l ?? PRIOR, PRIOR)))
  }
  return { requests, map, roster, endsAt, threshold, typical, orders }
}

/** A seeded random number in [0, 1) from a text. */
function rand(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  h = Math.imul(h ^ (h >>> 15), 2246822507)
  h = Math.imul(h ^ (h >>> 13), 3266489909)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}

/** X, lognormal with median 1.15 and log sd 0.2, seeded by the order. */
function bookingX(seed: string, orderId: string): number {
  const u1 = Math.max(1e-9, rand(`${seed} ${orderId} a`))
  const u2 = rand(`${seed} ${orderId} b`)
  const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
  return 1.15 * Math.exp(0.2 * z)
}

function orderOf(data: SeedData, request: PriceRequest, kind: string, price: number): Order {
  const saved = data.orders.get(`${request.id} ${kind}`)
  const option = request.options.find((o) => o.kind === kind)!
  const base: Order = saved
    ? structuredClone(saved)
    : ({
        id: request.id,
        dealerId: request.dealerId,
        option: kind,
        priceCents: price,
        deadline: option.deadline,
        legs: structuredClone(request.legs),
        status: 'waiting',
        deliveredAt: request.legs.map(() => null),
        lastPickupAt: option.deadline - 120,
      } as unknown as Order)
  return { ...base, priceCents: price, status: 'waiting', deliveredAt: base.legs.map(() => null) }
}

class QuietJournal extends Journal {
  override read() {
    return []
  }
  override write(): void {}
}

type Result = { margin: number; revenue: number; won: number; fees: number; late: number; seconds: number }

async function play(name: string, spec: string, seed: string, level: number, data: SeedData): Promise<Result> {
  const run = runFromSpec(spec)
  const kind = STRATEGIES[run.name]
  if (!kind) throw new Error(`no strategy ${run.name}: ${Object.keys(STRATEGIES).join(', ')}`)
  const started = performance.now()
  let gigNo = 0
  const fake = {
    id: `arena-${name}-${seed}`,
    act: async (actions: Action[]): Promise<ActionResult[]> =>
      actions.map((a) => (a.type === 'post' ? { ok: true, id: `G${++gigNo}` } : { ok: true })) as ActionResult[],
  } as unknown as World
  const setup = { roster: data.roster, map: data.map, level }
  const guard = new Guard()
  const strategy = guard.run('build', () => kind.build(setup, { ...kind.defaults, ...run.params }))
  if (!strategy) throw new Error(`${name} did not build: ${guard.messages.get('build error')}`)
  const snapshot = { now: 0, endsAt: data.endsAt, gigs: [], orders: [], openRequests: [] } as unknown as DeskSnapshot
  const desk = new Desk(fake, strategy, guard, snapshot, new QuietJournal(fake.id))

  const trust = new Map<string, number>()
  type Item = { at: number; order: number; run: () => Promise<void> }
  const queue: Item[] = []
  let n = 0
  const push = (at: number, run: () => Promise<void>) => queue.push({ at, order: n++, run })
  let seq = 0
  const r: Result = { margin: 0, revenue: 0, won: 0, fees: 0, late: 0, seconds: 0 }

  const decide = async (request: PriceRequest) => {
    const sent = [...desk.outbox, ...desk.inFlight]
    void sent
    const quote = quotes.get(request.id)
    const t = trust.get(request.dealerId) ?? 0
    const under = request.options.filter((o) => {
      const price = quote?.[o.kind]
      if (price === undefined) return false
      const th = (data.threshold.get(`${request.id} ${o.kind}`) ?? PRIOR) * (1 + t / 100)
      return price <= th * o.listPriceCents
    })
    under.sort(
      (a, b) => ((SPEED.indexOf(a.kind) + 99) % 99) - ((SPEED.indexOf(b.kind) + 99) % 99) || a.deadline - b.deadline,
    )
    const pick = under[0]
    desk.now = request.respondBy
    if (!pick) {
      await desk.handle({ seq: ++seq, at: request.respondBy, kind: 'order_lost', requestId: request.id } as DeskEvent)
      return
    }
    const order = orderOf(data, request, pick.kind, quote![pick.kind]!)
    await desk.handle({ seq: ++seq, at: request.respondBy, kind: 'order_won', order } as DeskEvent)
    await desk.send()
    await desk.settle()
    r.won++
    r.revenue += order.priceCents
    const typical = data.typical.get(`${request.id} ${pick.kind}`) ?? order.priceCents
    const gigs = desk.gigsOf(order.id)
    const x = bookingX(seed, order.id)
    let late = gigs.length === 0
    for (const gigId of gigs) {
      const post = desk.posts.get(gigId)!
      const share = post.stops.filter((s) => s.kind === 'pickup' && s.orderId === order.id).length / order.legs.length
      const steps = [...post.schedule].sort((a, b) => a.at - b.at)
      const step = steps.find((s) => s.feeCents >= x * typical * share && s.at <= order.lastPickupAt)
      if (step) r.fees += step.feeCents
      else {
        late = true
        r.fees += Math.max(0, ...steps.map((s) => s.feeCents))
      }
    }
    if (late) {
      r.late++
      r.fees += Math.round(order.priceCents * 0.25)
    } else
      push(order.deadline, async () => {
        trust.set(order.dealerId, Math.min(25, (trust.get(order.dealerId) ?? 0) + 1))
        for (const leg of order.legs.keys())
          await desk.handle({
            seq: ++seq,
            at: order.deadline,
            kind: 'delivered',
            gigId: gigs[0] ?? '',
            orderId: order.id,
            leg,
            placeId: order.legs[leg]!.delivery.placeId,
          } as DeskEvent)
      })
  }

  // The quotes as the desk sent them, read from the outbox after each request.
  const quotes = new Map<string, Record<string, number>>()
  for (const request of data.requests)
    push(request.arrivedAt, async () => {
      desk.now = request.arrivedAt
      await desk.handle({ seq: ++seq, at: request.arrivedAt, kind: 'price_request', request } as DeskEvent)
      for (const a of desk.outbox) if (a.type === 'quote') quotes.set(a.requestId, a.prices as Record<string, number>)
      await desk.send()
      await desk.settle()
      push(request.respondBy, () => decide(request))
    })

  const every = strategy.every
  if (every !== null)
    for (let t = every; t < data.endsAt; t += Math.max(1, every))
      push(t, async () => {
        desk.now = Math.max(desk.now, t)
        await desk.tick()
        await desk.send()
        await desk.settle()
      })

  while (queue.length > 0) {
    let best = 0
    for (let i = 1; i < queue.length; i++)
      if (queue[i]!.at < queue[best]!.at || (queue[i]!.at === queue[best]!.at && queue[i]!.order < queue[best]!.order))
        best = i
    const [item] = queue.splice(best, 1)
    if (item!.at > data.endsAt) break
    await item!.run()
  }
  r.margin = r.revenue - r.fees
  r.seconds = (performance.now() - started) / 1000
  return r
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  const flag = (name: string) => {
    const i = args.indexOf(name)
    return i >= 0 ? args.splice(i, 2)[1] : undefined
  }
  const seeds = (flag('--seeds') ?? 'spread-1').split(',').filter(Boolean)
  const level = Number(flag('--level') ?? 8)
  const specs = args.filter((a) => !a.startsWith('--'))
  if (specs.length === 0) {
    console.error('usage: node src/arena.ts <strategy>[:key=value,...] [...] --seeds spread-1,spread-9 [--level 8]')
    process.exit(2)
  }
  const eur = (cents: number) => `${(cents / 100).toFixed(0)}`.padStart(9)
  console.log(
    `${'strategy'.padEnd(28)} ${'seed'.padEnd(10)} ${'margin'.padStart(9)} ${'revenue'.padStart(9)} ${'won'.padStart(5)} ${'fees'.padStart(9)} ${'late'.padStart(5)} ${'secs'.padStart(5)}`,
  )
  for (const seed of seeds) {
    const data = load(seed, level)
    for (const spec of specs) {
      const r = await play(spec, spec, seed, level, data)
      console.log(
        `${spec.padEnd(28)} ${seed.padEnd(10)} ${eur(r.margin)} ${eur(r.revenue)} ${String(r.won).padStart(5)} ${eur(r.fees)} ${String(r.late).padStart(5)} ${r.seconds.toFixed(1).padStart(5)}`,
      )
    }
  }
}

await main()
