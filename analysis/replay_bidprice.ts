/** Feeds saved level 8 weeks through the bidprice strategy, offline: every event through `observe`, every request
 * through `quote`, and a gig for each order that the saved week won, after each deadline warning, failed visit and
 * expired gig. The saved week's own quotes and gigs go to the strategy's `sent`, as the desk's journal does on a
 * rebuild, so the quote learner waits for the answers the week gave and the fee learner follows its gigs. Not a test: it prints what the strategy would do, to read the numbers.
 *
 *     node analysis/replay_bidprice.ts [weeks per seed, default 1] [key=value ...]
 *
 * The weeks are those played by `dispatch.py` (policy `dispatch`) under data/scrape/runs/L8/. */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { gunzipSync } from 'node:zlib'
import { canServe } from '../src/ops/index.ts'
import { requestFeeGig } from '../src/strategies/bidprice/fees.ts'
import { bidprice } from '../src/strategies/bidprice/index.ts'
import type { BidPriceParams } from '../src/strategies/bidprice/params.ts'
import type { Books, GigNeed, GigPlan, Prices } from '../src/strategy.ts'
import type {
  Action,
  ActionResult,
  DeskEvent,
  DeskSnapshot,
  DriverProfile,
  Gig,
  Order,
  PostAction,
  PriceRequest,
  Reveal,
  WorldMap,
} from '../vendor/spread-typescript/types.ts'

const RUNS = 'data/scrape/runs/L8'
const perSeed = Number(process.argv[2] ?? 1)
const overrides = Object.fromEntries(
  process.argv.slice(3).map((pair) => {
    const [key, text = ''] = pair.split(/=(.*)/s)
    let value: unknown = text
    try {
      value = JSON.parse(text)
    } catch {}
    return [key, value]
  }),
) as Partial<BidPriceParams>
const map = JSON.parse(readFileSync('data/scrape/runs/map.json', 'utf8')) as WorldMap
const gz = (path: string) => gunzipSync(readFileSync(path)).toString('utf8')

type Probe = {
  costs(request: PriceRequest, now: number): Partial<Record<string, number>>
  observe(event: DeskEvent, books: Books): void
  sent(action: Action, result: ActionResult, books: Books): void
  quote(request: PriceRequest, books: Books): Prices | null
  tick(books: Books): Action[]
  gig(need: GigNeed, books: Books): GigPlan | GigPlan[]
  summary(): string
  quotes: unknown
  fees: unknown
}

/** A running mean and the values, for quantiles. */
class Stat {
  values: number[] = []
  add(x: number) {
    if (Number.isFinite(x)) this.values.push(x)
  }
  toString() {
    const v = [...this.values].sort((a, b) => a - b)
    if (v.length === 0) return 'n=0'
    const q = (p: number) => v[Math.min(v.length - 1, Math.floor(p * v.length))]!.toFixed(2)
    const mean = v.reduce((s, x) => s + x, 0) / v.length
    return `mean ${mean.toFixed(2)} (p10 ${q(0.1)}, p50 ${q(0.5)}, p90 ${q(0.9)}), n=${v.length}`
  }
}

const stats = new Map<string, Stat>()
const stat = (name: string) => stats.get(name) ?? stats.set(name, new Stat()).get(name)!
const counts = new Map<string, number>()
const count = (name: string, n = 1) => counts.set(name, (counts.get(name) ?? 0) + n)
const slowest = new Map<string, number>()

function timed<T>(call: string, run: () => T): T | undefined {
  const started = performance.now()
  try {
    return run()
  } catch (error) {
    count(`fault: ${call}: ${error instanceof Error ? error.message.replace(/\bR\d+/g, '#') : String(error)}`)
    return undefined
  } finally {
    const ms = performance.now() - started
    slowest.set(call, Math.max(slowest.get(call) ?? 0, ms))
    stat(`ms a call: ${call}`).add(ms)
  }
}

function weeks(): string[] {
  const out: string[] = []
  for (const seed of readdirSync(RUNS).sort()) {
    const worlds = readdirSync(join(RUNS, seed))
      .map((world) => join(RUNS, seed, world))
      .filter((dir) => {
        try {
          return JSON.parse(readFileSync(join(dir, 'meta.json'), 'utf8')).policy === 'dispatch'
        } catch {
          return false
        }
      })
      .sort()
    out.push(...worlds.slice(0, perSeed))
  }
  return out
}

function play(dir: string): void {
  const events = gz(join(dir, 'events.jsonl.gz'))
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as DeskEvent)
  const roster = JSON.parse(gz(join(dir, 'drivers.json.gz'))) as DriverProfile[]
  const snapshot = JSON.parse(gz(join(dir, 'snapshot.json.gz'))) as DeskSnapshot
  const reveal = JSON.parse(gz(join(dir, 'reveal.json.gz'))) as Reveal
  const sent = new Map(reveal.requests.map((r) => [r.request.id, r]))
  // The week's answers are to the saved week's quotes, not ours: they go through `sent`, as the journal would.
  const observe = (s: Probe, event: DeskEvent) => {
    s.observe(event, books)
    if (event.kind !== 'price_request') return
    const prices = sent.get(event.request.id)?.quote
    if (prices)
      s.sent({ type: 'quote', requestId: event.request.id, prices }, { ok: true, id: event.request.id }, books)
  }
  const sendPost = (s: Probe, post: PostAction, gig: Gig) => {
    const now = books.now
    books.now = gig.postedAt
    s.sent(post, { ok: true, id: gig.id }, books)
    books.now = now
  }
  const setup = { roster, map, level: 8 }
  const params = { ...bidprice.defaults, ...overrides }
  const strategy = bidprice.build(setup, params) as unknown as Probe
  const restarted = bidprice.build(setup, params) as unknown as Probe
  // A third copy runs the tick, and hears its own reprices back as sent, as the desk would tell it.
  const ticker = bidprice.build(setup, params) as unknown as Probe
  let nextTick = 0

  const requests = new Map<string, PriceRequest>()
  const orders = new Map<string, Order>()
  const posts = new Map<string, PostAction>()
  const urgent = new Set<string>()
  const finished = new Set<string>() // gigs delivered, expired or cancelled
  const booked = new Set<string>()
  const gigsOf = (orderId: string) =>
    [...posts]
      .filter(([id, post]) => !finished.has(id) && post.stops.some((stop) => stop.orderId === orderId))
      .map(([id]) => id)
  const books: Books = {
    now: 0,
    endsAt: snapshot.endsAt,
    requests,
    orders,
    posts,
    legGigs: new Map(),
    booked,
    urgent,
    gigsOf,
  }

  const untold = [...snapshot.gigs].sort((a, b) => a.postedAt - b.postedAt)
  const told = new Set<string>()
  const tell = (gig: Gig) => {
    if (told.has(gig.id)) return
    told.add(gig.id)
    const post: PostAction = { type: 'post', stops: gig.stops, audience: gig.audience, schedule: gig.schedule }
    posts.set(gig.id, post)
    for (const s of [strategy, restarted, ticker]) timed('sent', () => sendPost(s, post, gig))
  }

  const gigOf = (need: GigNeed, what: string) => {
    const plans = [timed('gig', () => strategy.gig(need, books)) ?? []].flat()
    if (plans.length === 0) count(`${what}: no plan (starter's gig)`)
    if (plans.length > 1) count(`${what}: split into ${plans.length} gigs`)
    const typical = requests.get(need.order.id)?.referenceFeeCents ?? 0
    for (const plan of plans) {
      const schedule = plan.schedule
      const cars = plan.stops.filter((s) => s.kind === 'pickup').length / need.order.legs.length
      const fee = typical * cars
      if (schedule.length === 0) count(`${what}: empty schedule`)
      if (schedule.some((step, i) => i > 0 && step.feeCents < schedule[i - 1]!.feeCents)) count(`${what}: falling`)
      if (schedule.some((step, i) => i > 0 && step.at <= schedule[i - 1]!.at)) count(`${what}: times not rising`)
      if (schedule.some((step) => !Number.isInteger(step.feeCents) || !Number.isInteger(step.at)))
        count(`${what}: fractions (the harness rounds)`)
      if ((schedule[0]?.at ?? 0) < books.now - 1) count(`${what}: starts in the past`)
      stat(`${what}: opening fee / typical`).add((schedule[0]?.feeCents ?? 0) / fee)
      stat(`${what}: top fee / typical`).add((schedule.at(-1)?.feeCents ?? 0) / fee)
      stat(`${what}: steps`).add(schedule.length)
      const top = schedule.find((step) => step.feeCents >= 1.49 * fee)
      if (what === 'won')
        stat('won: hours from top fee to last pickup').add(top ? (need.order.lastPickupAt - top.at) / 60 : Number.NaN)
      if (top === undefined && what === 'won') count('won: never reaches 1.5 × typical')
    }
  }

  const half = events[Math.floor(events.length / 2)]!.seq
  for (const event of events) {
    books.now = event.at
    const named =
      'gigId' in event ? [event.gigId] : event.kind === 'order_cancelled' ? event.gigs.map((g) => g.gigId) : []
    for (const gig of untold) if (gig.postedAt < event.at || named.includes(gig.id)) tell(gig)
    for (const s of [strategy, restarted, ticker]) timed('observe', () => observe(s, event))
    if (event.kind === 'gig_booked') booked.add(event.gigId)
    if (event.kind === 'gig_dropped' || event.kind === 'no_show') booked.delete(event.gigId)
    if (event.kind === 'delivered' || event.kind === 'gig_expired') finished.add(event.gigId)
    if (event.kind === 'order_cancelled') for (const g of event.gigs) finished.add(g.gigId)
    if (event.at >= nextTick) {
      nextTick = event.at + 30
      const actions = timed('tick', () => ticker.tick(books)) ?? []
      stat('tick: reprices a tick').add(actions.length)
      for (const action of actions) {
        if (action.type !== 'reprice') continue
        count('tick: reprices')
        const steps = action.schedule
        if (steps.length === 0 || steps.length > 48) count('tick: bad step count')
        if (steps.some((step, i) => i > 0 && step.feeCents < steps[i - 1]!.feeCents)) count('tick: falling')
        if ((steps[0]?.at ?? 0) < event.at) count('tick: starts in the past')
        const post = posts.get(action.gigId)
        const order = post && orders.get(post.stops[0]!.orderId)
        const typical = order && requests.get(order.id)?.referenceFeeCents
        if (typical) stat('tick: reprice top / typical').add((steps.at(-1)?.feeCents ?? 0) / typical)
        ticker.sent(action, { ok: true, id: action.gigId }, books)
      }
    }

    if (event.kind === 'price_request') {
      const { request } = event
      requests.set(request.id, request)
      count('requests')
      const prices = timed('quote', () => strategy.quote(request, books))
      const costs = strategy.costs(request, event.at)
      for (const option of request.options) {
        const c = costs[option.kind]
        if (c === undefined) count(`option ${option.kind}: not offered`)
        else if (canServe(request, option, event.at, { map, level: 8 }).slack < 9 * 60)
          count(`option ${option.kind}: offered under 9 h of slack (the slowest servable)`)
        else stat(`${option.kind}: c / typical`).add(c / request.referenceFeeCents)
        count(`option ${option.kind}: offered`)
      }
      if (!prices) {
        count(Object.keys(costs).length === 0 ? 'declined: no option offered' : 'declined: no value')
        continue
      }
      count('quoted')
      // Our win, where the saved week's answer settles it: under a price that won, or over one that lost.
      const saved = sent.get(request.id)
      const theirs = saved?.quote ? Math.min(...Object.values(saved.quote)) : undefined
      const ours = Math.min(...Object.values(prices))
      if (theirs !== undefined && saved?.outcome === 'won' && ours <= theirs)
        count('quoted: would win (under a price that won)')
      else if (theirs !== undefined && saved?.outcome === 'lost' && ours >= theirs)
        count('quoted: would lose (over a price that lost)')
      else count('quoted: answer unknown')
      if (saved?.quote) stat("our lowest quote / saved week's lowest quote").add(ours / (theirs ?? ours))
      count(`quoted options: ${Object.keys(prices).sort().join('+')}`)
      for (const option of request.options) {
        const price = prices[option.kind]
        if (price === undefined) continue
        stat(`${option.kind}: quote / list`).add(price / option.listPriceCents)
        const c = costs[option.kind]
        if (c === undefined) count('priced an option it does not offer')
        else if (price < c) count('priced under cost')
        else stat(`${option.kind}: margin over c / typical`).add((price - c) / request.referenceFeeCents)
      }
      // Faster options never under slower ones.
      const ladder = ['same_day', 'next_day', 'within_3_days'] as const
      const priced = ladder.map((kind) => prices[kind]).filter((p): p is number => p !== undefined)
      if (priced.some((p, i) => i > 0 && p > priced[i - 1]!)) count('faster option priced under a slower one')
    } else if (event.kind === 'order_won') {
      const order = { ...event.order, deliveredAt: [...event.order.deliveredAt] }
      orders.set(order.id, order)
      const request = requests.get(order.id)
      const option = request?.options.find((o) => o.kind === order.option)
      if (request && option)
        stat('won: estimated last pickup − real, hours').add(
          (requestFeeGig(request, option, 1, setup).lastPickupAt - order.lastPickupAt) / 60,
        )
      gigOf({ why: 'won', order, legs: order.legs.map((_, leg) => leg) }, 'won')
    } else if (event.kind === 'order_changed') {
      orders.set(event.order.id, { ...event.order, deliveredAt: [...event.order.deliveredAt] })
    } else if (event.kind === 'deadline_close') {
      const order = orders.get(event.orderId)
      urgent.add(event.orderId)
      const previous = gigsOf(event.orderId)
        .map((id) => posts.get(id)!)
        .at(-1)
      if (order && previous) {
        order.lastPickupAt = event.lastPickupAt
        const legs = previous.stops.filter((s) => s.orderId === order.id && s.kind === 'pickup').map((s) => s.leg)
        gigOf({ why: 'urgent', order, legs, previous }, 'urgent')
      }
    } else if (event.kind === 'visit_failed') {
      const order = orders.get(event.orderId)
      if (order) gigOf({ why: 'retry', order, legs: [event.leg], failed: event.reason }, 'retry')
    } else if (event.kind === 'gig_expired') {
      const previous = posts.get(event.gigId)
      const order = previous && orders.get(previous.stops[0]!.orderId)
      if (order && previous) {
        const legs = previous.stops.filter((s) => s.orderId === order.id && s.kind === 'pickup').map((s) => s.leg)
        gigOf({ why: 'repost', order, legs, previous }, 'repost')
      }
    } else if (event.kind === 'delivered') {
      const order = orders.get(event.orderId)
      if (order) order.deliveredAt[event.leg] = event.at
    }
    if (event.seq === half) {
      // A restart: a new strategy fed the log so far must hold the same state.
      const fresh = bidprice.build(setup, params) as unknown as Probe
      const toldNow = new Set<string>()
      for (const e of events) {
        if (e.seq > half) break
        const named2 = 'gigId' in e ? [e.gigId] : e.kind === 'order_cancelled' ? e.gigs.map((g) => g.gigId) : []
        for (const gig of untold)
          if (told.has(gig.id) && !toldNow.has(gig.id) && (gig.postedAt < e.at || named2.includes(gig.id))) {
            toldNow.add(gig.id)
            sendPost(fresh, posts.get(gig.id)!, gig)
          }
        observe(fresh, e)
      }
      const same =
        JSON.stringify(fresh.quotes) === JSON.stringify(strategy.quotes) &&
        JSON.stringify(fresh.fees) === JSON.stringify(strategy.fees)
      count(same ? 'restart at half week: same state' : 'restart at half week: DIFFERENT state')
    }
  }
  const same =
    JSON.stringify(restarted.quotes) === JSON.stringify(strategy.quotes) &&
    JSON.stringify(restarted.fees) === JSON.stringify(strategy.fees)
  if (!same) count('observe-only twin: DIFFERENT state')
  console.log(`${dir}: ${strategy.summary()}`)
}

for (const dir of weeks()) play(dir)
console.log()
for (const [name, n] of [...counts].sort()) console.log(`${name}: ${n}`)
console.log()
for (const [name, s] of [...stats].sort()) console.log(`${name}: ${s}`)
console.log()
console.log(`slowest call (ms): ${[...slowest].map(([call, ms]) => `${call} ${ms.toFixed(1)}`).join(', ')}`)
