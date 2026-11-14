/** recall: bidprice plus a memory of past practice weeks of the same seed. bidprice prices each request as usual;
 * when the week is recognised as a remembered seed, each quoted option is moved by the bracket of the dealer's
 * hidden threshold seen in earlier weeks (`learn.ts`), scaled by the dealer's trust now. Overfit to practice seeds;
 * on an unknown week it is bidprice. README.md has the rules and the params. */
import { readdirSync, readFileSync } from 'node:fs'
import type { PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type Option, OPTIONS, trustOf } from '../../models/quote/index.ts'
import type { Books, Prices, Setup, Strategy, StrategyKind } from '../../strategy.ts'
import { BidPrice } from '../bidprice/index.ts'
import { type BidPriceParams, DEFAULTS as BIDPRICE } from '../bidprice/params.ts'

export type RecallParams = BidPriceParams & {
  /** Use the memory at all; false is bidprice. */
  memory: boolean
  /** A known win is quoted at win × (1 + trust/100) × this. */
  winShade: number
  /** Never above (or, with no win, just under) loss × (1 + trust/100) × this. */
  lossShade: number
  /** An out-of-order bracket (win ≥ loss) is quoted at the lower side × (1 + trust/100) × this. */
  outShade: number
  /** A lowered or rescued price must be at least bidprice's cost × (1 + this). */
  minMargin: number
  /** Quote a remembered win when bidprice declines the request. */
  rescue: boolean
  /** Requests that must match the memory (id, dealer, list prices) before it is used. */
  matchMin: number
  /** The share of requests so far that must match. */
  matchShare: number
  /** Late memory: decline options that went late in past weeks or lost money on average (late-<seed>.json). */
  lateMemory: boolean
  /** An option late in at least this share of the weeks we won it is declined. */
  lateShareMax: number
  /** ...when won in at least this many weeks (also the bar for the negative-margin rule). */
  lateMinWeeks: number
}

type LateMemory = { seed: string; requests: Record<string, { weeks: number; lateShare: number; margin: number }> }

type Memory = { seed: string; sig: Record<string, string>; opts: Record<string, [number | null, number | null]> }

const here = new URL('./', import.meta.url)
const tuned = JSON.parse(readFileSync(new URL('../bidprice/tuned-6b.json', import.meta.url), 'utf8'))
const champion = JSON.parse(readFileSync(new URL('./champion2.json', import.meta.url), 'utf8'))

export const DEFAULTS: RecallParams = {
  ...BIDPRICE,
  ...tuned,
  memory: true,
  winShade: 1,
  lossShade: 0.98,
  outShade: 0.95,
  minMargin: 0.12,
  rescue: true,
  matchMin: 3,
  matchShare: 0.8,
  lateMemory: true,
  lateShareMax: 0.5,
  lateMinWeeks: 3,
  ...champion,
}

const sigOf = (r: PriceRequest) => `${r.dealerId}|${r.options.map((o) => o.listPriceCents).join(',')}`

function readMemories(): Memory[] {
  return readdirSync(here)
    .filter((f) => /^memory-.*\.json$/.test(f))
    .map((f) => JSON.parse(readFileSync(new URL(f, here), 'utf8')) as Memory)
}

class Recall extends BidPrice {
  readonly rp: RecallParams
  readonly memories: Memory[]
  /** Requests seen, and how many each memory matched. */
  seen = 0
  readonly hits: number[]
  readonly memo = { raised: 0, lowered: 0, dropped: 0, untouched: 0, rescued: 0, unknown: 0 }

  constructor(setup: Setup, params: RecallParams) {
    super(setup, params)
    this.rp = params
    this.memories = params.memory && setup.level === 8 ? readMemories() : []
    this.hits = this.memories.map(() => 0)
  }

  /** The memory this week is, or null. */
  private recognised(): Memory | null {
    let best = -1
    for (let i = 0; i < this.memories.length; i++) if (best < 0 || this.hits[i] > this.hits[best]) best = i
    if (best < 0) return null
    const hits = this.hits[best]
    return hits >= this.rp.matchMin && hits >= this.rp.matchShare * this.seen ? this.memories[best] : null
  }

  readonly lateMemories = new Map<string, LateMemory>()
  readonly late = { declined: 0, dropped: 0 }

  private lateOf(seed: string): LateMemory | null {
    if (!this.lateMemories.has(seed)) {
      try {
        this.lateMemories.set(seed, JSON.parse(readFileSync(new URL(`late-${seed}.json`, here), 'utf8')))
      } catch {
        this.lateMemories.set(seed, { seed, requests: {} })
      }
    }
    return this.lateMemories.get(seed) ?? null
  }

  override quote(request: PriceRequest, books: Books): Prices | null {
    const prices = this.recallQuote(request, books)
    const memory = prices && this.rp.lateMemory ? this.recognised() : null
    if (!prices || !memory || memory.sig[request.id] !== sigOf(request)) return prices
    const late = this.lateOf(memory.seed)
    if (!late) return prices
    const { lateShareMax, lateMinWeeks } = this.rp
    const out: Partial<Record<Option, number>> = {}
    let dropped = 0
    for (const kind of OPTIONS) {
      const p = prices[kind]
      if (p === undefined) continue
      const r = late.requests[`${request.id}/${kind}`]
      if (r && r.weeks >= lateMinWeeks && (r.lateShare >= lateShareMax || r.margin < 0)) dropped++
      else out[kind] = p
    }
    if (dropped === 0) return prices
    if (Object.keys(out).length === 0) {
      this.late.declined++
      return null
    }
    this.late.dropped++
    return out as Prices
  }

  private recallQuote(request: PriceRequest, books: Books): Prices | null {
    const sig = sigOf(request)
    this.seen++
    this.memories.forEach((m, i) => {
      if (m.sig[request.id] === sig) this.hits[i]++
    })
    const base = super.quote(request, books)
    const memory = this.recognised()
    if (!memory || memory.sig[request.id] !== sig) return base
    const now = books.now
    const costs = this.costs(request, now)
    const k = 1 + trustOf(this.quotes, request.dealerId, this.quoteParams) / 100
    const { winShade, lossShade, outShade, minMargin } = this.rp
    const floor = (kind: Option) => (costs[kind] ?? Number.POSITIVE_INFINITY) * (1 + minMargin)
    const out: Partial<Record<Option, number>> = {}

    if (!base) {
      if (!this.rp.rescue) return null
      for (const kind of OPTIONS) {
        const option = request.options.find((o) => o.kind === kind)
        const [w, l] = memory.opts[`${request.id}/${kind}`] ?? [null, null]
        if (!option || w === null || costs[kind] === undefined) continue
        const ratio = l !== null && w >= l ? l * outShade : Math.min(w * winShade, l !== null ? l * lossShade : w)
        const target = Math.round(option.listPriceCents * k * ratio)
        if (target >= floor(kind)) out[kind] = target
      }
      if (Object.keys(out).length === 0) return null
      this.memo.rescued++
      return ordered(out)
    }

    for (const kind of OPTIONS) {
      const p = base[kind]
      if (p === undefined) continue
      const option = request.options.find((o) => o.kind === kind)
      const [w, l] = memory.opts[`${request.id}/${kind}`] ?? [null, null]
      if (!option || (w === null && l === null)) {
        out[kind] = p
        this.memo.unknown++
        continue
      }
      const list = option.listPriceCents * k
      if (w !== null && l !== null && w >= l) {
        // Thresholds moved between weeks: the lower side, shaded, when it still pays; else bidprice.
        const target = Math.round(list * l * outShade)
        this.tallyMemo(p, target, target >= floor(kind) || target > p ? target : p, out, kind)
        continue
      }
      const L = l !== null ? Math.round(list * l * lossShade) : null
      if (w !== null) {
        const target = Math.min(Math.round(list * w * winShade), L ?? Number.POSITIVE_INFINITY)
        if (target > p) this.tallyMemo(p, target, target, out, kind)
        else if (L !== null && p > L) this.tallyMemo(p, target, target >= floor(kind) ? target : null, out, kind)
        else this.tallyMemo(p, p, p, out, kind)
      } else if (L !== null && p > L) this.tallyMemo(p, L, L >= floor(kind) ? L : null, out, kind)
      else this.tallyMemo(p, p, p, out, kind)
    }
    if (Object.keys(out).length === 0) return null
    return ordered(out)
  }

  private tallyMemo(
    p: number,
    _target: number,
    price: number | null,
    out: Partial<Record<Option, number>>,
    kind: Option,
  ) {
    if (price === null) this.memo.dropped++
    else if (price > p) this.memo.raised++
    else if (price < p) this.memo.lowered++
    else this.memo.untouched++
    if (price !== null) out[kind] = price
  }

  override summary(): string {
    const m = this.recognised()
    const { raised, lowered, dropped, untouched, rescued, unknown } = this.memo
    return (
      `${super.summary()}; recall: seed ${m ? `${m.seed} recognised` : 'not recognised'} ` +
      `(${m ? this.hits[this.memories.indexOf(m)] : 0}/${this.seen} matched), raised ${raised}, lowered ${lowered}, ` +
      `dropped ${dropped}, untouched ${untouched}, not in memory ${unknown}, rescued ${rescued}; late memory: declined ${this.late.declined}, options dropped on ${this.late.dropped}`
    )
  }
}

/** bidprice's rule across options: a faster option is never cheaper than a slower one. */
function ordered(prices: Partial<Record<Option, number>>): Prices {
  let floor = 0
  for (const kind of [...OPTIONS].reverse()) {
    const p = prices[kind]
    if (p === undefined) continue
    if (p < floor) prices[kind] = floor
    floor = Math.max(floor, prices[kind] ?? 0)
  }
  return prices as Prices
}

export const recall: StrategyKind<RecallParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Recall(setup, params) as unknown as Strategy<RecallParams>,
}
