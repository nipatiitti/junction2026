/** recall's fee memory: scans every saved level-8 week of a seed and writes, for each won order's gig (request id and
 * its legs), the fee ratios over the typical fee at which drivers booked it, to fees-<seed>.json:
 * `[lowest ratio booked and delivered on time, median booked ratio, weeks seen, highest ratio that stayed unbooked
 * for more than `STALE` minutes or null]`. Prints how repeatable the booked ratio of a gig is across weeks.
 * Usage: node src/strategies/recall/learn-fees.ts <seed> [runs dir ...] */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

type Step = { at: number; feeCents: number }
type Gig = { id: string; stops: { orderId: string; leg: number; kind: string }[]; schedule: Step[]; postedAt: number }
type Order = { id: string; deadline: number; legs: unknown[] }
type Ev = { at: number; kind: string; gigId?: string; feeCents?: number; orderId?: string; request?: Req }
type Req = { id: string; referenceFeeCents: number; legs: unknown[] }

/** A fee shown this long (minutes) without a booking is a known failure. */
const STALE = 180
const here = dirname(fileURLToPath(import.meta.url))
const seed = process.argv[2] ?? 'spread-1'
const dirs =
  process.argv.length > 3
    ? process.argv.slice(3)
    : ['/home/nipatiitti/projects/hackathons/junction2026/data/scrape/runs', join(here, '../../../data/scrape/runs')]
const gz = (p: string) => gunzipSync(readFileSync(p)).toString('utf8')
const feeAt = (s: Step[], at: number) => s.reduce((f, x) => (x.at <= at ? x.feeCents : f), s[0]?.feeCents ?? 0)

type Seen = { booked: { ratio: number; onTime: boolean; week: number }[]; stale: number | null; weeks: Set<number> }
const memo = new Map<string, Seen>()
const seen = new Set<string>()
let weeks = 0
for (const root of dirs) {
  const base = join(root, 'L8', seed)
  if (!existsSync(base)) continue
  for (const world of readdirSync(base)) {
    const dir = join(base, world)
    if (seen.has(world) || !existsSync(join(dir, 'snapshot.json.gz')) || !existsSync(join(dir, 'events.jsonl.gz')))
      continue
    seen.add(world)
    const week = weeks++
    const snap = JSON.parse(gz(join(dir, 'snapshot.json.gz'))) as { gigs: Gig[]; orders: Order[] }
    const orders = new Map(snap.orders.map((o) => [o.id, o]))
    const reqs = new Map<string, Req>()
    const lastDelivery = new Map<string, number>()
    const bookings: { gigId: string; at: number; fee: number }[] = []
    for (const line of gz(join(dir, 'events.jsonl.gz')).split('\n')) {
      if (!line) continue
      const e = JSON.parse(line) as Ev
      if (e.kind === 'price_request' && e.request) reqs.set(e.request.id, e.request)
      else if (e.kind === 'gig_booked' && e.gigId) bookings.push({ gigId: e.gigId, at: e.at, fee: e.feeCents ?? 0 })
      else if (e.kind === 'delivered' && e.orderId)
        lastDelivery.set(e.orderId, Math.max(lastDelivery.get(e.orderId) ?? 0, e.at))
    }
    const gigs = new Map(snap.gigs.map((g) => [g.id, g]))
    const typical = (g: Gig) => {
      const orderId = g.stops[0]?.orderId
      const r = reqs.get(orderId)
      if (!r || g.stops.some((s) => s.orderId !== orderId)) return null
      const legs = new Set(g.stops.map((s) => s.leg))
      return {
        key: `${orderId}/${[...legs].sort().join(',')}`,
        cents: (r.referenceFeeCents * legs.size) / r.legs.length,
      }
    }
    const firstBook = new Map<string, number>()
    for (const b of bookings) {
      const g = gigs.get(b.gigId)
      const t = g && typical(g)
      if (!g || !t) continue
      if (!firstBook.has(g.id)) firstBook.set(g.id, b.at)
      const order = orders.get(g.stops[0].orderId)
      const done = lastDelivery.get(g.stops[0].orderId)
      const onTime = !!order && done !== undefined && done <= order.deadline
      const m = memo.get(t.key) ?? { booked: [], stale: null, weeks: new Set() }
      memo.set(t.key, m)
      m.weeks.add(week)
      m.booked.push({ ratio: b.fee / t.cents, onTime, week })
    }
    for (const g of gigs.values()) {
      const t = typical(g)
      if (!t) continue
      const end = firstBook.get(g.id) ?? Number.POSITIVE_INFINITY
      const m = memo.get(t.key) ?? { booked: [], stale: null, weeks: new Set() }
      memo.set(t.key, m)
      m.weeks.add(week)
      // The highest fee in the schedule that was shown at least STALE minutes before the first booking.
      let stale: number | null = null
      for (const s of g.schedule)
        if (s.at >= g.postedAt - 1 && s.at + STALE <= end && s.at + STALE <= g.postedAt + 7 * 1440)
          stale = Math.max(stale ?? 0, s.feeCents / t.cents)
      if (stale !== null) m.stale = Math.max(m.stale ?? 0, stale)
    }
  }
}

const r3 = (x: number) => Math.round(x * 1e3) / 1e3
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b)
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2
}
const out: Record<string, [number | null, number, number, number | null]> = {}
for (const [key, m] of memo) {
  if (m.booked.length === 0) continue
  const good = m.booked.filter((b) => b.onTime).map((b) => b.ratio)
  out[key] = [
    good.length ? r3(Math.min(...good)) : null,
    r3(median(m.booked.map((b) => b.ratio))),
    m.weeks.size,
    m.stale === null ? null : r3(m.stale),
  ]
}
writeFileSync(join(here, `fees-${seed}.json`), JSON.stringify({ seed, level: 8, weeks, gigs: out }))

// Repeatability: the spread (sd) of a gig's per-week booked ratio across weeks, against the spread across gigs.
const sd = (xs: number[]) => {
  const mu = xs.reduce((s, x) => s + x, 0) / xs.length
  return Math.sqrt(xs.reduce((s, x) => s + (x - mu) ** 2, 0) / Math.max(1, xs.length - 1))
}
const within: number[] = []
const means: number[] = []
for (const m of memo.values()) {
  const perWeek = new Map<number, number>()
  for (const b of m.booked) if (!perWeek.has(b.week)) perWeek.set(b.week, b.ratio)
  const xs = [...perWeek.values()]
  if (xs.length >= 3) {
    within.push(sd(xs))
    means.push(xs.reduce((s, x) => s + x, 0) / xs.length)
  }
}
const all = [...memo.values()].flatMap((m) => m.booked.map((b) => b.ratio))
const lows = Object.values(out)
  .map((v) => v[0])
  .filter((x): x is number => x !== null)
console.log(
  `${seed}: ${weeks} weeks, ${Object.keys(out).length} gigs booked; first-booking ratio: overall sd ${sd(all).toFixed(3)}, ` +
    `within-gig sd (median over ${within.length} gigs seen 3+ weeks) ${median(within).toFixed(3)}, ` +
    `across-gig sd of gig means ${sd(means).toFixed(3)}; median ratio ${median(all).toFixed(3)}, ` +
    `median lowest on-time ratio ${median(lows).toFixed(3)}`,
)
