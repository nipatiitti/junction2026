/** Sweep the market clean (`sweep`): aim for a high win rate rather than the highest profit per quote. Phase 1, while
 * a dealer's trust count is under `sweepTrust`: the highest grid price whose modelled win chance is at least
 * `sweepWinEarly`, never under cost × (1 + `sweepMarginEarly`), on options with `sweepComfortHours` of slack. Phase 2:
 * bidprice's profit price capped at the highest price that wins at least `sweepWinLate`, never under cost × (1 +
 * `sweepMarginLate`). Costs use `sweepCostScale`. A load brake prices as plain bidprice while more than `sweepMaxOpen`
 * won orders have no driver. The counters only feed the summary. */
import type { Action, DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { bestQuote, OPTIONS, type Option, type QuoteDecision, trustOf, winProb } from '../../models/quote/index.ts'
import { canServe, HOUR } from '../../ops/index.ts'
import type { Books } from '../../strategy.ts'
import type { BidPrice } from './index.ts'

const DAY = 24 * 60

type Phase = 'early' | 'late' | 'floor' | 'brake' | 'normal'
type Sent = { day: number; overList: number; trust: number }

export class Sweep {
  readonly phases: Record<Phase, number> = { early: 0, late: 0, floor: 0, brake: 0, normal: 0 }
  /** The decision context of each request quoted, until the quote is sent. */
  private readonly pending = new Map<string, Sent>()
  private readonly sentQuotes = new Map<string, Sent>()
  private readonly days: { quotes: number; wins: number; overList: number; trust: number }[] = []
  private readonly topByDay: string[] = []
  private lastDay = 0

  decide(bp: BidPrice, request: PriceRequest, books: Books): QuoteDecision {
    const now = books.now
    const trust = trustOf(bp.quotes, request.dealerId, bp.quoteParams)
    const decision = this.choose(bp, request, books, trust)
    if (!decision.decline) {
      const ratios = request.options.flatMap((o) => {
        const price = decision.prices[o.kind]
        return price ? [price / o.listPriceCents] : []
      })
      const overList = ratios.length > 0 ? Math.min(...ratios) : 0
      this.pending.set(request.id, { day: Math.floor(now / DAY), overList, trust })
    }
    return decision
  }

  private choose(bp: BidPrice, request: PriceRequest, books: Books, trust: number): QuoteDecision {
    const now = books.now
    const p = bp.params
    if (openOrders(books) > p.sweepMaxOpen) {
      this.phases.brake++
      return bp.decide(request, now)
    }
    const costs = bp.costs(request, now, p.sweepCostScale)
    const q = bp.quoteParams
    const grid = (list: number) => {
      const out: number[] = []
      for (let x = list * q.gridFrom; x <= list * q.gridTo; x *= Math.exp(q.gridStep)) out.push(Math.round(x))
      return out
    }
    const win = (price: number, kind: Option) => winProb(price, kind, request, bp.quotes, q)
    /** The highest grid price that wins at least `target`, or null. */
    const capOf = (kind: Option, list: number, target: number) => {
      let best: number | null = null
      for (const price of grid(list)) if (win(price, kind) >= target) best = price
      return best
    }

    if (trust < p.sweepTrust) {
      const context = bp.context()
      let best: { kind: Option; price: number; value: number; w: number; floor: boolean } | null = null
      for (const option of request.options) {
        const cost = costs[option.kind]
        if (cost === undefined || !Number.isFinite(cost)) continue
        if (canServe(request, option, now, context).slack < p.sweepComfortHours * HOUR) continue
        const floorPrice = Math.round(cost * (1 + p.sweepMarginEarly))
        const cap = capOf(option.kind, option.listPriceCents, p.sweepWinEarly)
        const price = Math.max(cap ?? 0, floorPrice)
        const w = win(price, option.kind)
        if (w < p.sweepWinFloor) continue
        const value = w * (price - cost)
        if (!best || value > best.value) best = { kind: option.kind, price, value, w, floor: price === floorPrice }
      }
      if (best && best.value >= q.minValueCents) {
        this.phases[best.floor ? 'floor' : 'early']++
        return { prices: { [best.kind]: best.price }, valueCents: best.value, winProb: best.w, decline: false }
      }
      this.phases.normal++
      return bp.decide(request, now)
    }

    const normal = bestQuote(request, costs, bp.quotes, q, now)
    if (normal.decline) return normal
    const prices: Partial<Record<Option, number>> = {}
    for (const kind of OPTIONS) {
      const price = normal.prices[kind]
      const option = request.options.find((o) => o.kind === kind)
      const cost = costs[kind]
      if (price === undefined || !option || cost === undefined) continue
      const cap = capOf(kind, option.listPriceCents, p.sweepWinLate) ?? 0
      prices[kind] = Math.max(Math.min(price, cap), Math.round(cost * (1 + p.sweepMarginLate)))
    }
    // A faster option never cheaper than a slower one (OPTIONS runs fastest first).
    let floor = 0
    for (const kind of [...OPTIONS].reverse()) {
      const price = prices[kind]
      if (price === undefined) continue
      prices[kind] = Math.max(price, floor)
      floor = prices[kind] ?? floor
    }
    this.phases.late++
    return { ...normal, prices }
  }

  sent(action: Action): void {
    if (action.type !== 'quote') return
    const s = this.pending.get(action.requestId)
    if (!s) return
    this.pending.delete(action.requestId)
    this.sentQuotes.set(action.requestId, s)
    const d = this.dayOf(s.day)
    d.quotes++
    d.overList += s.overList
    d.trust += s.trust
  }

  observe(bp: BidPrice, event: DeskEvent): void {
    const day = Math.floor(event.at / DAY)
    while (this.lastDay < day) {
      const top = Object.entries(bp.quotes.trust)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([, n]) => n)
      this.topByDay[this.lastDay] = top.join('/')
      this.lastDay++
    }
    if (event.kind === 'order_won') {
      const s = this.sentQuotes.get(event.order.id)
      if (s) this.dayOf(s.day).wins++
    }
  }

  summary(): string {
    const days = this.days
      .map((d, i) =>
        d
          ? `d${i} ${d.quotes}q ${((100 * d.wins) / Math.max(1, d.quotes)).toFixed(0)}% x${(d.overList / Math.max(1, d.quotes)).toFixed(2)} t${(d.trust / Math.max(1, d.quotes)).toFixed(1)} top ${this.topByDay[i] ?? '-'}`
          : '',
      )
      .filter(Boolean)
      .join('; ')
    const ph = Object.entries(this.phases)
      .map(([k, v]) => `${k} ${v}`)
      .join(' ')
    return `sweep: ${ph}; ${days}`
  }

  private dayOf(day: number) {
    this.days[day] ??= { quotes: 0, wins: 0, overList: 0, trust: 0 }
    return this.days[day]
  }
}

/** Won orders with undelivered legs and no driver on any of their gigs. */
function openOrders(books: Books): number {
  let open = 0
  for (const order of books.orders.values()) {
    const gigs = books.gigsOf(order.id)
    if (gigs.length > 0 && !gigs.some((g) => books.booked.has(g))) open++
  }
  return open
}
