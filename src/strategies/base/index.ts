/** The shared base of a priced strategy: `PricedStrategy` does everything but the price. It admits only the options
 * it can serve on time, brakes quoting when drivers fall behind or the late share rises, posts every gig with
 * bidprice's ramp, reprices dropped, stale and urgent gigs, and keeps trackers (trust, dealer share, wins and losses,
 * expected cost, drivers near) for the subclass. All state is rebuilt from `observe` and `sent`. src/README.md,
 * "Write a strategy on the base", is the guide. */
import type {
  Action,
  ActionResult,
  DeliveryOption,
  DeskEvent,
  FeeStep,
  Order,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  type FeeGig,
  type FeeParams,
  type FeeState,
  featuresOf,
  fewDriversNear,
  learn,
  newFeeState,
  planFees,
} from '../../models/fees/index.ts'
import { feeAt } from '../../models/fees/plan.ts'
import { driversNear } from '../../models/quote/index.ts'
import { type Context, canServe, DAY, driveMinutes, type GigShape, gigShape, HOUR } from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Params,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import { climb, higher, orderFeeGig, ramp, urgentRamp } from '../bidprice/fees.ts'
import { legsOf, WeekLog } from '../bidprice/log.ts'
import { DEFAULTS as BIDPRICE, feeParamsOf } from '../bidprice/params.ts'

export type OptionKind = DeliveryOption['kind']

export const BASE_DEFAULTS = {
  /** Offer an option only with this many hours of slack (more as the late share rises); with none that comfortable,
   * only the slowest option we can serve. */
  comfortHours: 9,
  /** Capacity brake: open gigs no driver holds, plus `pendingWeight` × quotes waiting for an answer, per pickup day. */
  maxOpenPerDay: 18,
  pendingWeight: 0.4,
  /** Late brake: the projected late share (late orders, plus `riskWeight` × each warned one) over this brakes. */
  lateBrake: 0.05,
  riskWeight: 0.5,
  /** While braked: prices × this; 0 declines the option. */
  brakeMarkup: 0,
  /** Plan fees with bidprice's fee solver and learned booking hazard (src/models/fees/); false: the ramp below. The
   * solver opens at `feeFloor` × the expected fee and reaches `topRatio` × typical `topLeadHours` before the last
   * pickup; `feeExtras`, `hazardFit`, `onTime`, `etaMu` and `lateTarget` pass through to the fee model as in bidprice.
   * `feeFloor`, `topRatio` and `topLeadHours` are the best bidprice tune's (flat on spread-1: EUR 9,199 at 95.6% on
   * time, fees 1.16 × typical, against the ramp's EUR 7,251 at 95.9%, 1.23 × typical). */
  feeSolver: true,
  feeFloor: 1.03,
  feeExtras: BIDPRICE.feeExtras,
  hazardFit: BIDPRICE.hazardFit,
  onTime: BIDPRICE.onTime,
  etaMu: BIDPRICE.etaMu,
  lateTarget: BIDPRICE.lateTarget,
  /** The fee ramp: `openFee` × typical, up to `topFee` × typical `topLeadHours` before the last pickup. */
  openFee: 0.9,
  topFee: 2.5,
  topLeadHours: 11.8,
  /** After the deadline warning: `topRatio` × typical at once, up to `urgentTop` × typical in two hours. */
  topRatio: 1.58,
  urgentTop: 2.5,
  /** The tick: reprice a dropped gig (`dropStep` × typical above), and one whose schedule ended `staleHours` ago
   * (climbing `climbStep` × typical an hour to `climbTop` × typical); at most `repriceMax` a tick. */
  staleHours: 2,
  dropStep: 0.15,
  climbStep: 0.1,
  climbTop: 3,
  repriceMax: 10,
  /** Expected driver cost = typical fee × `costFactor` × feature multipliers; never quote under cost × `minMargin`.
   * With the solver and `costPseudo` over 0, learned towards the fees paid over typical this week, `costFactor`
   * weighing `costPseudo` bookings. Off by default: on spread-1 the learned 1.19 let flat win underpriced orders
   * (EUR 7,208 at 94.4% against EUR 9,199 at 95.6% with 1.3). */
  costFactor: 1.3,
  costPseudo: 0,
  minMargin: 1.1,
  /** Seeds `ctx.random`. */
  seed: 1,
}
export type BaseParams = typeof BASE_DEFAULTS

/** Merges a strategy's own defaults over the base's, flat, so the bench can override any of them. */
export const withBase = <P extends Params>(own: P): BaseParams & P => ({ ...BASE_DEFAULTS, ...own })

/** Wins and losses for a dealer, an option or a day. */
export type Tally = { won: number; lost: number }

/** What the subclass sees, once per servable option. */
export type PriceCtx = {
  request: PriceRequest
  option: DeliveryOption
  listCents: number
  /** Expected driver cost of the option, in cents. */
  costCents: number
  dealerId: string
  /** The dealer's trust: +1 per on-time order, halved on a late one, capped at 25. */
  trust: number
  /** The dealer's share of the requests so far, 0 to 1. */
  dealerShare: number
  /** Drivers living near the pickup and the delivery place. */
  nearPickup: number
  nearDelivery: number
  now: number
  /** 0 Monday .. 6 Sunday, and the hour 0..23. */
  weekday: number
  hour: number
  /** Slack of the option in minutes (how much later than the latest safe pickup we still could be). */
  slack: number
  /** The projected late share and the open load of the option's pickup day. */
  lateShare: number
  load: number
  /** The trackers, read-only. */
  t: Trackers
  /** Seeded by `seed` and the request id: the same on a rebuild. */
  random: () => number
}

export type FeeCtx = { need: GigNeed; order: Order; legs: number[]; gig: FeeGig; now: number; urgent: boolean }
export type Outcome = { request: PriceRequest; prices: Prices; won: OptionKind | null }

export type Trackers = {
  trust: Map<string, number>
  requests: Map<string, number>
  total: number
  byDealer: Map<string, Tally>
  byOption: Map<OptionKind, Tally>
  byDay: Map<number, Tally>
  delivered: number
  late: number
}

type Pending = { request: PriceRequest; prices: Prices }

export abstract class PricedStrategy<P extends BaseParams = BaseParams> extends Strategy<P> {
  override readonly every = 30
  readonly log = new WeekLog()
  readonly near: Record<string, number>
  readonly t: Trackers = {
    trust: new Map(),
    requests: new Map(),
    total: 0,
    byDealer: new Map(),
    byOption: new Map(),
    byDay: new Map(),
    delivered: 0,
    late: 0,
  }
  private readonly pending = new Map<string, Pending>()
  private readonly done = new Set<string>()
  private readonly lateOrders = new Set<string>()
  private readonly brakes = { load: 0, late: 0, maxLoad: 0, quoted: 0, won: 0 }
  /** Bookings of our gigs and the fees paid over typical, summed: the learned cost and the summary. */
  private readonly paid = { booked: 0, overTypical: 0 }
  readonly feeParams: FeeParams
  readonly fees: FeeState

  constructor(setup: Setup, params: P) {
    super(setup, params)
    this.near = driversNear(setup.roster, setup.map)
    this.feeParams = feeParamsOf({ ...BIDPRICE, ...pick(params) }, setup.level)
    this.fees = newFeeState(this.feeParams)
  }

  /** The price of one servable option, as a multiple of its list price; null declines that option. */
  abstract price(ctx: PriceCtx): number | null

  /** The fee schedule of a gig: the fee solver's with `feeSolver`, else bidprice's ramp. */
  feePlan(ctx: FeeCtx): FeeStep[] {
    return this.planOf(ctx.gig, ctx.now)
  }

  /** The schedule for a gig from now: the solver's, or the ramp. */
  planOf(gig: FeeGig, now: number): FeeStep[] {
    if (this.params.feeSolver) return planFees(gig, now, this.fees, this.feeParams).schedule
    return ramp(gig, now, this.params, this.setup.level)
  }

  onOutcome(_outcome: Outcome, _won: boolean): void {}

  extraActions(_books: Books): Action[] {
    return []
  }

  observe(event: DeskEvent): void {
    this.settle(event.at)
    this.log.observe(event)
    learn(this.fees, event, this.feeParams)
    if (event.kind === 'gig_booked') {
      const gig = this.log.gigs.get(event.gigId)
      const typical = gig && this.log.requests.get(gig.orderId)?.referenceFeeCents
      const order = gig && this.log.orders.get(gig.orderId)
      if (gig && typical && order) {
        this.paid.booked++
        this.paid.overTypical += event.feeCents / ((typical * gig.legs.length) / order.legs.length)
      }
    }
    if (event.kind === 'price_request') {
      const d = event.request.dealerId
      this.t.requests.set(d, (this.t.requests.get(d) ?? 0) + 1)
      this.t.total++
    } else if (event.kind === 'order_won') {
      this.brakes.won++
      const p = this.pending.get(event.order.id)
      this.pending.delete(event.order.id)
      if (p) this.outcome(p, event.order.option)
    } else if (event.kind === 'delivered') {
      const order = this.log.orders.get(event.orderId)
      if (order && event.at > order.deadline) this.lateOrders.add(order.id)
      if (order && !this.done.has(order.id) && order.deliveredAt.every((at) => at !== null)) {
        this.done.add(order.id)
        const late = this.lateOrders.has(order.id)
        const trust = this.t.trust.get(order.dealerId) ?? 0
        this.t.trust.set(order.dealerId, late ? trust / 2 : Math.min(25, trust + 1))
        this.t.delivered++
        if (late) this.t.late++
      }
    }
  }

  sent(action: Action, result: ActionResult, books: Books): void {
    if (!result.ok) return
    if (action.type === 'quote') {
      const request = this.log.requests.get(action.requestId)
      if (request && Object.keys(action.prices).length > 0) {
        this.pending.set(request.id, { request, prices: action.prices })
        this.brakes.quoted++
      }
    } else if (action.type === 'reprice') {
      this.log.reprice(action.gigId, action.schedule)
      learn(
        this.fees,
        { kind: 'gig_repriced', at: books.now, gigId: action.gigId, schedule: action.schedule },
        this.feeParams,
      )
    } else if (action.type === 'withdraw') {
      learn(this.fees, { kind: 'gig_withdrawn', at: books.now, gigId: action.gigId }, this.feeParams)
    } else if (action.type === 'post') {
      const order = this.log.orders.get(action.stops[0]?.orderId ?? '')
      if (!order) return
      const legs = legsOf(action.stops, order.id)
      const gig = this.feeGig(order, legs, action.audience.experienced, books.now)
      this.log.post(result.id, order.id, legs, action.schedule)
      if (gig) {
        const event = {
          kind: 'gig_posted' as const,
          at: books.now,
          gigId: result.id,
          orderIds: [order.id],
          gig,
          schedule: action.schedule,
        }
        learn(this.fees, event, this.feeParams)
      }
    }
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const now = books.now
    const lateShare = this.lateShare(books)
    const prices: Prices = {}
    for (const { option, slack } of this.admitted(request, now, lateShare)) {
      const load = this.load(books, this.pickupDay(request, option))
      this.brakes.maxLoad = Math.max(this.brakes.maxLoad, load)
      const braked = load >= this.params.maxOpenPerDay || lateShare > this.params.lateBrake
      if (braked) {
        if (load >= this.params.maxOpenPerDay) this.brakes.load++
        else this.brakes.late++
        if (this.params.brakeMarkup <= 0) continue
      }
      const ctx = this.ctxOf(request, option, slack, now, lateShare, load)
      const multiple = this.price(ctx)
      if (multiple === null || !Number.isFinite(multiple)) continue
      const cents = multiple * option.listPriceCents * (braked ? this.params.brakeMarkup : 1)
      prices[option.kind] = Math.round(Math.max(cents, ctx.costCents * this.params.minMargin))
    }
    return Object.keys(prices).length > 0 ? prices : null
  }

  gig(need: GigNeed, books: Books): GigPlan[] {
    const { order, legs, previous } = need
    const shapes: GigShape[] =
      need.why === 'urgent' && previous
        ? [previous]
        : gigShape(order, legs, this.log.factsOf(order.id), this.log.retryOf(order.id, legs), books.now, this.context())
    if (shapes.length === 0) throw new Error('cannot read the order')
    return shapes.map(({ stops, audience }) => {
      const gig = this.feeGig(order, legsOf(stops, order.id), audience.experienced, books.now)
      if (!gig) throw new Error(`no request for order ${order.id}`)
      const urgent = books.urgent.has(order.id)
      const plan = this.feePlan({ need, order, legs: legsOf(stops, order.id), gig, now: books.now, urgent })
      const schedule = urgent
        ? higher(plan, urgentRamp(books.now, gig.typicalCents, this.params), this.setup.level)
        : plan
      return { stops, audience, schedule }
    })
  }

  tick(books: Books): Action[] {
    const now = books.now
    this.settle(now)
    const p = this.params
    const level = this.setup.level
    const due = [...this.log.gigs].flatMap(([gigId, gig]) => {
      const order = books.orders.get(gig.orderId)
      if (!order || books.urgent.has(order.id) || books.booked.has(gigId)) return []
      if (!books.gigsOf(order.id).includes(gigId)) return []
      const ended = (gig.schedule.at(-1)?.at ?? now) + p.staleHours * HOUR <= now
      return gig.dropped || ended ? [{ gigId, gig, order }] : []
    })
    due.sort((a, b) => a.order.lastPickupAt - b.order.lastPickupAt)
    const reprices = due.slice(0, p.repriceMax).flatMap(({ gigId, gig, order }) => {
      const feeGig = this.feeGig(order, gig.legs, books.posts.get(gigId)?.audience.experienced ?? false, now)
      if (!feeGig) return []
      const fee = feeAt(gig.schedule, now)
      // With the solver, bidprice's way: the solver again from now, never under the fee in the app.
      const schedule = p.feeSolver
        ? higher(this.planOf(feeGig, now), [{ at: now, feeCents: fee }], level)
        : gig.dropped
          ? higher(ramp(feeGig, now, p, level), [{ at: now, feeCents: fee + p.dropStep * feeGig.typicalCents }], level)
          : climb(fee, now, feeGig, p, level)
      return schedule.length > 0 && (schedule.at(-1)?.feeCents ?? 0) > fee
        ? [{ type: 'reprice' as const, gigId, schedule }]
        : []
    })
    return [...reprices, ...this.extraActions(books)]
  }

  summary(): string {
    const b = this.brakes
    const { booked, overTypical } = this.paid
    const fees =
      booked > 0 ? `fees paid ${(overTypical / booked).toFixed(2)} × typical over ${booked} bookings` : 'no fee paid'
    return `base: quoted ${b.quoted}, won ${b.won}, braked options ${b.load} by load (max ${b.maxLoad.toFixed(1)}) and ${b.late} by lateness, late ${this.t.late} of ${this.t.delivered} delivered, ${fees}, cost factor ${this.costFactor().toFixed(2)}`
  }

  /** Fees over typical: `costFactor`; with the solver and `costPseudo` over 0, learned towards what this week's
   * bookings paid over typical. */
  costFactor(): number {
    const p = this.params
    if (!p.feeSolver || p.costPseudo <= 0) return p.costFactor
    return (this.paid.overTypical + p.costPseudo * p.costFactor) / (this.paid.booked + p.costPseudo)
  }

  /** Expected driver cost of an option, in cents: typical fee × `costFactor()` × simple feature multipliers. */
  costOf(request: PriceRequest, option: DeliveryOption, now: number): number {
    const f = featuresOf(request.legs, option.deadline, now, this.fewNear(request))
    let m = this.costFactor()
    if (f.premium) m *= 1.1
    if (f.privatePickup || f.privateDelivery) m *= 1.1
    if (f.fewDriversNear) m *= 1.2
    if (f.weekendDelivery) m *= 1.1
    if (option.kind === 'same_day') m *= 1.15
    return request.referenceFeeCents * m
  }

  /** The projected late share: late orders plus `riskWeight` × each warned undelivered one, over a prior of 20 on
   * time. */
  lateShare(books: Books): number {
    const atRisk = [...books.urgent].filter((id) => books.orders.has(id) && !this.done.has(id)).length
    return (this.t.late + this.params.riskWeight * atRisk) / (this.t.delivered + atRisk + 20)
  }

  /** Open gigs no driver holds whose last pickup falls on `day`, plus `pendingWeight` × pending quotes for it. */
  load(books: Books, day: number): number {
    let open = 0
    for (const [gigId, gig] of this.log.gigs) {
      const order = books.orders.get(gig.orderId)
      if (!order || books.booked.has(gigId) || Math.floor(order.lastPickupAt / DAY) !== day) continue
      if (books.gigsOf(order.id).includes(gigId)) open++
    }
    let pending = 0
    for (const { request, prices } of this.pending.values()) {
      const days = request.options.filter((o) => prices[o.kind] !== undefined).map((o) => this.pickupDay(request, o))
      if (days.includes(day)) pending += 1 / days.length
    }
    return open + this.params.pendingWeight * pending
  }

  private admitted(request: PriceRequest, now: number, lateShare: number) {
    const context = this.context()
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const served = options.map((option) => ({ option, ...canServe(request, option, now, context) })).filter((v) => v.ok)
    const tight = 1 + Math.max(0, lateShare / this.params.lateBrake - 0.5)
    const comfortable = served.filter((v) => v.slack >= this.params.comfortHours * HOUR * tight)
    return comfortable.length > 0 ? comfortable : served.slice(-1)
  }

  private ctxOf(
    request: PriceRequest,
    option: DeliveryOption,
    slack: number,
    now: number,
    lateShare: number,
    load: number,
  ): PriceCtx {
    const requests = this.t.requests.get(request.dealerId) ?? 0
    return {
      request,
      option,
      listCents: option.listPriceCents,
      costCents: this.costOf(request, option, now),
      dealerId: request.dealerId,
      trust: this.t.trust.get(request.dealerId) ?? 0,
      dealerShare: this.t.total > 0 ? requests / this.t.total : 0,
      nearPickup: this.near[request.legs[0]?.pickup.placeId ?? ''] ?? 0,
      nearDelivery: this.near[request.legs[0]?.delivery.placeId ?? ''] ?? 0,
      now,
      weekday: Math.floor(now / DAY) % 7,
      hour: Math.floor((now % DAY) / HOUR),
      slack,
      lateShare,
      load,
      t: this.t,
      random: rng(`${this.params.seed}/${request.id}/${option.kind}`),
    }
  }

  /** Quotes not won by `respondBy` are lost. */
  private settle(now: number): void {
    for (const [id, p] of this.pending) {
      if (p.request.respondBy >= now) continue
      this.pending.delete(id)
      this.outcome(p, null)
    }
  }

  private outcome(p: Pending, won: OptionKind | null): void {
    const day = Math.floor(p.request.arrivedAt / DAY)
    const bump = <K>(map: Map<K, Tally>, key: K) => {
      const tally = map.get(key) ?? { won: 0, lost: 0 }
      if (won) tally.won++
      else tally.lost++
      map.set(key, tally)
    }
    bump(this.t.byDealer, p.request.dealerId)
    bump(this.t.byDay, day)
    for (const kind of Object.keys(p.prices) as OptionKind[]) if (!won || kind === won) bump(this.t.byOption, kind)
    this.onOutcome({ ...p, won }, won !== null)
  }

  private pickupDay(request: PriceRequest, option: DeliveryOption): number {
    return Math.floor((option.deadline - driveMinutes(this.setup.map, request.legs)) / DAY)
  }

  private fewNear(request: PriceRequest): boolean {
    return fewDriversNear(request.legs[0]?.delivery.placeId ?? '', this.setup.roster, this.setup.map)
  }

  private feeGig(order: Order, legs: number[], experienced: boolean, at: number): FeeGig | null {
    const request = this.log.requests.get(order.id)
    if (!request) return null
    return orderFeeGig(order, request, legs, experienced, at, this.log.seen(order.id, legs), 1, this.setup)
  }

  private context(): Context {
    return { map: this.setup.map, level: this.setup.level, forecasts: this.log.forecasts }
  }
}

/** A strategy kind from the subclass and its own defaults, merged over the base's. */
export function priced<P extends Params>(
  own: P,
  Kind: new (setup: Setup, params: BaseParams & P) => PricedStrategy<BaseParams & P>,
): StrategyKind<BaseParams & P> {
  return { defaults: withBase(own), build: (setup, params) => new Kind(setup, params) }
}

/** The base params that bidprice's `feeParamsOf` reads. */
function pick(p: BaseParams) {
  const { feeSolver, feeExtras, hazardFit, onTime, etaMu, lateTarget, feeFloor, topRatio, topLeadHours } = p
  return { feeSolver, feeExtras, hazardFit, onTime, etaMu, lateTarget, feeFloor, topRatio, topLeadHours }
}

/** A small seeded generator (mulberry32 over a string hash). */
export function rng(seed: string): () => number {
  let a = 0
  for (let i = 0; i < seed.length; i++) a = (Math.imul(a ^ seed.charCodeAt(i), 2654435761) + i) | 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
