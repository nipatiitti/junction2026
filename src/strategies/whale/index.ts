/** whale: a casino host. Find the few dealers who send most requests, earn their trust with safe on-time orders at
 * an easy price and generous driver fees, then charge them a price that climbs with their trust. Small dealers only
 * get a fat-margin quote. README.md next to this file has the idea and the params. */
import type { DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { canServe, pickOption } from '../../ops/index.ts'
import { type Books, type GigNeed, type GigPlan, type Prices, Strategy, type StrategyKind } from '../../strategy.ts'
import { starterGig } from '../starter/gig.ts'

export type WhaleParams = {
  /** A dealer is a whale once it sent this share of the requests so far. */
  whaleShare: number
  /** Requests seen before anyone is called a whale or a small dealer. */
  minRequests: number
  /** Whale price over list at trust 0. */
  whaleBase: number
  /** Whale price added per trust point (one on-time order). */
  whaleRise: number
  /** Extra convex part: added times (trust / cap)^2. */
  whaleCurve: number
  /** Trust count cap (the world's 25). */
  trustCap: number
  /** Small dealer price over list. */
  smallMult: number
  /** Small dealer price added per trust point. */
  smallRise: number
  /** Price over list before we know who is who. */
  unknownMult: number
  /** Driver fee multiplier on whale orders while the whale is still building trust. */
  whaleBuildFee: number
  /** Driver fee multiplier on whale orders once trust is full. */
  whaleFullFee: number
  /** Driver fee multiplier on other orders. */
  smallFee: number
  /** Extra slack (hours) a whale option needs while trust builds: only safe orders. */
  whaleSafeHours: number
  /** Extra price over list for same_day options. */
  sameDayExtra: number
}

const DEFAULTS: WhaleParams = {
  whaleShare: 0.07,
  minRequests: 25,
  whaleBase: 1.25,
  whaleRise: 0.018,
  whaleCurve: 0.15,
  trustCap: 25,
  smallMult: 1.55,
  smallRise: 0.01,
  unknownMult: 1.4,
  whaleBuildFee: 1.05,
  whaleFullFee: 0.95,
  smallFee: 0.9,
  whaleSafeHours: 3,
  sameDayExtra: 0.05,
}

class Whale extends Strategy<WhaleParams> {
  private counts = new Map<string, number>()
  private total = 0
  private seen = new Set<string>()
  /** Dealer -> on-time count, as the world keeps it (halved on a late order). */
  private trust = new Map<string, number>()
  /** Orders already scored for trust. */
  private scored = new Set<string>()
  private late = 0
  private onTime = 0

  observe(event: DeskEvent, books: Books): void {
    if (event.kind === 'price_request') {
      const r = event.request
      if (this.seen.has(r.id)) return
      this.seen.add(r.id)
      this.total++
      this.counts.set(r.dealerId, (this.counts.get(r.dealerId) ?? 0) + 1)
    } else if (event.kind === 'delivered') {
      const order = books.orders.get(event.orderId)
      if (!order || this.scored.has(order.id)) return
      const times = order.deliveredAt.map((t, i) => (i === event.leg ? event.at : t))
      if (times.some((t) => t === null)) return
      this.scored.add(order.id)
      const last = Math.max(...(times as number[]))
      const t = this.trust.get(order.dealerId) ?? 0
      if (last <= order.deadline) {
        this.onTime++
        this.trust.set(order.dealerId, Math.min(this.params.trustCap, t + 1))
      } else {
        this.late++
        this.trust.set(order.dealerId, Math.floor(t / 2))
      }
    }
  }

  private kind(dealer: string): 'whale' | 'small' | 'unknown' {
    if (this.total < this.params.minRequests) return 'unknown'
    const share = (this.counts.get(dealer) ?? 0) / this.total
    return share >= this.params.whaleShare ? 'whale' : 'small'
  }

  private trustOf(dealer: string): number {
    return this.trust.get(dealer) ?? 0
  }

  private mult(dealer: string): number {
    const p = this.params
    const t = this.trustOf(dealer)
    switch (this.kind(dealer)) {
      case 'whale': {
        const x = Math.min(1, t / p.trustCap)
        return p.whaleBase + p.whaleRise * t + p.whaleCurve * x * x
      }
      case 'small':
        return p.smallMult + p.smallRise * t
      default:
        return p.unknownMult + p.smallRise * t
    }
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const context = { map: this.setup.map, level: this.setup.level }
    let option = pickOption(request, books.now, context)
    if (!option) return null
    const whale = this.kind(request.dealerId) === 'whale'
    if (whale && this.trustOf(request.dealerId) < this.params.trustCap) {
      // Only safe orders while trust builds: the first option with extra slack, else decline.
      const need = this.params.whaleSafeHours * 60
      const safe = request.options.find((o) => {
        const v = canServe(request, o, books.now, context)
        return v.ok && v.slack >= 5 * 60 + need
      })
      if (!safe) return null
      option = safe
    }
    const extra = option.kind === 'same_day' ? this.params.sameDayExtra : 0
    return { [option.kind]: Math.round(option.listPriceCents * (this.mult(request.dealerId) + extra)) }
  }

  gig(need: GigNeed, books: Books): GigPlan {
    const plan = starterGig(need, books, this.setup.level)
    const dealer = need.order.dealerId
    let f = this.params.smallFee
    if (this.kind(dealer) === 'whale')
      f = this.trustOf(dealer) < this.params.trustCap ? this.params.whaleBuildFee : this.params.whaleFullFee
    return {
      ...plan,
      schedule: plan.schedule.map((s) => ({ ...s, feeCents: Math.max(1, Math.round(s.feeCents * f)) })),
    }
  }

  summary(): string {
    const whales = [...this.counts.keys()].filter((d) => this.kind(d) === 'whale')
    const t = whales.map((d) => `${d}:${this.trustOf(d)}`).join(' ')
    return `whales ${t}; trust-scored on time ${this.onTime}, late ${this.late}`
  }
}

export const whale: StrategyKind<WhaleParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Whale(setup, params),
}
