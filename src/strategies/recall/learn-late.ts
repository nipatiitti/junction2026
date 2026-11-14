/** late memory: scans every saved level-8 week of a seed and writes, for each request id and option we won, how often
 * it was delivered late or never, its mean refund/penalty, its mean margin (ledger sum: price minus fees minus refunds)
 * and the number of weeks, to late-<seed>.json. Prints how repeatable lateness is and what late orders share.
 * Usage: node src/strategies/recall/learn-late.ts <seed> [runs dir ...] */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

type Leg = { pickup: { placeId: string } }
type Order = { id: string; dealerId: string; option: string; deadline: number; legs: Leg[] }
type Ev = {
  at: number
  kind: string
  order?: Order
  orderId?: string
  line?: { kind: string; cents: number; orderId: string | null }
}

const here = dirname(fileURLToPath(import.meta.url))
const seed = process.argv[2] ?? 'spread-1'
const dirs =
  process.argv.length > 3
    ? process.argv.slice(3)
    : ['/home/nipatiitti/projects/hackathons/junction2026/data/scrape/runs', join(here, '../../../data/scrape/runs')]
const gz = (p: string) => gunzipSync(readFileSync(p)).toString('utf8')

type Stat = { weeks: number; late: number; refund: number; margin: number }
const stats: Record<string, Stat> = {}
const feat: Record<string, Record<string, [number, number]>> = {
  option: {},
  slackH: {},
  town: {},
  hour: {},
  dealer: {},
}
const tally = (f: string, v: string, late: boolean) => {
  const t = (feat[f][v] ??= [0, 0])
  t[0]++
  if (late) t[1]++
}
const seen = new Set<string>()
let weeks = 0
for (const root of dirs) {
  const base = join(root, 'L8', seed)
  if (!existsSync(base)) continue
  for (const world of readdirSync(base)) {
    const dir = join(base, world)
    if (seen.has(world) || !existsSync(join(dir, 'events.jsonl.gz'))) continue
    seen.add(world)
    weeks++
    const orders = new Map<string, { o: Order; wonAt: number; left: number; doneAt: number | null }>()
    const money = new Map<string, { margin: number; refund: number }>()
    for (const line of gz(join(dir, 'events.jsonl.gz')).split('\n')) {
      if (!line) continue
      const e = JSON.parse(line) as Ev
      if (e.kind === 'order_won' && e.order)
        orders.set(e.order.id, { o: e.order, wonAt: e.at, left: e.order.legs.length, doneAt: null })
      else if (e.kind === 'order_changed' && e.order) {
        const o = orders.get(e.order.id)
        if (o) o.o = { ...o.o, deadline: e.order.deadline }
      } else if (e.kind === 'order_cancelled' && e.orderId) orders.delete(e.orderId)
      else if (e.kind === 'delivered' && e.orderId) {
        const o = orders.get(e.orderId)
        if (o && --o.left === 0) o.doneAt = e.at
      } else if (e.kind === 'ledger' && e.line?.orderId) {
        const m = money.get(e.line.orderId) ?? { margin: 0, refund: 0 }
        m.margin += e.line.cents
        if (e.line.kind !== 'revenue' && e.line.kind !== 'driver_fee' && e.line.cents < 0) m.refund -= e.line.cents
        money.set(e.line.orderId, m)
      }
    }
    for (const [id, { o, wonAt, doneAt }] of orders) {
      const late = doneAt === null || doneAt > o.deadline
      const m = money.get(id) ?? { margin: 0, refund: 0 }
      const s = (stats[`${id}/${o.option}`] ??= { weeks: 0, late: 0, refund: 0, margin: 0 })
      s.weeks++
      if (late) s.late++
      s.refund += m.refund
      s.margin += m.margin
      tally('option', o.option, late)
      tally('slackH', String(Math.min(48, Math.floor((o.deadline - wonAt) / 60 / 6) * 6)), late)
      tally('town', o.legs[0]?.pickup.placeId ?? '?', late)
      tally('hour', String(Math.floor((wonAt % 1440) / 60)), late)
      tally('dealer', o.dealerId, late)
    }
  }
}
const r = (x: number) => Math.round(x)
const out = Object.fromEntries(
  Object.entries(stats).map(([k, s]) => [
    k,
    {
      weeks: s.weeks,
      lateShare: Math.round((s.late / s.weeks) * 1000) / 1000,
      refund: r(s.refund / s.weeks),
      margin: r(s.margin / s.weeks),
    },
  ]),
)
writeFileSync(join(here, `late-${seed}.json`), JSON.stringify({ seed, level: 8, weeks, requests: out }))

const all = Object.values(stats)
const lateTotal = all.reduce((a, s) => a + s.late, 0)
const wonTotal = all.reduce((a, s) => a + s.weeks, 0)
const chronic = all.filter((s) => s.weeks >= 3 && s.late / s.weeks >= 0.5)
const chronicLate = all.filter((s) => s.late / s.weeks >= 0.5).reduce((a, s) => a + s.late, 0)
const chronicLate3 = chronic.reduce((a, s) => a + s.late, 0)
const negative = all.filter((s) => s.weeks >= 3 && s.margin < 0)
console.log(
  `${seed}: ${weeks} weeks, ${wonTotal} won orders, ${lateTotal} late (${((100 * lateTotal) / wonTotal).toFixed(1)}%); ` +
    `${((100 * chronicLate) / lateTotal).toFixed(1)}% of late orders are on requests late in >=half their weeks ` +
    `(${((100 * chronicLate3) / lateTotal).toFixed(1)}% with >=3 weeks: ${chronic.length} requests, ` +
    `mean margin ${r(chronic.reduce((a, s) => a + s.margin / s.weeks, 0) / Math.max(1, chronic.length))}c); ` +
    `${negative.length} requests with mean margin < 0 over >=3 weeks`,
)
for (const [f, t] of Object.entries(feat)) {
  const rows = Object.entries(t)
    .filter(([, [n]]) => n >= 30)
    .map(([v, [n, l]]) => [v, n, l / n] as const)
    .sort((a, b) => b[2] - a[2])
  console.log(
    `  ${f}: ${rows
      .slice(0, 8)
      .map(([v, n, s]) => `${v} ${(100 * s).toFixed(1)}% (${n})`)
      .join(', ')}`,
  )
}
