/** The baseline that a new in-week win model has to beat: how well `Demand` (strategy `lean`) predicts the dealers.
 *
 *     node ml/replay_demand.ts
 *
 * Each week is walked in event order as `lean` would have seen it had it sent that week's quotes: `dawn` on each
 * price request, the belief of each quoted option before its outcome, `learn` at the outcome (a win: the option
 * taken; a loss: every quoted option), and the trust offset from the week's deliveries.
 *
 * 1. Flip error on the probe weeks pr-1..pr-4: the belief's mu at arrival against log(flip).
 * 2. Log-loss of the chance to win against won/lost on 200 ordinary weeks.
 *
 * Offline; reads the data folders, writes only ml/baseline_demand.json. */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { Demand } from '../../src/strategies/lean/demand.ts'

const DATA = process.env.SPREAD_DATA ?? '../junction2026-data'
const OUT = `${DATA}/ml/baseline_demand.json`
const DAY = 1440
const TRUST = 0.7 // lean's params.trust
const DECLINE = 5 // a quote at or above this × list is a decline
const WEEKS = 200

type Option = { kind: string; listPriceCents: number }
type Request = { id: string; dealerId: string; arrivedAt: number; legs: any[]; options: Option[] }
type Belief = { mu: number; scale: number; variance: number }
/** One quoted option, as the model saw it before the answer. */
type Row = {
  week: string
  requestId: string
  kind: string
  at: number
  options: number // the options of the request that got a real quote
  multiple: number
  belief: Belief
  prior: Belief // a model that never learns: the priors plus the trust offset
  offset: number
  won: boolean | null // null: another option of the request was taken
}

const gz = (path: string) => gunzipSync(readFileSync(path)).toString('utf8')

/** Walks one week. `quotes` is the price sent per request and option; `seen` gets each belief at arrival. */
function replay(week: string, level: number, quotes: Map<string, Record<string, number>>): Row[] {
  const demand = new Demand(level)
  const fresh = new Demand(level)
  const requests = new Map<string, Request>()
  const delivered = new Map<string, string[]>()
  const late = new Set<string>()
  const open = new Map<string, Row[]>()
  const rows: Row[] = []
  const trust = (dealerId: string): number => {
    let count = 0
    for (const id of delivered.get(dealerId) ?? []) count = late.has(id) ? Math.floor(count / 2) : Math.min(25, count + 1)
    return TRUST * Math.log(1 + count / 100)
  }
  const outcome = (requestId: string, won: string | null) => {
    const request = requests.get(requestId)
    const prices = quotes.get(requestId)
    for (const row of open.get(requestId) ?? []) row.won = won === null ? false : row.kind === won ? true : null
    open.delete(requestId)
    if (!request || !prices) return
    const offset = trust(request.dealerId)
    for (const option of request.options) {
      const cents = prices[option.kind]
      if (cents === undefined || cents === null || (won && option.kind !== won)) continue
      demand.learn(demand.keys(request as any, option.kind as any), offset, cents / option.listPriceCents, won !== null)
    }
  }
  for (const line of gz(`${week}/events.jsonl.gz`).split('\n')) {
    if (!line) continue
    const event = JSON.parse(line)
    switch (event.kind) {
      case 'price_request': {
        const request: Request = event.request
        requests.set(request.id, request)
        demand.dawn(Math.floor(event.at / DAY))
        const prices = quotes.get(request.id) ?? {}
        const offset = trust(request.dealerId)
        const real = request.options.filter((o) => prices[o.kind] != null && prices[o.kind]! < DECLINE * o.listPriceCents)
        const made: Row[] = []
        for (const option of request.options) {
          const keys = demand.keys(request as any, option.kind as any)
          const cents = prices[option.kind]
          made.push({
            week,
            requestId: request.id,
            kind: option.kind,
            at: request.arrivedAt,
            options: real.length,
            multiple: cents == null ? Number.NaN : cents / option.listPriceCents,
            belief: demand.belief(keys, offset),
            prior: fresh.belief(keys, offset),
            offset,
            won: null,
          })
        }
        open.set(request.id, made)
        rows.push(...made)
        break
      }
      case 'order_won':
        outcome(event.order.id, event.order.option)
        break
      case 'order_lost':
        outcome(event.requestId, null)
        break
      case 'ledger': {
        const { kind, orderId } = event.line
        if (!orderId) break
        if (kind === 'late_refund' || kind === 'undelivered_penalty') late.add(orderId)
        const dealerId = requests.get(orderId)?.dealerId
        if (kind === 'revenue' && dealerId) delivered.set(dealerId, [...(delivered.get(dealerId) ?? []), orderId])
        break
      }
    }
  }
  for (const made of open.values()) for (const row of made) row.multiple = Number.NaN // never answered
  return rows
}

/** The quotes of a week, from its reveal (our last quote per request and option). */
function quotesOf(week: string): Map<string, Record<string, number>> {
  const reveal = JSON.parse(gz(`${week}/reveal.json.gz`))
  const quotes = new Map<string, Record<string, number>>()
  for (const item of reveal.requests ?? []) if (item.quote) quotes.set(item.request.id, item.quote)
  return quotes
}

const round = (x: number, digits = 4) => Number(x.toFixed(digits))
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b)
  return s.length === 0 ? Number.NaN : s.length % 2 ? s[(s.length - 1) / 2]! : (s[s.length / 2 - 1]! + s[s.length / 2]!) / 2
}
/** n, bias, RMSE and median absolute error of the errors `xs` (in log price). */
function errors(xs: number[]) {
  const n = xs.length
  if (n === 0) return { n: 0, bias: null, rmse: null, medAbs: null }
  return {
    n,
    bias: round(xs.reduce((a, b) => a + b, 0) / n),
    rmse: round(Math.sqrt(xs.reduce((a, b) => a + b * b, 0) / n)),
    medAbs: round(median(xs.map(Math.abs))),
  }
}

// ---------------------------------------------------------------------------------------------- 1. flip error

type Flip = { day: number; onTime: number; model: number; constant: number; week: string }
const flips: Flip[] = []
const probeCounts: Record<string, { probes: number; used: number; unmatched: number }> = {}
for (const seed of ['pr-1', 'pr-2', 'pr-3', 'pr-4']) {
  const week = `${DATA}/probe2/quote/L8/${seed}`
  const level = JSON.parse(readFileSync(`${week}/meta.json`, 'utf8')).level
  const rows = new Map(replay(week, level, quotesOf(week)).map((r) => [`${r.requestId}/${r.kind}`, r]))
  const count = { probes: 0, used: 0, unmatched: 0 }
  for (const line of readFileSync(`${week}/probes.jsonl`, 'utf8').split('\n')) {
    if (!line) continue
    const probe = JSON.parse(line)
    count.probes++
    const { flip, bracket } = probe
    if (!(flip > 0) || probe.ends || !bracket || flip < bracket[0] || flip > bracket[1]) continue
    const row = rows.get(`${probe.requestId}/${probe.option}`)
    if (!row) {
      count.unmatched++
      continue
    }
    count.used++
    flips.push({
      week: seed,
      day: Math.floor(probe.at / DAY),
      onTime: probe.dealer?.onTime ?? 0,
      model: row.belief.mu - Math.log(flip),
      constant: Math.log(1.4) + row.offset - Math.log(flip),
    })
  }
  probeCounts[seed] = count
}
const bucket = (onTime: number) => (onTime === 0 ? '0' : onTime < 5 ? '1-4' : onTime < 10 ? '5-9' : '10+')
const flipTable = (pick: (f: Flip) => boolean) => {
  const some = flips.filter(pick)
  return { model: errors(some.map((f) => f.model)), constant: errors(some.map((f) => f.constant)) }
}
const flipError = {
  probes: probeCounts,
  overall: flipTable(() => true),
  byWeek: Object.fromEntries(['pr-1', 'pr-2', 'pr-3', 'pr-4'].map((w) => [w, flipTable((f) => f.week === w)])),
  byDay: Object.fromEntries([0, 1, 2, 3, 4, 5, 6].map((d) => [d, flipTable((f) => f.day === d)]).filter(([, t]) => (t as any).model.n > 0)),
  byOnTime: Object.fromEntries(['0', '1-4', '5-9', '10+'].map((b) => [b, flipTable((f) => bucket(f.onTime) === b)])),
}

// ------------------------------------------------------------------------------------------------ 2. log-loss

const folders: string[] = []
for (const seed of readdirSync(`${DATA}/runs/L8`).sort())
  for (const world of readdirSync(`${DATA}/runs/L8/${seed}`).sort()) folders.push(`${DATA}/runs/L8/${seed}/${world}`)
folders.sort()
const step = Math.floor(folders.length / WEEKS)

type Scored = { p: number; prior: number; won: boolean }
const single: Scored[] = []
const multi: Scored[] = []
const policies: Record<string, number> = {}
const skipped: { folder: string; policy: string; why: string }[] = []
const sampled: string[] = []
for (let i = 0; i < WEEKS; i++) {
  // every step-th folder; one that cannot be used gives its place to the next folder along
  for (let j = i * step; j < Math.min(folders.length, (i + 1) * step); j++) {
    const week = folders[j]!
    let meta: any
    let rows: Row[]
    try {
      meta = JSON.parse(readFileSync(`${week}/meta.json`, 'utf8'))
      rows = replay(week, meta.level ?? 8, quotesOf(week))
    } catch (error) {
      skipped.push({ folder: week, policy: meta?.policy ?? '?', why: `unreadable: ${(error as Error).message}` })
      continue
    }
    const answered = rows.filter((r) => Number.isFinite(r.multiple))
    const real = answered.filter((r) => r.multiple < DECLINE)
    const requests = new Set(rows.map((r) => r.requestId)).size
    const quoted = new Set(real.map((r) => r.requestId)).size
    if (requests === 0 || quoted / requests < 0.1) {
      skipped.push({ folder: week, policy: meta.policy, why: `quotes ${quoted} of ${requests} requests` })
      continue
    }
    sampled.push(week)
    policies[meta.policy] = (policies[meta.policy] ?? 0) + 1
    for (const r of real) {
      if (r.won === null) continue // the dealer took another option
      const scored = { p: Demand.chance(r.belief, r.multiple), prior: Demand.chance(r.prior, r.multiple), won: r.won }
      ;(r.options === 1 ? single : multi).push(scored)
    }
    break
  }
}

function logLoss(rows: Scored[]) {
  const clip = (p: number) => Math.min(1 - 1e-6, Math.max(1e-6, p))
  const loss = (pick: (r: Scored) => number) =>
    round(-rows.reduce((a, r) => a + Math.log(r.won ? clip(pick(r)) : 1 - clip(pick(r))), 0) / rows.length)
  const share = rows.filter((r) => r.won).length / rows.length
  const calibration = Array.from({ length: 10 }, (_, b) => {
    const some = rows.filter((r) => Math.min(9, Math.floor(r.p * 10)) === b)
    return {
      bucket: `${(b / 10).toFixed(1)}-${((b + 1) / 10).toFixed(1)}`,
      n: some.length,
      predicted: some.length ? round(some.reduce((a, r) => a + r.p, 0) / some.length, 3) : null,
      won: some.length ? round(some.filter((r) => r.won).length / some.length, 3) : null,
    }
  })
  return {
    n: rows.length,
    wonShare: round(share, 3),
    logLoss: loss((r) => r.p),
    logLossNoLearning: loss((r) => r.prior),
    logLossBaseRate: round(-(share * Math.log(share) + (1 - share) * Math.log(1 - share))),
    calibration,
  }
}

const result = {
  flipError,
  logLoss: {
    folders: folders.length,
    step,
    weeks: sampled.length,
    policies: Object.fromEntries(Object.entries(policies).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))),
    skipped,
    single: logLoss(single),
    multi: logLoss(multi),
  },
  sampled,
}
writeFileSync(OUT, `${JSON.stringify(result, null, 2)}\n`)

// ---------------------------------------------------------------------------------------------------- printing

const cell = (x: number | null, width = 8) => (x === null ? '-' : String(x)).padStart(width)
const flipLine = (name: string, t: ReturnType<typeof flipTable>) =>
  console.log(
    `${name.padEnd(12)}${cell(t.model.n, 6)}${cell(t.model.bias)}${cell(t.model.rmse)}${cell(t.model.medAbs)}   |${cell(t.constant.bias)}${cell(t.constant.rmse)}${cell(t.constant.medAbs)}`,
  )
console.log('1. Flip error, mu - log(flip), probe weeks pr-1..pr-4', JSON.stringify(probeCounts))
console.log(`${''.padEnd(12)}${'n'.padStart(6)}${'bias'.padStart(8)}${'rmse'.padStart(8)}${'medAbs'.padStart(8)}   |${'bias'.padStart(8)}${'rmse'.padStart(8)}${'medAbs'.padStart(8)}   (Demand | log 1.40 + trust)`)
flipLine('overall', flipError.overall)
for (const [k, t] of Object.entries(flipError.byWeek)) flipLine(k, t)
for (const [k, t] of Object.entries(flipError.byDay)) flipLine(`day ${k}`, t as any)
for (const [k, t] of Object.entries(flipError.byOnTime)) flipLine(`onTime ${k}`, t)
console.log(`\n2. Log-loss on ${sampled.length} weeks (every ${step}th of ${folders.length} folders), ${skipped.length} skipped`)
for (const [name, t] of [['single', result.logLoss.single], ['multi', result.logLoss.multi]] as const) {
  console.log(`${name}: n ${t.n}, won ${t.wonShare}, log-loss ${t.logLoss} (no learning ${t.logLossNoLearning}, base rate ${t.logLossBaseRate})`)
  for (const c of t.calibration) console.log(`  ${c.bucket}${cell(c.n, 8)}${cell(c.predicted)}${cell(c.won)}`)
}
console.log('policies:', JSON.stringify(result.logLoss.policies))
console.log('skipped:', JSON.stringify(skipped.map((s) => `${s.policy}: ${s.why}`)))
console.log(`saved ${OUT}`)
