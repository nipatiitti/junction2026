/** groundhog's memory: scans every saved level-8 week of a seed and writes, for each request option, the bracket of its
 * trust-free threshold (highest winning ratio, lowest losing ratio, each / (1 + trust / 100)) to memory-<seed>.json.
 * Usage: node src/strategies/groundhog/learn.ts <seed> [runs dir ...] */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

type Req = { id: string; dealerId: string; arrivedAt: number; options: { kind: string; listPriceCents: number }[] }
type Reveal = {
  requests: { request: Req; quote: Record<string, number> | null; outcome: string; option: string | null }[]
}
type Ev = { at: number; kind: string; order?: { id: string; dealerId: string; deadline: number; legs: unknown[] } }
type DeliveredEv = Ev & { orderId: string; leg: number }

const here = dirname(fileURLToPath(import.meta.url))
const seed = process.argv[2] ?? 'spread-1'
const dirs = process.argv.length > 3 ? process.argv.slice(3) : [join(here, '../../../data/scrape/runs')]
const gz = (p: string) => gunzipSync(readFileSync(p)).toString('utf8')

/** Signature of a request: dealer and list prices, to recognise the seed. */
export const sigOf = (r: Req) => `${r.dealerId}|${r.options.map((o) => o.listPriceCents).join(',')}`

const sig: Record<string, string> = {}
const bracket: Record<string, [number | null, number | null]> = {}
const seen = new Set<string>()
let weeks = 0
for (const root of dirs) {
  const base = join(root, 'L8', seed)
  if (!existsSync(base)) continue
  for (const world of readdirSync(base)) {
    const dir = join(base, world)
    if (seen.has(world) || !existsSync(join(dir, 'reveal.json.gz')) || !existsSync(join(dir, 'events.jsonl.gz')))
      continue
    seen.add(world)
    weeks++
    // Trust over time from the events: +1 per on-time order, halved on a late one, capped at 25.
    const changes: { at: number; dealer: string; late: boolean }[] = []
    const orders = new Map<string, { dealer: string; deadline: number; left: number }>()
    for (const line of gz(join(dir, 'events.jsonl.gz')).split('\n')) {
      if (!line) continue
      const e = JSON.parse(line) as DeliveredEv
      if (e.kind === 'order_won' && e.order)
        orders.set(e.order.id, { dealer: e.order.dealerId, deadline: e.order.deadline, left: e.order.legs.length })
      else if (e.kind === 'order_changed' && e.order) {
        const o = orders.get(e.order.id)
        if (o) o.deadline = e.order.deadline
      } else if (e.kind === 'delivered') {
        const o = orders.get(e.orderId)
        if (o && --o.left === 0) changes.push({ at: e.at, dealer: o.dealer, late: e.at > o.deadline })
      }
    }
    const reveal = JSON.parse(gz(join(dir, 'reveal.json.gz'))) as Reveal
    const rows = [...reveal.requests].sort((a, b) => a.request.arrivedAt - b.request.arrivedAt)
    const trust = new Map<string, number>()
    let next = 0
    for (const { request, quote, outcome, option } of rows) {
      while (next < changes.length && changes[next].at <= request.arrivedAt) {
        const c = changes[next++]
        const t = trust.get(c.dealer) ?? 0
        trust.set(c.dealer, c.late ? t / 2 : Math.min(25, t + 1))
      }
      sig[request.id] = sigOf(request)
      const k = 1 + (trust.get(request.dealerId) ?? 0) / 100
      for (const o of request.options) {
        const cents = quote?.[o.kind]
        if (cents === undefined) continue
        const ratio = cents / o.listPriceCents
        if (ratio > 2.5) continue
        const free = ratio / k
        const won = outcome === 'won' && option === o.kind
        const lost = outcome !== 'won'
        if (!won && !lost) continue
        const key = `${request.id}/${o.kind}`
        const b = (bracket[key] ??= [null, null])
        if (won) b[0] = Math.max(b[0] ?? 0, free)
        else b[1] = Math.min(b[1] ?? Number.POSITIVE_INFINITY, free)
      }
    }
  }
}
const r4 = (x: number | null) => (x === null ? null : Math.round(x * 1e4) / 1e4)
const opts = Object.fromEntries(Object.entries(bracket).map(([k, [w, l]]) => [k, [r4(w), r4(l)]]))
writeFileSync(join(here, `memory-${seed}.json`), JSON.stringify({ seed, level: 8, weeks, sig, opts }))
const both = Object.values(bracket).filter(([w, l]) => w !== null && l !== null) as [number, number][]
const ordered = both.filter(([w, l]) => w < l)
const width = ordered.reduce((s, [w, l]) => s + (l - w), 0) / Math.max(1, ordered.length)
console.log(
  `${seed}: ${weeks} weeks, ${Object.keys(bracket).length} options, ${both.length} with both sides ` +
    `(${ordered.length} ordered, mean width ${width.toFixed(4)}), ` +
    `${Object.values(bracket).filter(([w]) => w !== null).length} with a win, ` +
    `${Object.values(bracket).filter(([, l]) => l !== null).length} with a loss`,
)
