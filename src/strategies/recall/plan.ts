/** recall's plan (prophet): for a remembered seed the whole week is known, so choose its wins before it starts.
 * Each remembered request is valued at its best option: the sellable price (the memory's bracket × the trust the
 * dealer will have by then under the plan) less the expected cost (reference fee × feeScale). Requests are kept by
 * margin, per pickup day and in total up to the capacity, plus a trust bonus: 1% of the price of each of that dealer's
 * later planned wins (up to 25). Writes plan-<seed>.json with the planned and declined ids.
 * Usage: node src/strategies/recall/plan.ts <seed> [feeScale] [dayCap] [totalCap] [minMarginCents] */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

type Req = {
  id: string
  dealerId: string
  arrivedAt: number
  referenceFeeCents: number
  legs: { pickup: { window: { from: number } } }[]
  options: { kind: string; listPriceCents: number }[]
}
type Memory = { sig: Record<string, string>; opts: Record<string, [number | null, number | null]> }

const here = dirname(fileURLToPath(import.meta.url))
const seed = process.argv[2] ?? 'spread-1'
const feeScale = Number(process.argv[3] ?? 1.15)
const dayCap = Number(process.argv[4] ?? 75)
const totalCap = Number(process.argv[5] ?? 430)
const minMarginCents = Number(process.argv[6] ?? 300)
const lossShade = 0.957
const trustStep = 0.01
const roots = [
  '/home/nipatiitti/projects/hackathons/junction2026/data/scrape/runs',
  join(here, '../../../data/scrape/runs'),
]

const memory = JSON.parse(readFileSync(join(here, `memory-${seed}.json`), 'utf8')) as Memory
let requests: Req[] = []
for (const root of roots) {
  const base = join(root, 'L8', seed)
  if (!existsSync(base) || requests.length) continue
  for (const world of readdirSync(base)) {
    const p = join(base, world, 'reveal.json.gz')
    if (!existsSync(p)) continue
    const reveal = JSON.parse(gunzipSync(readFileSync(p)).toString('utf8')) as { requests: { request: Req }[] }
    requests = reveal.requests.map((r) => r.request)
    break
  }
}
requests.sort((a, b) => a.arrivedAt - b.arrivedAt)

type Cand = { id: string; dealer: string; day: number; at: number; price: number; cost: number; margin: number }
const cands: Cand[] = []
for (const r of requests) {
  let best: Cand | null = null
  for (const o of r.options) {
    const [w, l] = memory.opts[`${r.id}/${o.kind}`] ?? [null, null]
    if (w === null && l === null) continue
    const ratio = w !== null && l !== null ? Math.min(w, l * lossShade) : (w ?? (l as number) * lossShade)
    const price = o.listPriceCents * ratio
    const cost = (r.referenceFeeCents ?? 0) * feeScale
    const pickup = Math.max(r.arrivedAt, ...r.legs.map((g) => g.pickup.window.from))
    const c = { id: r.id, dealer: r.dealerId, day: Math.floor(pickup / 1440), at: r.arrivedAt, price, cost, margin: 0 }
    c.margin = price - cost
    if (!best || c.margin > best.margin) best = c
  }
  if (best) cands.push(best)
}

/** Choose by value (margin + trust bonus), within the caps; then recompute the bonus from the chosen set. */
let bonus = new Map<string, number>()
let chosen = new Set<string>()
for (let iter = 0; iter < 4; iter++) {
  const value = (c: Cand) => c.margin * (1 + 0) + (bonus.get(c.id) ?? 0)
  const order = [...cands].filter((c) => value(c) >= minMarginCents).sort((a, b) => value(b) - value(a))
  const perDay = new Map<number, number>()
  chosen = new Set()
  for (const c of order) {
    if (chosen.size >= totalCap) break
    const n = perDay.get(c.day) ?? 0
    if (n >= dayCap) continue
    perDay.set(c.day, n + 1)
    chosen.add(c.id)
  }
  // Trust bonus: each early win raises the dealer's later planned wins by 1% (counted up to 25 wins).
  bonus = new Map()
  const byDealer = new Map<string, Cand[]>()
  for (const c of cands) if (chosen.has(c.id)) byDealer.set(c.dealer, [...(byDealer.get(c.dealer) ?? []), c])
  for (const c of cands) {
    const later = (byDealer.get(c.dealer) ?? []).filter((x) => x.at > c.at + 720)
    const before = (byDealer.get(c.dealer) ?? []).filter((x) => x.at < c.at).length
    if (before >= 25) continue
    bonus.set(
      c.id,
      later.reduce((s, x) => s + x.price * trustStep, 0),
    )
  }
}

/** Trust under the plan raises the prices: report the planned margin with each dealer's trust count. */
const count = new Map<string, number>()
let margin = 0
for (const c of cands) {
  if (!chosen.has(c.id)) continue
  const t = Math.min(25, count.get(c.dealer) ?? 0)
  margin += c.price * (1 + t / 100) - c.cost
  count.set(c.dealer, (count.get(c.dealer) ?? 0) + 1)
}
const planned = cands.filter((c) => chosen.has(c.id)).map((c) => c.id)
const declined = cands.filter((c) => !chosen.has(c.id)).map((c) => c.id)
writeFileSync(
  join(here, `plan-${seed}.json`),
  JSON.stringify({ seed, feeScale, dayCap, totalCap, minMarginCents, margin: Math.round(margin), planned, declined }),
)
console.log(
  `${seed}: ${requests.length} requests, ${cands.length} remembered, planned ${planned.length} ` +
    `(margin EUR ${(margin / 100).toFixed(0)}), declined ${declined.length}`,
)
