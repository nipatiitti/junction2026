/** The lean strategy: the whole policy in three decisions, each from the measured level 8 facts (README.md).
 *
 * 1. Price. Each option is quoted at the price that earns the most: the chance that the dealer takes it (demand.ts,
 *    learned from this week's wins and losses) times what the win leaves after the drivers and after `capacity`, the
 *    worth of one order's place in the week. Drivers move about a third of what dealers ask for, so that worth is
 *    high, and it is steered so that we win `target` of the requests: the dearest third, not the first third.
 * 2. Fee. A gig holds `open` × typical and raises only at a few hours of its own before the last pickup (fees.ts):
 *    drivers who see fees rise wait for the rise. It climbs fast only when the last pickup is near.
 * 3. Serve. Only options that can arrive on time with room to spare are quoted, and the note decides the windows,
 *    plates and licence of every gig (src/ops). Open cars that one driver can take in a row go out as one gig
 *    (planner.ts, chains.ts).
 *
 * All state is rebuilt from `observe` and `sent`, so a restart in the final loses nothing. */
import type {
  Action,
  ActionResult,
  DeliveryOption,
  DeskEvent,
  FeeStep,
  Order,
  PriceRequest,
  StopRef,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  type Context,
  canServe,
  DAY,
  driveMinutes,
  FIRST_TRY,
  features,
  gigShape,
  HOUR,
  type NoteFacts,
  type Retry,
  readNote,
  retryAfter,
  type Setback,
  type Snowfall,
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
import { bestPrice, Demand } from './demand.ts'
import { awake, BOOK_AHEAD, fast, feeAt, SHORT, stepped } from './fees.ts'
import { Offers } from './offers.ts'
import { Planner } from './planner.ts'
import { Supply } from './supply.ts'

export const DEFAULTS = {
  /** The share of the week's requests to win, in a world with 777 drivers (the median). */
  target: 0.3,
  /** The worth of an order's place in the week when it starts, × the typical fee, and how fast it follows the
   * share won: this much for each quote that wins above or loses below the target. Both 0 (off): with the wider
   * `noise` the best price needs no charge, and the charge priced us out by Friday (README.md). */
  capacity: 0,
  gain: 0,
  /** How much of that worth is the same for every order (`flatEuros` × `capacity`), not in proportion to its typical
   * fee: a short hop takes a driver's place in the day as a long one does. */
  flatShare: 0.5,
  flatEuros: 60,
  /** The fee a gig opens at, × typical. It holds it and raises only 24, 16, 10 and 6 hours before the last pickup
   * (to 1.05, 1.25, 1.55 and 2 × typical). */
  open: 0.88,
  /** 1 moves each gig's raises by up to 1.5 hours either way and their size by 5%, drawn from the order id, so that
   * drivers cannot time a second look; 0 keeps the table. */
  jitter: 1,
  /** Time the raises by the drivers' planning (fees.ts, `planBy`): three raises over the waking time until a gig
   * should have its driver (21:00 the evening before for a last pickup before 16:00, else 5 hours before it), then
   * the top. Without it the raises come at fixed hours before the last pickup, a car won 7 hours before it opens
   * at 1.55 × typical, and a morning pickup gets its raises when drivers have planned their day. It also ends a
   * hold or a chain that would run into the last planning hours. */
  spread: true,
  /** A premium car's cost × this, and what a private pickup and a private delivery add × typical. */
  premium: 3,
  privatePickup: 0.25,
  privateDelivery: 0.25,
  /** The fee a gig for a later day shows in its first hour, × typical; 0 opens at `open`. */
  early: 0,
  /** What a booking costs × typical before this week's bookings say: the measured median with the climb's steps. */
  feeRatio: 0.84,
  /** Learn what a booking costs by pickup place, delivery place and whether the car goes today (supply.ts), not
   * as one figure for the week. */
  supply: true,
  /** Added to the cost × typical for drops, failed visits and refunds. */
  overhead: 0.06,
  /** An option needs this many waking hours between now and the last minute to book, or we do not quote it. */
  minHours: 4,
  /** Never quote under this × the expected cost. */
  minMargin: 1.05,
  /** The noise that stays in one request's threshold, as a logistic scale in log price: 20 to 25% stays whatever
   * we learn. A wider noise makes the best price higher, because a dearer quote then loses fewer wins. */
  noise: 0.28,
  /** How much of the dealer's trust (1% for each order on time) goes into the price. */
  trust: 0.7,
  /** How much the target falls for each 1.0 × typical that bookings cost over `feeRatio`. 0 leaves volume to the
   * lateness alone: dear bookings are already in the price. */
  feeBrake: 1.5,
  /** The late share from which we win less, and the one from which options need twice the room. */
  lateSoft: 0.04,
  lateHard: 0.05,
  /** Open gigs without a driver from which we win less. */
  openGigs: 40,
  /** Direct offers (offers.ts): each driver who views a gig and lives near it gets the fee in the app × this as an
   * offer, so that waiting for a raise pays nothing. 0 sends none. */
  offers: 0,
  /** The top of the fast climb × typical, and for a car that is late already. */
  urgentTop: 2,
  lateTop: 1.7,
  /** Chains (chains.ts): post open cars together when one driver can take them one after the other. A car joins
   * when the next is collected within `maxHop` road minutes of its delivery, a chain holds `maxCars` at most and
   * must cost a driver `minSaving` less than its cars alone. It goes back to single gigs when no driver has taken
   * it `chainHours` before its last start. */
  chains: true,
  maxHop: 60,
  maxCars: 4,
  minSaving: 0.15,
  chainHours: 5,
  /** A new car that may join a chain waits this many hours for a partner before it is posted alone: half of the
   * single gigs book within half an hour, before a partner can arrive, and a chain of cars never posted before
   * books 79% of the time against 57%. 0 posts at once. */
  holdHours: 2,
  /** A chain that no driver took this many hours after its post is taken apart while its cars still have time; 0
   * waits until `chainHours` before its last start. */
  chainPatience: 0,
  /** Plan the chain before the bid: a request that completes a chain with a car we hold or have open is costed at
   * its share of the chain and pays `pairCharge` of the capacity charge. Each of our cars backs one bid at a time. */
  chainBid: false,
  pairCharge: 1,
}
export type LeanParams = typeof DEFAULTS

type OptionKind = DeliveryOption['kind']
const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))
const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')

class Lean extends Strategy<LeanParams> {
  override readonly every = 15
  private readonly demand: Demand
  private readonly planner: Planner
  private readonly supply: Supply
  private readonly offers: Offers
  private readonly drivers: number
  private capacity: number
  private feeRatio: number
  /** Our quotes that wait for the dealer: request id -> prices. */
  private readonly pending = new Map<string, Prices>()
  /** The requests that wait for their dealer: the yard of the first car, and when the dealer decides. */
  private asked: { id: string; yard: string | undefined; respondBy: number }[] = []
  /** Gig id -> the schedule in the app. */
  private readonly schedules = new Map<string, FeeStep[]>()
  /** Gig id -> the fee its driver booked at, for the gigs a driver gave back. */
  private readonly dropped = new Map<string, number>()
  private readonly bookedAt = new Map<string, number>()
  /** "<order id> <leg>" -> what the car's setbacks taught. */
  private readonly retries = new Map<string, Retry>()
  /** Order id -> the fee that its last gig showed when its window ended. */
  private readonly floors = new Map<string, number>()
  private readonly forecasts: Snowfall[] = []
  /** Dealer id -> its delivered orders, in order; and the orders with a refund. */
  private readonly delivered = new Map<string, string[]>()
  private readonly late = new Set<string>()
  private done = 0
  private readonly tally = { requests: 0, quoted: 0, won: 0, multiples: 0, bookings: 0, ratios: 0 }
  constructor(setup: Setup, params: LeanParams) {
    super(setup, params)
    this.supply = new Supply(params.feeRatio)
    this.offers = new Offers(setup.map, setup.roster)
    this.demand = new Demand(setup.level, params.noise)
    this.drivers = setup.roster.length > 0 ? setup.roster.length / 777 : 1
    this.capacity = params.capacity
    this.feeRatio = params.feeRatio
    this.planner = new Planner(params, setup.map, params.chains && setup.level >= 3, {
      context: () => this.context(),
      troubled: (orderId, gigId) =>
        this.retries.has(`${orderId} 0`) || (gigId !== undefined && this.dropped.has(gigId)),
    })
  }

  // ------------------------------------------------------------------------------------------------- the price

  quote(request: PriceRequest, books: Books): Prices | null {
    const now = books.now
    const lateShare = this.lateShare(books)
    const context = this.context(lateShare > this.params.lateHard ? 0.5 : 1)
    const facts = readNote(request.note, request.arrivedAt)
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const p = this.params
    const quotes: [OptionKind, number][] = []
    for (const option of options) {
      if (!canServe(request, option, now, context).ok) continue
      if (this.setup.level <= 3) return { [option.kind]: option.listPriceCents }
      const alone = this.cost(request, option, facts, now)
      if (alone === null) continue
      const share = this.planner.share(request, option, facts, books)
      const cost = alone * share
      const belief = this.demand.belief(this.demand.keys(request, option.kind), this.trustOffset(request.dealerId))
      const crowd = 1 + 0.04 * Math.max(0, this.askedFrom(request) - 4)
      const place = (1 - p.flatShare) * request.referenceFeeCents + p.flatShare * p.flatEuros * 100
      const charge = cost + this.capacity * crowd * place * (share < 1 ? p.pairCharge : 1)
      const best = bestPrice(belief, option.listPriceCents, charge)
      if (best === null) continue
      quotes.push([option.kind, Math.round(Math.max(best, cost * p.minMargin))])
    }
    return quotes.length > 0 ? Object.fromEntries(quotes) : null
  }

  /** What the drivers of an option cost: the typical fee × what bookings pay this week, more when the gig has
   * little time to find its driver or is work that drivers ask more for. */
  private cost(request: PriceRequest, option: DeliveryOption, facts: NoteFacts, now: number): number | null {
    const f = features(request, this.setup.map, option)
    const deadline = Math.min(option.deadline, facts.deadline ?? Infinity)
    const lastPickup = deadline - 1.1 * driveMinutes(this.setup.map, request.legs) - 30
    const time = awake(now + 15, lastPickup - BOOK_AHEAD)
    if (time < this.params.minHours * HOUR) return null // too little time for the raises to find a driver
    const leg = request.legs[0]
    const today = lastPickup < (Math.floor(now / DAY) + 1) * DAY
    const learned = this.supply.ratio(this.supply.keys(leg?.pickup.placeId, leg?.delivery.placeId, today))
    let ratio = (this.params.supply ? learned : this.feeRatio) + this.params.overhead
    if (f.privatePickup) ratio += this.params.privatePickup
    else if (f.privateDelivery) ratio += this.params.privateDelivery
    if (f.tradeIn) ratio += 0.05
    if (f.weekendDelivery) ratio += 0.05
    if (facts.deadline !== null || facts.pickupHours !== null || facts.deliveryHours !== null) ratio += 0.03
    if (f.premium) ratio *= this.params.premium // one driver in twelve may take it
    return request.referenceFeeCents * ratio
  }

  /** The share of the requests to win now: less when bookings cost more than planned, when gigs wait without a
   * driver, and when orders arrive late. */
  private target(books: Books): number {
    const p = this.params
    let open = 0
    for (const order of books.orders.values())
      for (const gigId of books.gigsOf(order.id)) if (!books.booked.has(gigId)) open++
    return (
      p.target *
      this.drivers *
      clamp(1 - p.feeBrake * (this.feeRatio - p.feeRatio), 0.5, 1.25) *
      clamp(2 - open / p.openGigs, 0.4, 1) *
      clamp(1 - 10 * Math.max(0, this.lateShare(books) - p.lateSoft), 0.2, 1)
    )
  }

  /** Late orders, and half of each one warned without a driver, over the orders done (and 20 on time for a start). */
  private lateShare(books: Books): number {
    let atRisk = 0
    for (const id of books.urgent) {
      const order = books.orders.get(id)
      const waits = order?.deliveredAt.some((at) => at === null) && !books.gigsOf(id).some((g) => books.booked.has(g))
      if (waits) atRisk++
    }
    return (this.late.size + 0.5 * atRisk) / (this.done + atRisk + 20)
  }

  /** The dealer's trust as a move of its threshold: each order on time adds 1%, a late one halves the count. */
  private trustOffset(dealerId: string): number {
    return this.params.trust * Math.log(1 + this.trustCount(dealerId) / 100)
  }

  /** The dealer's count of orders on time, up to 25; a late one halves it. */
  private trustCount(dealerId: string): number {
    let count = 0
    for (const id of this.delivered.get(dealerId) ?? [])
      count = this.late.has(id) ? Math.floor(count / 2) : Math.min(25, count + 1)
    return count
  }

  /** The other requests from the same yard that wait for their dealer: a bulk order asks for 30 to 40 at once, and
   * one yard cannot find that many drivers. */
  private askedFrom(request: PriceRequest): number {
    const yard = request.legs[0]?.pickup.placeId
    return this.asked.filter((other) => other.yard === yard && other.id !== request.id).length
  }

  /** A quote won (with the option the dealer took) or lost: the demand learns, and the worth of capacity follows
   * the share won. */
  private outcome(requestId: string, won: OptionKind | null, books: Books): void {
    this.planner.release(requestId)
    const prices = this.pending.get(requestId)
    const request = books.requests.get(requestId)
    this.pending.delete(requestId)
    if (!prices || !request) return
    const offset = this.trustOffset(request.dealerId)
    for (const option of request.options) {
      const cents = prices[option.kind]
      if (cents === undefined || (won && option.kind !== won)) continue
      const multiple = cents / option.listPriceCents
      this.demand.learn(this.demand.keys(request, option.kind), offset, multiple, won !== null)
      if (won) this.tally.multiples += multiple
    }
    if (won) this.tally.won++
    this.capacity = clamp(this.capacity + this.params.gain * ((won ? 1 : 0) - this.target(books)), 0, 2)
  }

  // --------------------------------------------------------------------------------------------------- the gig

  gig(need: GigNeed, books: Books): GigPlan[] {
    const { order, legs, previous } = need
    const request = books.requests.get(order.id)
    if (!request) throw new Error(`no request for order ${order.id}`)
    const now = books.now
    const typical = (stops: readonly StopRef[]) => this.typicalOf(stops, books)
    if (need.why === 'urgent' && previous) {
      const gigId = books.gigsOf(order.id).find((id) => books.posts.get(id) === previous)
      // A gig that a driver gave back starts again from the fee that booked it, not from the fee of the hours since.
      const shown = gigId ? (this.dropped.get(gigId) ?? feeAt(this.schedules.get(gigId) ?? previous.schedule, now)) : 0
      const schedule = this.fees(order, typical(previous.stops), now, shown, true)
      return [{ stops: previous.stops, audience: previous.audience, schedule }]
    }
    const facts = readNote(request.note, request.arrivedAt)
    const shapes = gigShape(order, legs, facts, this.retryOf(order.id, legs), now, this.context())
    if (shapes.length === 0) throw new Error(`cannot read order ${order.id}`)
    const floor = this.floors.get(order.id) ?? 0
    return shapes.map(({ stops, audience }) => ({
      stops,
      audience,
      schedule: this.fees(order, typical(stops), now, floor),
    }))
  }

  /** The schedule of a gig from now, never under `floor` cents: the stepped one while there is time to book, the
   * fast one when the last pickup is near, and a calmer one for a car that is late already. */
  private fees(order: Order, typical: number, now: number, floor: number, warned = false): FeeStep[] {
    const p = this.params
    const shown = floor / typical
    if (now > order.lastPickupAt) return fast(now, typical, Math.max(shown, 1.1), 0.05, 30, p.lateTop)
    if (warned || awake(now, order.lastPickupAt - BOOK_AHEAD) < SHORT)
      return fast(now, typical, Math.max(shown + 0.05, 1.15), 0.12, 15, Math.max(p.urgentTop, shown + 0.05))
    return stepped(now, typical, order.lastPickupAt, p.open, shown, p.jitter, order.id, p.spread, p.early)
  }

  private retryOf(orderId: string, legs: readonly number[]): Retry {
    return legs
      .map((leg) => this.retries.get(`${orderId} ${leg}`) ?? FIRST_TRY)
      .reduce((a, b) => ({
        pickupFrom: Math.max(a.pickupFrom, b.pickupFrom),
        manualLicence: a.manualLicence || b.manualLicence,
        plates: a.plates || b.plates,
        late: a.late || b.late,
      }))
  }

  private setback(orderId: string, leg: number, reason: Setback, books: Books): void {
    const order = books.orders.get(orderId)
    if (!order) return
    const key = `${orderId} ${leg}`
    this.retries.set(key, retryAfter(reason, order, books.requests.get(orderId), leg, books.now, this.retries.get(key)))
  }

  /** A gig that a driver gave back shows the fee of the hours it was held. It takes a new schedule from the fee
   * that booked it. */
  tick(books: Books): Action[] {
    const actions: Action[] = []
    for (const [gigId, fee] of this.dropped) {
      this.dropped.delete(gigId)
      const post = books.posts.get(gigId)
      const order = post && books.orders.get(post.stops[0]?.orderId ?? '')
      const request = order && books.requests.get(order.id)
      if (!post || !order || !request || books.booked.has(gigId) || !books.gigsOf(order.id).includes(gigId)) continue
      const schedule = this.fees(order, this.typicalOf(post.stops, books), books.now, fee)
      if (schedule.length > 0) actions.push({ type: 'reprice', gigId, schedule })
    }
    if (this.params.offers > 0 && this.setup.level >= 3) {
      const fee = (gigId: string) => this.params.offers * feeAt(this.schedules.get(gigId) ?? [], books.now)
      actions.push(...this.offers.actions(books, fee))
    }
    return [...actions, ...this.planner.actions(books)]
  }

  override hold(need: GigNeed, books: Books): boolean {
    return this.planner.hold(need, books)
  }

  /** The typical fees of a gig's cars as single gigs, summed. */
  private singlesOf(stops: readonly StopRef[], books: Books): number {
    let sum = 0
    for (const stop of pickups(stops)) {
      const request = books.requests.get(stop.orderId)
      if (request)
        sum += request.referenceFeeCents / (books.orders.get(stop.orderId)?.legs.length ?? request.legs.length)
    }
    return sum
  }

  /** The unit of a gig's fee schedule: what a chain is worth to its driver, or the cars' typical fees. */
  private typicalOf(stops: readonly StopRef[], books: Books): number {
    return this.planner.typical(stops) ?? this.singlesOf(stops, books)
  }

  // ------------------------------------------------------------------------------------------------- the books

  override observe(event: DeskEvent, books: Books): void {
    switch (event.kind) {
      case 'price_request':
        this.tally.requests++
        this.demand.dawn(Math.floor(event.at / DAY))
        this.asked = this.asked.filter((other) => other.respondBy > event.at)
        this.asked.push({
          id: event.request.id,
          yard: event.request.legs[0]?.pickup.placeId,
          respondBy: event.request.respondBy,
        })
        break
      case 'gig_viewed':
        if (this.params.offers > 0) this.offers.viewed(event.gigId, event.driverId)
        break
      case 'offer_answered':
        this.offers.answered(event.answer === 'accepted')
        break
      case 'order_won':
        this.outcome(event.order.id, event.order.option, books)
        break
      case 'order_lost':
        this.outcome(event.requestId, null, books)
        break
      case 'gig_booked': {
        this.dropped.delete(event.gigId)
        this.bookedAt.set(event.gigId, event.feeCents)
        const post = books.posts.get(event.gigId)
        const singles = post ? this.singlesOf(post.stops, books) : 0
        if (!post || !(singles > 0)) break
        this.planner.booked(event.gigId, event.feeCents / singles)
        const ratio = clamp(event.feeCents / singles, 0.3, 2.5)
        for (const stop of pickups(post.stops)) {
          const order = books.orders.get(stop.orderId)
          const leg = order?.legs[stop.leg]
          if (!order || !leg) continue
          const today = order.lastPickupAt < (Math.floor(event.at / DAY) + 1) * DAY
          this.supply.learn(this.supply.keys(leg.pickup.placeId, leg.delivery.placeId, today), ratio)
        }
        // A chain counts once for each of its cars: the cost behind a bid is a car's, not a booking's.
        for (let i = pickups(post.stops).length; i > 0; i--) this.feeRatio += 0.04 * (ratio - this.feeRatio)
        this.tally.bookings++
        this.tally.ratios += ratio
        break
      }
      case 'gig_dropped':
      case 'no_show':
        this.dropped.set(event.gigId, this.bookedAt.get(event.gigId) ?? 0)
        break
      case 'visit_failed':
        this.setback(event.orderId, event.leg, event.reason, books)
        break
      case 'gig_expired': {
        const post = books.posts.get(event.gigId)
        this.planner.expired(event.gigId, post?.stops ?? [])
        for (const stop of pickups(post?.stops ?? [])) {
          this.setback(stop.orderId, stop.leg, 'expired', books)
          this.floors.set(stop.orderId, feeAt(this.schedules.get(event.gigId) ?? post?.schedule ?? [], event.at))
        }
        break
      }
      case 'forecast':
        this.forecasts.push({ from: event.from, to: event.to, placeIds: event.placeIds })
        break
      case 'ledger': {
        const { kind, orderId } = event.line
        if (!orderId) break
        if (kind === 'late_refund' || kind === 'undelivered_penalty') this.late.add(orderId)
        const dealerId = books.requests.get(orderId)?.dealerId
        if (kind === 'revenue' && dealerId) {
          this.done++
          this.delivered.set(dealerId, [...(this.delivered.get(dealerId) ?? []), orderId])
        }
        break
      }
    }
  }

  override sent(action: Action, result: ActionResult, books: Books): void {
    this.planner.sent(action, result, books)
    if (!result.ok) return
    if (action.type === 'quote') {
      this.pending.set(action.requestId, action.prices)
      this.tally.quoted++
    } else if (action.type === 'post') this.schedules.set(result.id, action.schedule)
    else if (action.type === 'reprice') this.schedules.set(action.gigId, action.schedule)
  }

  override summary(): string {
    const t = this.tally
    const share = t.requests > 0 ? (100 * t.won) / t.requests : 0
    const multiple = t.won > 0 ? t.multiples / t.won : 0
    const paid = t.bookings > 0 ? t.ratios / t.bookings : 0
    return `lean: won ${t.won} of ${t.requests} requests (${share.toFixed(1)}%) at ${multiple.toFixed(2)} × list, ${t.bookings} bookings at ${paid.toFixed(2)} × typical, capacity worth ${this.capacity.toFixed(2)} × typical at the end, ${this.late.size} late of ${this.done} done. ${this.planner.summary()} Offers: ${this.offers.tally.accepted} accepted of ${this.offers.tally.sent}.`
  }

  private context(tightening = 1): Context {
    return { map: this.setup.map, level: this.setup.level, forecasts: this.forecasts, tightening }
  }
}

export const lean: StrategyKind<LeanParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Lean(setup, params),
}
