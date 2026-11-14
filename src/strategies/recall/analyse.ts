/** Why recall's brackets are out of order: loads every saved level-8 week of a seed as observations (request option,
 * price / list, the dealer's trust then, the share of that dealer's requests we won the day before, weekday, policy)
 * and scores normalisations of the price by the share of observations a single per-option threshold misclassifies.
 * Usage: node src/strategies/recall/analyse.ts <seed> [runs dir ...] */
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

type Req = { id: string; dealerId: string; arrivedAt: number; options: { kind: string; listPriceCents: number }[] }
type Reveal = {
  requests: { request: Req; quote: Record<string, number> | null; outcome: string; option: string | null }[]
}
type Ev = {
  at: number
  kind: string
  orderId?: string
  order?: { id: string; dealerId: string; deadline: number; legs: unknown[] }
}
export type Obs = {
  key: string
  ratio: number
  /** On-time completions minus halvings, as recall counts them (capped at 25), and uncapped. */
  trust: number
  trustRaw: number
  /** Share of this dealer's requests we won the day before (0 when it sent none). */
  prev: number
  /** Share of all requests we won the day before. */
  prevAll: number
  day: number
  policy: string
  week: string
  won: boolean
}

const here = dirname(fileURLToPath(import.meta.url))
const gz = (p: string) => gunzipSync(readFileSync(p)).toString('utf8')
const DAY = 1440

export function load(seed: string, dirs: string[]): Obs[] {
  const out: Obs[] = []
  const seen = new Set<string>()
  for (const root of dirs) {
    const base = join(root, 'L8', seed)
    if (!existsSync(base)) continue
    for (const world of readdirSync(base)) {
      const dir = join(base, world)
      if (seen.has(world) || !existsSync(join(dir, 'reveal.json.gz')) || !existsSync(join(dir, 'events.jsonl.gz')))
        continue
      seen.add(world)
      let policy = '?'
      try {
        policy = JSON.parse(readFileSync(join(dir, 'meta.json'), 'utf8')).policy ?? '?'
      } catch {}
      const changes: { at: number; dealer: string; late: boolean }[] = []
      const orders = new Map<string, { dealer: string; deadline: number; left: number }>()
      for (const line of gz(join(dir, 'events.jsonl.gz')).split('\n')) {
        if (!line) continue
        const e = JSON.parse(line) as Ev
        if (e.kind === 'order_won' && e.order)
          orders.set(e.order.id, { dealer: e.order.dealerId, deadline: e.order.deadline, left: e.order.legs.length })
        else if (e.kind === 'order_changed' && e.order) {
          const o = orders.get(e.order.id)
          if (o) o.deadline = e.order.deadline
        } else if (e.kind === 'delivered' && e.orderId) {
          const o = orders.get(e.orderId)
          if (o && --o.left === 0) changes.push({ at: e.at, dealer: o.dealer, late: e.at > o.deadline })
        }
      }
      const reveal = JSON.parse(gz(join(dir, 'reveal.json.gz'))) as Reveal
      const rows = [...reveal.requests].sort((a, b) => a.request.arrivedAt - b.request.arrivedAt)
      // Wins and requests per dealer per day.
      const perDay = new Map<string, [number, number]>()
      for (const { request, outcome } of rows) {
        const d = Math.floor(request.arrivedAt / DAY)
        for (const k of [`${request.dealerId}|${d}`, `*|${d}`]) {
          const c = perDay.get(k) ?? [0, 0]
          c[1]++
          if (outcome === 'won') c[0]++
          perDay.set(k, c)
        }
      }
      const share = (k: string) => {
        const c = perDay.get(k)
        return c && c[1] > 0 ? c[0] / c[1] : 0
      }
      const trust = new Map<string, number>()
      const raw = new Map<string, number>()
      let next = 0
      for (const { request, quote, outcome, option } of rows) {
        while (next < changes.length && changes[next].at <= request.arrivedAt) {
          const c = changes[next++]
          const t = trust.get(c.dealer) ?? 0
          trust.set(c.dealer, c.late ? t / 2 : Math.min(25, t + 1))
          const r = raw.get(c.dealer) ?? 0
          raw.set(c.dealer, c.late ? r / 2 : r + 1)
        }
        const day = Math.floor(request.arrivedAt / DAY)
        for (const o of request.options) {
          const cents = quote?.[o.kind]
          if (cents === undefined) continue
          const ratio = cents / o.listPriceCents
          if (ratio > 2.5) continue
          const won = outcome === 'won' && option === o.kind
          if (!won && outcome === 'won') continue
          out.push({
            key: `${request.id}/${o.kind}`,
            ratio,
            trust: trust.get(request.dealerId) ?? 0,
            trustRaw: raw.get(request.dealerId) ?? 0,
            prev: share(`${request.dealerId}|${day - 1}`),
            prevAll: share(`*|${day - 1}`),
            day,
            policy,
            week: world,
            won,
          })
        }
      }
    }
  }
  return out
}

/** Errors of the best single threshold per option (win iff x ≤ t), over options with both a win and a loss. */
export function misclassified(groups: Map<string, Obs[]>, norm: (o: Obs) => number): { err: number; n: number } {
  let err = 0
  let n = 0
  for (const obs of groups.values()) {
    if (!obs.some((o) => o.won) || !obs.some((o) => !o.won)) continue
    const xs = obs.map((o) => [norm(o), o.won ? 1 : 0] as const).sort((a, b) => a[0] - b[0] || b[1] - a[1])
    // Threshold after position i: errors = losses at or below + wins above.
    let lossesBelow = 0
    let winsAbove = xs.filter((x) => x[1] === 1).length
    let best = winsAbove
    for (const [, w] of xs) {
      if (w === 1) winsAbove--
      else lossesBelow++
      best = Math.min(best, lossesBelow + winsAbove)
    }
    err += best
    n += xs.length
  }
  return { err, n }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const seed = process.argv[2] ?? 'spread-1'
  const dirs =
    process.argv.length > 3
      ? process.argv.slice(3)
      : ['/home/nipatiitti/projects/hackathons/junction2026/data/scrape/runs', join(here, '../../../data/scrape/runs')]
  const obs = load(seed, dirs)
  const groups = new Map<string, Obs[]>()
  for (const o of obs) groups.set(o.key, [...(groups.get(o.key) ?? []), o])
  const pct = (f: (o: Obs) => number) => {
    const { err, n } = misclassified(groups, f)
    return `${((100 * err) / Math.max(1, n)).toFixed(2)}% of ${n}`
  }
  console.log(
    `${seed}: ${obs.length} observations, ${groups.size} options, ${new Set(obs.map((o) => o.week)).size} weeks`,
  )
  console.log(`raw ratio: ${pct((o) => o.ratio)}`)
  console.log(`recall (/(1 + min(25, trust)/100)): ${pct((o) => o.ratio / (1 + o.trust / 100))}`)
  console.log('trust per order a, cap c:')
  for (const a of [0, 0.5, 1, 1.5, 2, 3])
    console.log(
      `  a=${a}%: ` +
        [10, 25, 50, 1e9]
          .map((c) => `cap ${c > 1e6 ? 'none' : c} ${pct((o) => o.ratio / (1 + (a * Math.min(c, o.trustRaw)) / 100))}`)
          .join(', '),
    )
  console.log('undercut: ratio / (1 + trust/100) / (1 - u × dealer win share the day before):')
  for (const u of [-0.2, -0.1, -0.05, 0, 0.05, 0.1, 0.2, 0.3])
    console.log(`  u=${u}: ${pct((o) => o.ratio / (1 + o.trust / 100) / (1 - u * o.prev))}`)
  console.log('market: ratio / (1 + trust/100) / (1 - v × our win share of all requests the day before):')
  for (const v of [-0.2, -0.1, 0, 0.1, 0.2, 0.3])
    console.log(`  v=${v}: ${pct((o) => o.ratio / (1 + o.trust / 100) / (1 - v * o.prevAll))}`)
  // Per-day multiplicative shift: fit the median normalised ratio of wins per (day) against the option's threshold.
  console.log('misclassified by day and by policy (recall normalisation, per-option threshold):')
  const norm = (o: Obs) => o.ratio / (1 + o.trust / 100)
  const thr = new Map<string, number>()
  for (const [k, os] of groups) {
    const wins = os.filter((o) => o.won).map(norm)
    const losses = os.filter((o) => !o.won).map(norm)
    if (wins.length && losses.length) thr.set(k, (Math.max(...wins) + Math.min(...losses)) / 2)
  }
  const bucket = (label: (o: Obs) => string) => {
    const m = new Map<string, [number, number]>()
    for (const o of obs) {
      const t = thr.get(o.key)
      if (t === undefined) continue
      const bad = o.won ? norm(o) > t : norm(o) <= t
      const c = m.get(label(o)) ?? [0, 0]
      c[1]++
      if (bad) c[0]++
      m.set(label(o), c)
    }
    return [...m]
      .sort()
      .map(([k, [b, n]]) => `${k} ${((100 * b) / n).toFixed(1)}% (${n})`)
      .join(', ')
  }
  console.log(`  day: ${bucket((o) => `d${o.day}`)}`)
  console.log(`  policy: ${bucket((o) => o.policy)}`)
  console.log(`  dealer win share prev day: ${bucket((o) => `${Math.min(4, Math.floor(o.prev * 5)) * 20}%+`)}`)
  console.log(
    `  trust: ${bucket((o) => (o.trustRaw >= 25 ? '25+' : o.trustRaw >= 10 ? '10-24' : o.trustRaw >= 1 ? '1-9' : '0'))}`,
  )
}
