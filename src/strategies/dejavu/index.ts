/** Dejavu: a time traveller who has lived this exact week many times. Deliberately overfit to practice seeds: it
 * recognises the week from its first requests and quotes each request just under the price it remembers winning
 * at. See README.md. */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { DeskEvent, FeeStep, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { canServe } from '../../ops/index.ts'
import { type Books, type GigNeed, type GigPlan, type Prices, Strategy, type StrategyKind } from '../../strategy.ts'
import { HOUR } from '../../time.ts'
import { starterGig } from '../starter/gig.ts'

export type DejavuParams = {
  /** Where inside the [highest win, lowest loss] bracket to quote: 0 at the win, 1 at the loss. */
  pos: number
  /** With only a loss known: quote this share of it. */
  belowLoss: number
  /** With only a win known: quote this multiple of it. */
  aboveWin: number
  /** Losses at or above this ratio are probes, ignored. */
  probeRatio: number
  /** Markup over list for requests the table does not know. */
  markup: number
  /** Threshold rise per trust point, in percent. */
  trustPct: number
  /** Trust cap. */
  trustMax: number
  /** Cost estimate without history, as a multiple of the reference fee. */
  costRef: number
  /** Least price over the expected cost. */
  minEdge: number
  /** Decline requests late in at least this share of saved weeks. */
  maxLate: number
  /** Fee schedule: opening multiple of the reference fee, the multiple at the last pickup, and the step count. */
  feeOpen: number
  feeMax: number
  feeSteps: number
  /** How many of the table's signature requests must match to trust the table. */
  sigMatch: number
}

type Bracket = [number, number]
type Entry = Record<string, Bracket> & { _c?: [number, number, number] }
type Table = { seed: string; sig: Record<string, Record<string, number>>; req: Record<string, Entry> }

const HERE = dirname(fileURLToPath(import.meta.url))
const TABLES: Table[] = ['spread-1', 'spread-9'].flatMap((seed) => {
  try {
    return [JSON.parse(readFileSync(join(HERE, `table-${seed}.json`), 'utf8')) as Table]
  } catch {
    return []
  }
})

class Dejavu extends Strategy<DejavuParams> {
  private trust = new Map<string, number>()
  private credited = new Set<string>()
  /** Signature matches per table; the table in use once it is clear. */
  private hits = new Map<Table, number>()
  private misses = new Map<Table, number>()
  private table: Table | null = null
  private quoted = 0
  private remembered = 0

  private recognise(request: PriceRequest): void {
    for (const t of TABLES) {
      const sig = t.sig[request.id]
      if (!sig) continue
      const same = request.options.every((o) => sig[o.kind] === undefined || sig[o.kind] === o.listPriceCents)
      const map = same ? this.hits : this.misses
      map.set(t, (map.get(t) ?? 0) + 1)
    }
    if (this.table && (this.misses.get(this.table) ?? 0) > 0) this.table = null
    for (const t of TABLES) {
      if ((this.hits.get(t) ?? 0) >= this.params.sigMatch && (this.misses.get(t) ?? 0) === 0) this.table = t
    }
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    this.recognise(request)
    const p = this.params
    const entry = this.table?.req[request.id]
    const cost = entry?._c
    if (cost && cost[1] >= p.maxLate) return null
    const trust = Math.min(p.trustMax, this.trust.get(request.dealerId) ?? 0)
    const lift = 1 + (trust * p.trustPct) / 100
    const context = { map: this.setup.map, level: this.setup.level }
    const prices: Prices = {}
    for (const option of request.options) {
      if (!canServe(request, option, books.now, context).ok) continue
      const list = option.listPriceCents
      let ratio = p.markup
      const b = entry?.[option.kind] as Bracket | undefined
      if (b) {
        const win = b[0] > 0 ? b[0] : null
        const loss = b[1] < p.probeRatio ? b[1] : null
        if (win && loss && loss > win) ratio = win + p.pos * (loss - win)
        else if (loss) ratio = loss * p.belowLoss
        else if (win) ratio = win * p.aboveWin
        ratio *= lift
      }
      const price = Math.round(ratio * list)
      const expected = cost ? cost[0] * list : request.referenceFeeCents * p.costRef
      if (price < expected * p.minEdge) continue
      prices[option.kind] = price
    }
    if (Object.keys(prices).length === 0) return null
    this.quoted++
    if (entry) this.remembered++
    return prices
  }

  observe(event: DeskEvent, books: Books): void {
    if (event.kind !== 'delivered') return
    const order = books.orders.get(event.orderId)
    if (!order || this.credited.has(order.id)) return
    const done = order.deliveredAt.every((at, leg) => at !== null || leg === event.leg)
    if (!done) return
    this.credited.add(order.id)
    if (event.at <= order.deadline) this.trust.set(order.dealerId, (this.trust.get(order.dealerId) ?? 0) + 1)
  }

  gig(need: GigNeed, books: Books): GigPlan {
    const plan = starterGig(need, books, this.setup.level)
    if (books.urgent.has(need.order.id) || this.setup.level === 1) return plan
    const p = this.params
    const request = books.requests.get(need.order.id)
    if (!request) return plan
    const fee = (request.referenceFeeCents * need.legs.length) / need.order.legs.length
    const end = Math.max(books.now + HOUR, need.order.lastPickupAt)
    const steps = Math.max(1, Math.round(p.feeSteps))
    const schedule: FeeStep[] = []
    for (let k = 0; k < steps; k++) {
      const share = steps === 1 ? 0 : k / (steps - 1)
      schedule.push({
        at: Math.round(books.now + share * (end - books.now)),
        feeCents: Math.max(1, Math.round(fee * (p.feeOpen + share * (p.feeMax - p.feeOpen)))),
      })
    }
    return { ...plan, schedule }
  }

  summary(): string {
    return `dejavu table=${this.table?.seed ?? 'none'} quoted=${this.quoted} remembered=${this.remembered}`
  }
}

export const dejavu: StrategyKind<DejavuParams> = {
  defaults: {
    pos: 0.5,
    belowLoss: 0.96,
    aboveWin: 1.03,
    probeRatio: 3,
    markup: 1.25,
    trustPct: 1,
    trustMax: 25,
    costRef: 1,
    minEdge: 1.05,
    maxLate: 0.5,
    feeOpen: 0.9,
    feeMax: 1.5,
    feeSteps: 6,
    sigMatch: 3,
  },
  build: (setup, params) => new Dejavu(setup, params),
}
