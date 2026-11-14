/** recall: bidprice plus a memory of past practice weeks of the same seed. bidprice prices each request as usual;
 * when the week is recognised as a remembered seed, each quoted option is moved by the bracket of the dealer's
 * hidden threshold seen in earlier weeks (`learn.ts`), scaled by the dealer's trust now. Overfit to practice seeds;
 * on an unknown week it is bidprice. README.md has the rules and the params. */
import { readdirSync, readFileSync } from 'node:fs'
import type { DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
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
  /** prophet: follow plan-<seed>.json (`plan.ts`), declining the remembered requests it leaves out. */
  plan: boolean
  /** From this minute of the day, a day whose planned requests so far won under planDriftShare follows recall. */
  planDriftMinute: number
  /** The share of the day's planned requests so far that must have been won to keep declining. */
  planDriftShare: number
  /** At least this many planned requests that day before the drift check applies. */
  planDriftMin: number
}

type Plan = { seed: string; margin: number; planned: string[]; declined: string[] }

type Memory = { seed: string; sig: Record<string, string>; opts: Record<string, [number | null, number | null]> }

const here = new URL('./', import.meta.url)
const tuned = JSON.parse(readFileSync(new URL('../bidprice/tuned-6b.json', import.meta.url), 'utf8'))

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
  plan: true,
  planDriftMinute: 720,
  planDriftShare: 0.5,
  planDriftMin: 8,
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
    if (params.plan)
      for (const m of this.memories) {
        const f = new URL(`plan-${m.seed}.json`, here)
        try {
          const p = JSON.parse(readFileSync(f, 'utf8')) as Plan
          this.plans.set(m.seed, { plan: p, planned: new Set(p.planned), declined: new Set(p.declined) })
        } catch {}
      }
  }

  readonly plans = new Map<string, { plan: Plan; planned: Set<string>; declined: Set<string> }>()
  /** Per day: planned requests seen so far, and their ids (to count wins). */
  readonly planDay = new Map<number, string[]>()
  readonly planTally = { declined: 0, loosened: 0, quoted: 0 }
  private loose = new Set<number>()

  /** prophet: true when the plan says decline this request. */
  private planDeclines(memory: Memory, request: PriceRequest, books: Books): boolean {
    const p = this.plans.get(memory.seed)
    if (!p) return false
    const day = Math.floor(books.now / 1440)
    if (p.planned.has(request.id)) {
      this.planDay.set(day, [...(this.planDay.get(day) ?? []), request.id])
      this.planTally.quoted++
      return false
    }
    if (!p.declined.has(request.id)) return false
    if (!this.loose.has(day) && books.now - day * 1440 >= this.rp.planDriftMinute) {
      const ids = this.planDay.get(day) ?? []
      const won = ids.filter((id) => books.orders.has(id)).length
      if (ids.length >= this.rp.planDriftMin && won < this.rp.planDriftShare * ids.length) this.loose.add(day)
    }
    if (this.loose.has(day)) {
      this.planTally.loosened++
      return false
    }
    this.planTally.declined++
    return true
  }

  /** The memory this week is, or null. */
  private recognised(): Memory | null {
    let best = -1
    for (let i = 0; i < this.memories.length; i++) if (best < 0 || this.hits[i] > this.hits[best]) best = i
    if (best < 0) return null
    const hits = this.hits[best]
    return hits >= this.rp.matchMin && hits >= this.rp.matchShare * this.seen ? this.memories[best] : null
  }

  override quote(request: PriceRequest, books: Books): Prices | null {
    const sig = sigOf(request)
    this.seen++
    this.memories.forEach((m, i) => {
      if (m.sig[request.id] === sig) this.hits[i]++
    })
    const base = super.quote(request, books)
    const memory = this.recognised()
    if (!memory || memory.sig[request.id] !== sig) return base
    if (this.rp.plan && this.planDeclines(memory, request, books)) return null
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
      `dropped ${dropped}, untouched ${untouched}, not in memory ${unknown}, rescued ${rescued}` +
      this.planSummary(m)
    )
  }

  private planSummary(m: Memory | null): string {
    const p = m && this.plans.get(m.seed)
    if (!this.rp.plan || !p) return '; plan: none'
    const won = p.plan.planned.filter((id) => this.wonIds.has(id)).length
    const { declined, loosened, quoted } = this.planTally
    return (
      `; plan: planned wins ${p.plan.planned.length}, planned margin EUR ${(p.plan.margin / 100).toFixed(0)}, ` +
      `won among planned ${won}/${quoted} quoted, declined by plan ${declined}, loosened ${loosened}`
    )
  }

  readonly wonIds = new Set<string>()
  override observe(event: DeskEvent): void {
    super.observe(event)
    if (event.kind === 'order_won') this.wonIds.add(event.order.id)
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
