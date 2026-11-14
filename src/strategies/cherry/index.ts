/** cherry: a fruit picker who takes only the ripest. Each request gets an expected driver cost from its features
 * (private addresses, trade-in, premium, Friday, drivers living near pickup and delivery) and an expected flip price
 * from its option, delivery region and the dealer's trust. Each option is priced at the grid price that maximises
 * (price - cost) x P(win); requests whose best margin is thin are declined. Slower options are never priced under
 * the chosen one, so the dealer pays for speed. Fees open near the typical fee scaled by the cost score and rise
 * towards the pickup. */
import type { DeliveryOption, DeskEvent, FeeStep, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { dayOf, weekday } from '../../ops/calendar.ts'
import {
  type Context,
  canServe,
  FIRST_TRY,
  features,
  gigShape,
  HOUR,
  minutes,
  type Retry,
  readNote,
  retryAfter,
  withoutWindows,
} from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'

export type CherryParams = {
  /** Median flip over list by option, before region and trust. */
  flipSame: number
  flipNext: number
  flipThree: number
  /** Region factor on the flip: capital (the towns in `capital`) and elsewhere. */
  capitalFactor: number
  otherFactor: number
  capital: string
  /** Log-sd of the flip around its median. */
  flipSd: number
  /** Trust: flip rises by this fraction per on-time order, up to `trustCap` orders. */
  trustStep: number
  trustCap: number
  /** Expected fee paid over typical for plain work, and the feature multipliers. */
  costBase: number
  privatePickup: number
  privateDelivery: number
  tradeIn: number
  premium: number
  friday: number
  weekend: number
  /** Supply: cost x (median drivers near / drivers near)^supplyPow, clipped. */
  supplyPow: number
  supplyMin: number
  supplyMax: number
  nearMinutes: number
  /** Lateness risk: cost added as a share of typical fee when the slack is under `tightSlackH` hours. */
  tightRisk: number
  tightSlackH: number
  /** Decline unless expected profit >= minEv cents and margin >= minMargin x cost. */
  minEv: number
  minMargin: number
  /** Price grid over list. */
  gridLo: number
  gridHi: number
  /** Slower options priced at least this times the chosen option's price. */
  ladderFloor: number
  /** Fees over typical, times the cost score: open, top before the pickup, and the urgent top. */
  feeOpen: number
  feeTop: number
  feeUrgent: number
  feeRepost: number
  feeSteps: number
  feeCurve: number
  feeHorizonH: number
  /** Load: cost += ref x loadPenalty x (open orders / loadTarget). */
  loadPenalty: number
  loadTarget: number
  /** same_day only with this many hours of slack. */
  sameSlackH: number
}

const DEFAULTS: CherryParams = {
  flipSame: 1.38,
  flipNext: 1.27,
  flipThree: 1.21,
  capitalFactor: 0.9,
  otherFactor: 1.07,
  capital: 'Helsinki,Espoo,Vantaa,Hyvinkää',
  flipSd: 0.17,
  trustStep: 0.01,
  trustCap: 25,
  costBase: 1.12,
  privatePickup: 1.1,
  privateDelivery: 1.07,
  tradeIn: 1.15,
  premium: 1.15,
  friday: 1.12,
  weekend: 1.03,
  supplyPow: 0.2,
  supplyMin: 0.85,
  supplyMax: 1.35,
  nearMinutes: 30,
  tightRisk: 0.1,
  tightSlackH: 8,
  minEv: 700,
  minMargin: 0.15,
  gridLo: 0.95,
  gridHi: 1.9,
  ladderFloor: 1.0,
  feeOpen: 1.0,
  feeTop: 1.65,
  feeUrgent: 2.3,
  feeRepost: 1.15,
  feeSteps: 8,
  feeCurve: 1.5,
  feeHorizonH: 12,
  loadPenalty: 0.35,
  loadTarget: 100,
  sameSlackH: 7,
}

/** Standard normal CDF. */
function phi(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x))
  const d = 0.3989423 * Math.exp((-x * x) / 2)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
  return x > 0 ? 1 - p : p
}

class Cherry extends Strategy<CherryParams> {
  private near = new Map<string, number>()
  private medianNear = 1
  private capitalIds = new Set<string>()
  private trust = new Map<string, number>()
  private retries = new Map<string, Retry>()
  private stats = { quoted: 0, declined: 0, same: 0 }
  private context: Context

  constructor(setup: Setup, params: CherryParams) {
    super(setup, params)
    this.context = { map: setup.map, level: setup.level }
    const names = new Set(
      String(params.capital)
        .split(',')
        .map((s) => s.trim().toLowerCase()),
    )
    for (const place of setup.map.places) {
      if (names.has(place.name.toLowerCase())) this.capitalIds.add(place.id)
      let n = 0
      for (const d of setup.roster) if (minutes(setup.map, d.homePlaceId, place.id) <= params.nearMinutes) n++
      this.near.set(place.id, n)
    }
    const counts = [...this.near.values()].sort((a, b) => a - b)
    this.medianNear = Math.max(1, counts[Math.floor(counts.length / 2)] ?? 1)
  }

  observe(event: DeskEvent, books: Books): void {
    if (event.kind !== 'delivered') return
    const order = books.orders.get(event.orderId)
    if (!order) return
    const others = order.deliveredAt.filter((at, leg) => leg !== event.leg && at == null).length
    if (others > 0) return
    const t = this.trust.get(order.dealerId) ?? 0
    this.trust.set(order.dealerId, event.at <= order.deadline ? t + 1 : t / 2)
  }

  /** The cost score: expected fee paid over the typical fee. */
  private costScore(work: Parameters<typeof features>[0], option?: DeliveryOption): number {
    const p = this.params
    const f = features(work, this.setup.map, option)
    let s = p.costBase
    if (f.privatePickup) s *= p.privatePickup
    if (f.privateDelivery) s *= p.privateDelivery
    if (f.tradeIn) s *= p.tradeIn
    if (f.premium) s *= p.premium
    if (f.weekendDelivery) s *= p.weekend
    const first = work.legs[0]
    if (first) {
      const nearP = this.near.get(first.pickup.placeId) ?? 0
      const nearD = this.near.get(first.delivery.placeId) ?? 0
      const supply = (Math.max(1, nearP) + 2 * Math.max(1, nearD)) / 3
      const factor = (this.medianNear / supply) ** p.supplyPow
      s *= Math.min(p.supplyMax, Math.max(p.supplyMin, factor))
    }
    return s
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const p = this.params
    const ref = request.referenceFeeCents
    const delivery = request.legs[0]?.delivery.placeId ?? ''
    const region = this.capitalIds.has(delivery) ? p.capitalFactor : p.otherFactor
    const trust = 1 + p.trustStep * Math.min(p.trustCap, this.trust.get(request.dealerId) ?? 0)
    const fri = weekday(dayOf(books.now)) === 4 ? p.friday : 1
    let open = 0
    for (const o of books.orders.values()) if (o.deliveredAt.some((at) => at == null)) open++
    const load = p.loadPenalty * ref * (open / p.loadTarget)
    let best: { option: DeliveryOption; price: number; ev: number } | null = null
    const served: DeliveryOption[] = []
    for (const option of request.options) {
      const verdict = canServe(request, option, books.now, this.context)
      if (!verdict.ok) continue
      if (option.kind === 'same_day' && verdict.slack < p.sameSlackH * HOUR) continue
      served.push(option)
      const base = option.kind === 'same_day' ? p.flipSame : option.kind === 'next_day' ? p.flipNext : p.flipThree
      const median = base * region * trust * option.listPriceCents
      let cost = ref * this.costScore(request, option) * fri + load
      if (verdict.slack < p.tightSlackH * HOUR) cost += p.tightRisk * ref
      let top: { price: number; ev: number } | null = null
      for (let m = p.gridLo; m <= p.gridHi + 1e-9; m += 0.01) {
        const price = Math.round(option.listPriceCents * m)
        if (price - cost < p.minMargin * cost) continue
        const win = 1 - phi(Math.log(price / median) / p.flipSd)
        const ev = (price - cost) * win
        if (!top || ev > top.ev) top = { price, ev }
      }
      if (top && top.ev >= p.minEv && (!best || top.ev > best.ev)) best = { option, ...top }
    }
    if (!best) {
      this.stats.declined++
      return null
    }
    this.stats.quoted++
    if (best.option.kind === 'same_day') this.stats.same++
    const prices: Prices = { [best.option.kind]: best.price }
    const chosen = best.option
    for (const option of served) {
      if (option.deadline <= chosen.deadline) continue
      prices[option.kind] = Math.max(Math.round(best.price * p.ladderFloor), option.listPriceCents)
    }
    return prices
  }

  gig(need: GigNeed, books: Books): GigPlan | GigPlan[] {
    const p = this.params
    const { order, previous } = need
    const request = books.requests.get(order.id)
    const ref = request?.referenceFeeCents ?? 10000
    const share = (ref * need.legs.length) / Math.max(1, order.legs.length)
    const score = this.costScore(order) / p.costBase
    const now = books.now
    if (previous) {
      const stops = need.why === 'repost' ? withoutWindows(previous.stops, Infinity) : previous.stops
      const last = previous.schedule.at(-1)?.feeCents ?? share
      const urgent = need.why === 'urgent' || books.urgent.has(order.id)
      const open = Math.max(last, share * score * (urgent ? p.feeTop : p.feeRepost))
      const top = Math.max(open, share * score * (urgent ? p.feeUrgent : p.feeTop))
      return { stops, audience: previous.audience, schedule: this.rising(now, open, top, urgent ? 2 * HOUR : 4 * HOUR) }
    }
    const facts = request ? readNote(request.note, request.arrivedAt) : readNote(null, now)
    let retry = FIRST_TRY
    for (const leg of need.legs) {
      const key = `${order.id}:${leg}`
      let r = this.retries.get(key) ?? FIRST_TRY
      if (need.failed) r = retryAfter(need.failed, order, request, leg, now, r)
      this.retries.set(key, r)
      retry = r
    }
    const shapes = gigShape(order, need.legs, facts, retry, now, this.context)
    const pickupAt = Math.min(...need.legs.map((leg) => order.legs[leg]?.pickup.window.from ?? now))
    const horizon = Math.min(p.feeHorizonH * HOUR, Math.max(2 * HOUR, pickupAt - now))
    const fri = weekday(dayOf(now)) === 4 ? p.friday : 1
    const retryBump = need.failed ? p.feeRepost : 1
    return shapes.map((shape) => {
      const cars = shape.stops.filter((s) => s.kind === 'pickup').length
      const fee = (ref * cars) / Math.max(1, order.legs.length)
      const open = fee * score * p.feeOpen * fri * retryBump
      const top = Math.max(open, fee * score * p.feeTop * fri)
      return { ...shape, schedule: this.rising(now, open, top, horizon) }
    })
  }

  private rising(now: number, open: number, top: number, horizon: number): FeeStep[] {
    const n = Math.max(1, Math.min(48, Math.round(this.params.feeSteps)))
    const steps: FeeStep[] = []
    let prev = 0
    for (let k = 0; k < n; k++) {
      const x = n === 1 ? 0 : k / (n - 1)
      const fee = Math.max(prev, Math.max(1, Math.round(open + (top - open) * x ** this.params.feeCurve)))
      steps.push({ at: Math.round(now + x * horizon), feeCents: fee })
      prev = fee
    }
    return steps
  }

  summary(): string {
    const { quoted, declined, same } = this.stats
    return `cherry: quoted ${quoted} (same_day ${same}), declined ${declined}`
  }
}

export const cherry: StrategyKind<CherryParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Cherry(setup, params),
}
