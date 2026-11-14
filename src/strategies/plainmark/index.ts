/** plainmark: a market-stall trader's three numbers. One markup on the list price per option, raised by a fixed
 * percent for each on-time order the dealer already has from us, and one flat-then-rising driver fee as a multiple
 * of the typical fee. Options we cannot serve on time are not offered. No learning, no models. */
import type { DeskEvent, FeeStep, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { canServe } from '../../ops/index.ts'
import { type Books, type GigNeed, type GigPlan, type Prices, Strategy, type StrategyKind } from '../../strategy.ts'
import { HOUR } from '../../time.ts'
import { starterGig } from '../starter/gig.ts'

export type PlainmarkParams = {
  /** Quote over list price, per option. */
  markupSameDay: number
  markupNextDay: number
  markupWithin3Days: number
  /** Extra markup per on-time order the dealer has from us (dealers accept about 1% more each). */
  trustStep: number
  /** On-time orders that count, at most. */
  trustCap: number
  /** The opening fee as a multiple of the typical fee, held flat for `flatHours`. */
  feeOpen: number
  flatHours: number
  /** Added to the multiple each hour after the flat part, up to `feeMax`. */
  feeRise: number
  feeMax: number
  /** After the deadline warning: open at `urgentOpen`, add `urgentRise` each half hour, up to `urgentMax`. */
  urgentOpen: number
  urgentRise: number
  urgentMax: number
}

const MARKUP_KEY = {
  same_day: 'markupSameDay',
  next_day: 'markupNextDay',
  within_3_days: 'markupWithin3Days',
} as const

class Plainmark extends Strategy<PlainmarkParams> {
  /** Dealer -> on-time orders (halved on a late one, as the world does). */
  private trust = new Map<string, number>()
  /** Order -> legs delivered so far, and whether all were on time. */
  private delivered = new Map<string, { legs: Set<number>; late: boolean }>()
  private quoted = 0
  private declined = 0

  observe(event: DeskEvent, books: Books): void {
    if (event.kind !== 'delivered') return
    const order = books.orders.get(event.orderId)
    if (!order) return
    const state = this.delivered.get(order.id) ?? { legs: new Set<number>(), late: false }
    if (state.legs.has(event.leg)) return
    state.legs.add(event.leg)
    if (event.at > order.deadline) state.late = true
    this.delivered.set(order.id, state)
    if (state.legs.size < order.legs.length) return
    const count = this.trust.get(order.dealerId) ?? 0
    this.trust.set(order.dealerId, state.late ? Math.floor(count / 2) : count + 1)
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const p = this.params
    const context = { map: this.setup.map, level: this.setup.level }
    const trust = Math.min(this.trust.get(request.dealerId) ?? 0, p.trustCap)
    const lift = 1 + p.trustStep * trust
    const prices: Prices = {}
    let any = false
    for (const option of request.options) {
      if (!canServe(request, option, books.now, context).ok) continue
      prices[option.kind] = Math.round(option.listPriceCents * p[MARKUP_KEY[option.kind]] * lift)
      any = true
    }
    if (any) this.quoted++
    else this.declined++
    return any ? prices : null
  }

  gig(need: GigNeed, books: Books): GigPlan {
    const plan = starterGig(need, books, this.setup.level)
    const request = books.requests.get(need.order.id)!
    const cars = plan.stops.filter((stop) => stop.kind === 'pickup').length
    const typical = (request.referenceFeeCents * cars) / need.order.legs.length
    const urgent = books.urgent.has(need.order.id)
    return { ...plan, schedule: urgent ? this.steep(books.now, typical) : this.rising(books.now, typical) }
  }

  /** Flat at `feeOpen` for `flatHours`, then up by `feeRise` an hour to `feeMax`. */
  private rising(now: number, typical: number): FeeStep[] {
    const p = this.params
    const steps: FeeStep[] = [{ at: now, feeCents: fee(typical, p.feeOpen) }]
    for (let k = 1; k <= 24; k++) {
      const multiple = Math.min(p.feeMax, p.feeOpen + p.feeRise * k)
      steps.push({ at: now + (p.flatHours + k - 1) * HOUR, feeCents: fee(typical, multiple) })
      if (multiple >= p.feeMax) break
    }
    return steps
  }

  private steep(now: number, typical: number): FeeStep[] {
    const p = this.params
    const steps: FeeStep[] = []
    for (let k = 0; k < 24; k++) {
      const multiple = Math.min(p.urgentMax, p.urgentOpen + p.urgentRise * k)
      steps.push({ at: now + k * 30, feeCents: fee(typical, multiple) })
      if (multiple >= p.urgentMax) break
    }
    return steps
  }

  summary(): string {
    return `plainmark: quoted ${this.quoted}, declined ${this.declined}, dealers with trust ${this.trust.size}`
  }
}

const fee = (typical: number, multiple: number): number => Math.max(1, Math.round(typical * multiple))

export const plainmark: StrategyKind<PlainmarkParams> = {
  defaults: {
    markupSameDay: 1.42,
    markupNextDay: 1.45,
    markupWithin3Days: 1.48,
    trustStep: 0.01,
    trustCap: 25,
    feeOpen: 1.1,
    flatHours: 1,
    feeRise: 0.15,
    feeMax: 1.8,
    urgentOpen: 1.8,
    urgentRise: 0.25,
    urgentMax: 3,
  },
  build: (setup, params) => new Plainmark(setup, params),
}
