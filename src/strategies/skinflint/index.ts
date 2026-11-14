/** skinflint: a penny-pinching broker. Dull prices (a fixed markup per option plus trust), and every effort on the
 * fee side: open low, rise on a convex curve that reaches a generous fee only near the last pickup, open lower where
 * many drivers live at the delivery town, add premiums only for hard work, and rescue late gigs with direct offers. */
import type {
  Action,
  DeskEvent,
  FeeStep,
  Order,
  PostAction,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  type Context,
  DAY,
  FIRST_TRY,
  features,
  gigShape,
  HOUR,
  pickOption,
  type Retry,
  readNote,
  retryAfter,
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

export type SkinflintParams = {
  markupSameDay: number
  markupNextDay: number
  markupThreeDays: number
  /** Price up per on-time order of the dealer, up to trustCap orders. */
  trustStep: number
  trustCap: number
  /** Opening fee over typical, before premiums and the home-town discount. */
  open: number
  /** The fee over typical at the last useful minute (lastPickupAt - closeLead). */
  close: number
  /** Curve exponent: >1 stays low longer. */
  curve: number
  closeLeadHours: number
  stepMinutes: number
  privatePremium: number
  tradeInPremium: number
  premiumCarPremium: number
  fridayPremium: number
  /** Opening discount when at least homeDrivers drivers live at the delivery town; a surcharge when none. */
  homeDiscount: number
  homeDrivers: number
  lonelyPremium: number
  /** Opening discount per day of slack beyond the first, up to slackDays. */
  slackDiscount: number
  slackDays: number
  urgentOpen: number
  urgentClose: number
  /** Direct offers: when an open gig has under offerHours to its last pickup, offer at the current fee x offerFactor. */
  offerHours: number
  offerFactor: number
  tickMinutes: number
}

const DEFAULTS: SkinflintParams = {
  markupSameDay: 1.3,
  markupNextDay: 1.24,
  markupThreeDays: 1.18,
  trustStep: 0.01,
  trustCap: 25,
  open: 0.72,
  close: 1.35,
  curve: 2,
  closeLeadHours: 3,
  stepMinutes: 60,
  privatePremium: 0.06,
  tradeInPremium: 0.2,
  premiumCarPremium: 0.12,
  fridayPremium: 0.08,
  homeDiscount: 0.05,
  homeDrivers: 8,
  lonelyPremium: 0.06,
  slackDiscount: 0.03,
  slackDays: 2,
  urgentOpen: 1.5,
  urgentClose: 2.4,
  offerHours: 10,
  offerFactor: 1.05,
  tickMinutes: 30,
}

class Skinflint extends Strategy<SkinflintParams> {
  override readonly every: number
  private readonly context: Context
  private readonly homes = new Map<string, string[]>()
  private readonly onTime = new Map<string, number>()
  private readonly counted = new Set<string>()
  private readonly retries = new Map<string, Retry>()
  private readonly offered = new Map<string, number>() // gig -> offers sent
  private readonly driverDay = new Map<string, number>() // driver:day -> offers
  private offers = 0

  constructor(setup: Setup, params: SkinflintParams) {
    super(setup, params)
    this.every = params.tickMinutes
    this.context = { map: setup.map, level: setup.level }
    for (const driver of setup.roster) {
      const list = this.homes.get(driver.homePlaceId) ?? []
      list.push(driver.id)
      this.homes.set(driver.homePlaceId, list)
    }
  }

  override observe(event: DeskEvent, books: Books): void {
    if (event.kind !== 'delivered') return
    const order = books.orders.get(event.orderId)
    if (!order || this.counted.has(order.id)) return
    const others = order.legs.every((_, leg) => leg === event.leg || order.deliveredAt[leg] != null)
    if (!others) return
    this.counted.add(order.id)
    if (event.at <= order.deadline) this.onTime.set(order.dealerId, (this.onTime.get(order.dealerId) ?? 0) + 1)
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const option = pickOption(request, books.now, this.context)
    if (!option) return null
    const p = this.params
    const markup =
      option.kind === 'same_day' ? p.markupSameDay : option.kind === 'next_day' ? p.markupNextDay : p.markupThreeDays
    const trust = 1 + p.trustStep * Math.min(p.trustCap, this.onTime.get(request.dealerId) ?? 0)
    return { [option.kind]: Math.round(option.listPriceCents * markup * trust) }
  }

  gig(need: GigNeed, books: Books): GigPlan | GigPlan[] {
    const { order, previous } = need
    const request = books.requests.get(order.id)
    const typical = request?.referenceFeeCents ?? 0
    const perCar = typical / Math.max(1, order.legs.length)
    if (previous) {
      const stops =
        need.why === 'repost'
          ? previous.stops.map((s) => (s.window && s.window.to < Infinity ? { ...s, window: undefined } : s))
          : previous.stops
      const cars = stops.filter((s) => s.kind === 'pickup').length
      return { stops, audience: previous.audience, schedule: this.schedule(order, perCar * cars, books, true) }
    }
    const facts = readNote(request?.note ?? null, request?.arrivedAt ?? books.now)
    let retry = FIRST_TRY
    if (need.failed) {
      const key = `${order.id}:${need.legs[0]}`
      retry = retryAfter(need.failed, order, request, need.legs[0] ?? 0, books.now, this.retries.get(key) ?? FIRST_TRY)
      this.retries.set(key, retry)
    }
    const shapes = gigShape(order, need.legs, facts, retry, books.now, this.context)
    const urgent = books.urgent.has(order.id) || need.failed !== undefined
    return shapes.map((shape) => {
      const cars = shape.stops.filter((s) => s.kind === 'pickup').length
      return { ...shape, schedule: this.schedule(order, perCar * cars, books, urgent) }
    })
  }

  /** The opening factor over typical for this order. */
  private opening(order: Order, now: number): number {
    const p = this.params
    let f = p.open
    const feat = features(order, this.setup.map)
    if (feat.privatePickup || feat.privateDelivery) f += p.privatePremium
    if (feat.tradeIn) f += p.tradeInPremium
    if (feat.premium) f += p.premiumCarPremium
    if (Math.floor(now / DAY) % 7 === 4) f += p.fridayPremium
    const home = this.homes.get(order.legs[0]?.delivery.placeId ?? '')?.length ?? 0
    if (home >= p.homeDrivers) f -= p.homeDiscount
    else if (home === 0) f += p.lonelyPremium
    const slackDays = (order.lastPickupAt - now) / DAY - 1
    f -= p.slackDiscount * Math.max(0, Math.min(p.slackDays, slackDays))
    return f
  }

  private schedule(order: Order, fee: number, books: Books, urgent: boolean): FeeStep[] {
    const p = this.params
    const now = books.now
    const at = (k: number) => Math.max(1, Math.round(fee * k))
    if (urgent || books.urgent.has(order.id)) {
      return [0, 1, 2, 3, 4].map((i) => ({
        at: now + i * 30,
        feeCents: at(p.urgentOpen + ((p.urgentClose - p.urgentOpen) * i) / 4),
      }))
    }
    const open = Math.min(this.opening(order, now), p.close)
    const end = order.lastPickupAt - p.closeLeadHours * HOUR
    const span = end - now
    if (!(span > p.stepMinutes)) return [{ at: now, feeCents: at(Math.max(open, p.close)) }]
    const steps = Math.min(48, Math.max(2, Math.ceil(span / p.stepMinutes) + 1))
    const out: FeeStep[] = []
    let last = 0
    for (let i = 0; i < steps; i++) {
      const x = i / (steps - 1)
      const fee = at(open + (p.close - open) * x ** p.curve)
      const t = Math.round(now + x * span)
      const feeCents = Math.max(fee, last)
      if (out.length && t <= out[out.length - 1]!.at) continue
      out.push({ at: t, feeCents })
      last = feeCents
    }
    return out
  }

  override tick(books: Books): Action[] {
    const p = this.params
    const actions: Action[] = []
    const day = Math.floor(books.now / DAY)
    const hour = (books.now % DAY) / HOUR
    if (hour < 7 || hour >= 22) return actions
    for (const [gigId, post] of books.posts) {
      if (books.booked.has(gigId)) continue
      if ((this.offered.get(gigId) ?? 0) >= 3) continue
      if (post.audience.experienced) continue
      const orderId = post.stops[0]?.orderId
      const order = orderId ? books.orders.get(orderId) : undefined
      if (!order || order.status !== 'waiting') continue
      if (!books.gigsOf(order.id).includes(gigId)) continue
      if (order.lastPickupAt - books.now > p.offerHours * HOUR) continue
      const fee = currentFee(post, books.now)
      if (!fee) continue
      const leg = order.legs[post.stops[0]?.leg ?? 0]
      if (!leg) continue
      const candidates = [
        ...(this.homes.get(leg.delivery.placeId) ?? []),
        ...(this.homes.get(leg.pickup.placeId) ?? []),
      ]
      const manual = post.audience.manualLicence
      const roster = new Map(this.setup.roster.map((d) => [d.id, d]))
      let sent = this.offered.get(gigId) ?? 0
      for (const driverId of candidates) {
        if (sent >= 3) break
        const d = roster.get(driverId)
        if (!d || (manual && d.licence !== 'manual')) continue
        const key = `${driverId}:${day}`
        if ((this.driverDay.get(key) ?? 0) >= 3) continue
        this.driverDay.set(key, (this.driverDay.get(key) ?? 0) + 1)
        actions.push({ type: 'offer', gigId, driverId, feeCents: Math.round(fee * p.offerFactor) })
        sent++
        this.offers++
      }
      this.offered.set(gigId, sent)
    }
    return actions
  }

  override summary(): string {
    return `skinflint: ${this.offers} direct offers`
  }
}

const currentFee = (post: PostAction, now: number): number => {
  let fee = 0
  for (const step of post.schedule) if (step.at <= now) fee = step.feeCents
  return fee || (post.schedule[0]?.feeCents ?? 0)
}

export const skinflint: StrategyKind<SkinflintParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Skinflint(setup, params),
}
