/** The lean strategy: the whole policy in three decisions, each from the measured level 8 facts (README.md).
 *
 * 1. Price. Each option is quoted at the price that earns the most: the chance that the dealer takes it (demand.ts,
 *    learned from this week's wins and losses) times what the win leaves after the drivers and after `capacity`, the
 *    worth of one order's place in the week. Drivers move about a third of what dealers ask for, so that worth is
 *    high, and it is steered so that we win `target` of the requests: the dearest third, not the first third.
 * 2. Fee. A gig opens at 0.68 × typical and climbs slowly through the range where gigs book (fees.ts), so it pays
 *    what its own driver needs. It climbs fast only when the last pickup is near.
 * 3. Serve. Only options that can arrive on time with room to spare are quoted, and the note decides the windows,
 *    plates and licence of every gig (src/ops).
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
  earliestPickup,
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
import { type Car, type Chain, findChains } from './chains.ts'
import { bestPrice, Demand } from './demand.ts'
import { awake, BOOK_AHEAD, fast, feeAt, openingFor, SHORT, slow, stepped } from './fees.ts'

export const DEFAULTS = {
  /** The share of the week's requests to win, in a world with 777 drivers (the median). */
  target: 0.3,
  /** The worth of an order's place in the week when it starts, × the typical fee, and how fast it follows the
   * share won: this much for each quote that wins above or loses below the target. */
  capacity: 0.4,
  gain: 0.02,
  /** How much of that worth is the same for every order (`flatEuros` × `capacity`), not in proportion to its typical
   * fee: a short hop takes a driver's place in the day as a long one does. */
  flatShare: 0.5,
  flatEuros: 60,
  /** The fee a gig opens at and the end of its slow climb, × typical. */
  open: 0.88,
  climbTo: 0.88,
  /** Instead of the climb: hold `open` × typical and raise only 24, 16, 10 and 6 hours before the last pickup (to
   * 1.05, 1.25, 1.55 and 2 × typical). */
  stepped: false,
  /** With `stepped`: 1 moves each gig's raises by up to 1.5 hours either way and their size by 5%, drawn from the
   * order id, so that drivers cannot time a second look; 0 keeps the table. */
  jitter: 1,
  /** Each delivery must arrive this share of its drive (20 minutes at least) before its deadline: a driver plans by
   * the road minutes, and real drives run longer. 0 leaves the deadline as the window. */
  buffer: 0,
  /** A premium car's cost × this, and what a private address adds × typical. */
  premium: 3,
  privateAddress: 0.25,
  /** What a booking costs × typical before this week's bookings say: the measured median with the climb's steps. */
  feeRatio: 0.84,
  /** Added to the cost × typical for drops, failed visits and refunds. */
  overhead: 0.06,
  /** An option needs this many waking hours between now and the last minute to book, or we do not quote it. */
  minHours: 4,
  /** Never quote under this × the expected cost. */
  minMargin: 1.05,
  /** How much of the dealer's trust (1% for each order on time) goes into the price. */
  trust: 0.7,
  /** The late share from which we win less, and the one from which options need twice the room. */
  lateSoft: 0.04,
  lateHard: 0.05,
  /** Open gigs without a driver from which we win less. */
  openGigs: 40,
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
   * single gigs book within half an hour, before a partner can arrive. 0 posts at once. */
  holdHours: 0,
}
export type LeanParams = typeof DEFAULTS

type OptionKind = DeliveryOption['kind']
const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))
const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')
const keyOf = (stops: readonly StopRef[]): string => stops.map((s) => `${s.orderId}/${s.leg}/${s.kind}`).join(' ')

class Lean extends Strategy<LeanParams> {
  override readonly every = 15
  private readonly demand: Demand
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
  /** The chains decided: the key of their stops -> the chain; and, once posted, gig id -> the chain. */
  private readonly planned = new Map<string, Chain>()
  private readonly chains = new Map<string, Chain>()
  /** The orders that were in a chain no driver took: they stay single. */
  private readonly single = new Set<string>()
  /** Order id -> the minute it first waited for a partner; and the orders whose wait is over. */
  private readonly heldSince = new Map<string, number>()
  private readonly released = new Set<string>()
  private readonly chained = { posted: 0, cars: 0, booked: 0, bookedCars: 0, ratios: 0, undone: 0 }

  constructor(setup: Setup, params: LeanParams) {
    super(setup, params)
    this.demand = new Demand(setup.level)
    this.drivers = setup.roster.length > 0 ? setup.roster.length / 777 : 1
    this.capacity = params.capacity
    this.feeRatio = params.feeRatio
  }

  // ------------------------------------------------------------------------------------------------- the price

  quote(request: PriceRequest, books: Books): Prices | null {
    const now = books.now
    const lateShare = this.lateShare(books)
    const context = this.context(lateShare > this.params.lateHard ? 0.5 : 1)
    const facts = readNote(request.note, request.arrivedAt)
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const prices: Prices = {}
    for (const option of options) {
      if (!canServe(request, option, now, context).ok) continue
      if (this.setup.level <= 3) return { [option.kind]: option.listPriceCents }
      const cost = this.cost(request, option, facts, now)
      if (cost === null) continue
      const belief = this.demand.belief(this.demand.keys(request, option.kind), this.trustOffset(request.dealerId))
      const crowd = 1 + 0.04 * Math.max(0, this.askedFrom(request) - 4)
      const p = this.params
      const place = (1 - p.flatShare) * request.referenceFeeCents + p.flatShare * p.flatEuros * 100
      const price = bestPrice(belief, option.listPriceCents, cost + this.capacity * crowd * place)
      if (price !== null) prices[option.kind] = Math.round(Math.max(price, cost * this.params.minMargin))
    }
    return Object.keys(prices).length > 0 ? prices : null
  }

  /** What the drivers of an option cost: the typical fee × what bookings pay this week, more when the gig has
   * little time to find its driver or is work that drivers ask more for. */
  private cost(request: PriceRequest, option: DeliveryOption, facts: NoteFacts, now: number): number | null {
    const f = features(request, this.setup.map, option)
    const deadline = Math.min(option.deadline, facts.deadline ?? Infinity)
    const lastPickup = deadline - 1.1 * driveMinutes(this.setup.map, request.legs) - 30
    const ready = Math.max(request.legs[0]?.pickup.window.from ?? now, earliestPickup(facts) ?? 0)
    const time = awake(Math.max(now + 15, this.climbFrom(ready, now)), lastPickup - BOOK_AHEAD)
    if (time < this.params.minHours * HOUR) return null // too little time for the climb to find a driver
    let ratio = this.feeRatio + openingFor(time, this.params) - this.params.open + this.params.overhead
    if (f.privatePickup || f.privateDelivery) ratio += this.params.privateAddress
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
      clamp(1 - 1.5 * (this.feeRatio - p.feeRatio), 0.5, 1.25) *
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
    let count = 0
    for (const id of this.delivered.get(dealerId) ?? [])
      count = this.late.has(id) ? Math.floor(count / 2) : Math.min(25, count + 1)
    return this.params.trust * Math.log(1 + count / 100)
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
      const schedule = this.fees(order, typical(previous.stops), now, shown, now, true)
      return [{ stops: previous.stops, audience: previous.audience, schedule }]
    }
    const facts = readNote(request.note, request.arrivedAt)
    const shapes = gigShape(order, legs, facts, this.retryOf(order.id, legs), now, this.context())
    if (shapes.length === 0) throw new Error(`cannot read order ${order.id}`)
    return shapes.map(({ stops, audience }) => {
      const first = stops[0]!
      const ready = first.window?.from ?? order.legs[first.leg]?.pickup.window.from ?? now
      const floor = this.floors.get(order.id) ?? 0
      const schedule = this.fees(order, typical(stops), now, floor, this.climbFrom(ready, now))
      return { stops: this.buffered(order, stops, now), audience, schedule }
    })
  }

  /** The stops with each delivery due `buffer` of its drive before its deadline, where the note gave it no window
   * of its own and a driver who leaves now can still make it. */
  private buffered(order: Order, stops: StopRef[], now: number): StopRef[] {
    if (!(this.params.buffer > 0) || now > order.lastPickupAt) return stops
    return stops.map((stop) => {
      const leg = order.legs[stop.leg]
      if (stop.kind !== 'delivery' || stop.window || !leg) return stop
      const drive = driveMinutes(this.setup.map, [leg])
      const due = leg.delivery.privateAddress ? leg.delivery.window.to : order.deadline
      const to = due - Math.max(20, this.params.buffer * drive)
      const from = leg.delivery.window.from
      return to > from && to > now + drive + 60 ? { ...stop, window: { from, to: Math.round(to) } } : stop
    })
  }

  /** The schedule of a gig from now, never under `floor` cents: the slow climb while there is time to book, the fast
   * one when the last pickup is near, and a calmer one for a car that is late already. */
  private fees(order: Order, typical: number, now: number, floor: number, from: number, warned = false): FeeStep[] {
    const p = this.params
    const shown = floor / typical
    if (now > order.lastPickupAt) return fast(now, typical, Math.max(shown, 1.1), 0.05, 30, p.lateTop)
    const bookBy = order.lastPickupAt - BOOK_AHEAD
    if (warned || awake(Math.max(now, from), bookBy) < SHORT)
      return fast(now, typical, Math.max(shown + 0.05, 1.15), 0.12, 15, Math.max(p.urgentTop, shown + 0.05))
    if (p.stepped) return stepped(now, typical, order.lastPickupAt, p.open, shown, p.jitter, order.id)
    return slow(now, typical, bookBy, p, from, shown, p.urgentTop)
  }

  /** A car ready two or more days from now starts its climb the morning before: most drivers know only their next
   * day, so a climb before that pays for nothing. */
  private climbFrom(ready: number, now: number): number {
    const days = Math.floor(ready / DAY) - Math.floor(now / DAY)
    return days >= 2 ? (Math.floor(ready / DAY) - 1) * DAY + 7 * HOUR : now
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
      const schedule = this.fees(order, this.typicalOf(post.stops, books), books.now, fee, books.now)
      if (schedule.length > 0) actions.push({ type: 'reprice', gigId, schedule })
    }
    if (this.params.chains && this.setup.level >= 3) actions.push(...this.chainActions(books))
    return actions
  }

  // ------------------------------------------------------------------------------------------------ the chains

  /** Takes apart the chains that no driver took in time, and posts the new chains among the open single cars: each
   * car's own gig leaves the app, and one gig carries them all. */
  private chainActions(books: Books): Action[] {
    const p = this.params
    const now = books.now
    const actions: Action[] = []
    for (const [gigId, chain] of this.chains) {
      const live = chain.cars.some((car) => books.gigsOf(car.orderId).includes(gigId))
      if (!live) this.chains.delete(gigId)
      if (!live || books.booked.has(gigId) || now < chain.startBy - p.chainHours * HOUR) continue
      for (const car of chain.cars) this.single.add(car.orderId)
      this.chains.delete(gigId)
      this.chained.undone++
      actions.push({ type: 'withdraw', gigId }) // the harness posts each car again, as a single gig
    }
    const found = findChains(this.openCars(books), this.setup.map, now, p)
    for (const chain of found.filter((c) => c.startBy - now >= (p.chainHours + 3) * HOUR).slice(0, 5)) {
      const stops = chain.cars.flatMap((car) => car.stops)
      this.planned.set(keyOf(stops), chain)
      for (const car of chain.cars) if (car.gigId) actions.push({ type: 'withdraw', gigId: car.gigId })
      actions.push({
        type: 'post',
        stops,
        audience: { experienced: false, manualLicence: chain.cars.some((car) => car.audience.manualLicence) },
        schedule: slow(now, chain.typical, chain.startBy - BOOK_AHEAD, p, now, 0, 1.3),
      })
    }
    return actions
  }

  /** Whether an order's car may join a chain: one car, no setback, no warning, a dealer's yard, any driver, and
   * time left. */
  private chainable(order: Order, books: Books): boolean {
    const leg = order.legs[0]
    if (!leg || order.legs.length !== 1 || order.deliveredAt[0] !== null || books.urgent.has(order.id)) return false
    if (this.single.has(order.id) || this.retries.has(`${order.id} 0`)) return false
    if (leg.car.premium || leg.pickup.privateAddress) return false
    return books.now <= order.lastPickupAt - (this.params.chainHours + 3) * HOUR
  }

  /** A new car that may join a chain waits `holdHours` for a partner, while it has time to spare after the wait. */
  override hold(need: GigNeed, books: Books): boolean {
    const { order } = need
    const p = this.params
    if (!p.chains || !(p.holdHours > 0) || this.setup.level < 3) return false
    if ((need.why !== 'won' && need.why !== 'lost') || this.released.has(order.id)) return false
    if (!this.chainable(order, books) || books.gigsOf(order.id).length > 0) return false
    const since = this.heldSince.get(order.id) ?? books.now
    this.heldSince.set(order.id, since)
    const holds = books.now < since + p.holdHours * HOUR && books.now < order.lastPickupAt - (p.chainHours + 6) * HOUR
    if (!holds) this.released.add(order.id)
    return holds
  }

  /** Our open cars that may join a chain: the cars that wait for a partner, and the single gigs that no driver
   * holds. */
  private openCars(books: Books): Car[] {
    const now = books.now
    const cars: Car[] = []
    for (const order of books.orders.values()) {
      const leg = order.legs[0]
      const request = books.requests.get(order.id)
      const [gigId, ...more] = books.gigsOf(order.id)
      if (!leg || !request || more.length > 0 || !this.chainable(order, books)) continue
      if (!gigId && !(this.heldSince.has(order.id) && !this.released.has(order.id))) continue
      if (gigId && (books.booked.has(gigId) || this.dropped.has(gigId))) continue
      const post = gigId
        ? books.posts.get(gigId)
        : gigShape(order, [0], readNote(request.note, request.arrivedAt), FIRST_TRY, now, this.context())[0]
      if (!post || post.stops.length !== 2 || post.audience.experienced) continue
      const [pickup, delivery] = post.stops as [StopRef, StopRef]
      const drive = driveMinutes(this.setup.map, [leg])
      if (pickup.kind !== 'pickup' || delivery.kind !== 'delivery' || !Number.isFinite(drive)) continue
      cars.push({
        gigId,
        orderId: order.id,
        from: leg.pickup.placeId,
        to: leg.delivery.placeId,
        ready: pickup.window?.from ?? leg.pickup.window.from,
        collectBy: Math.min(pickup.window?.to ?? leg.pickup.window.to, order.lastPickupAt),
        due: delivery.window?.to ?? (leg.delivery.privateAddress ? leg.delivery.window.to : order.deadline),
        drive,
        typical: request.referenceFeeCents,
        pickupHours: leg.pickup.hours,
        deliveryHours: leg.delivery.hours,
        stops: [pickup, delivery],
        audience: post.audience,
      })
    }
    return cars
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
    return this.planned.get(keyOf(stops))?.typical ?? this.singlesOf(stops, books)
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
        const chain = this.chains.get(event.gigId)
        if (chain) {
          this.chained.booked++
          this.chained.bookedCars += chain.cars.length
          this.chained.ratios += event.feeCents / singles
        }
        const ratio = clamp(event.feeCents / singles, 0.3, 2.5)
        this.feeRatio += 0.04 * (ratio - this.feeRatio)
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
        for (const stop of pickups(post?.stops ?? [])) {
          if (this.chains.has(event.gigId)) this.single.add(stop.orderId)
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

  override sent(action: Action, result: ActionResult): void {
    const chain = action.type === 'post' ? this.planned.get(keyOf(action.stops)) : undefined
    if (action.type === 'post' && chain) {
      // A chain that the world refuses leaves its cars to single gigs.
      if (!result.ok) for (const car of chain.cars) this.single.add(car.orderId)
      else {
        this.chains.set(result.id, chain)
        this.chained.posted++
        this.chained.cars += chain.cars.length
      }
    }
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
    const c = this.chained
    return `lean: won ${t.won} of ${t.requests} requests (${share.toFixed(1)}%) at ${multiple.toFixed(2)} × list, ${t.bookings} bookings at ${paid.toFixed(2)} × typical, capacity worth ${this.capacity.toFixed(2)} × typical at the end, ${this.late.size} late of ${this.done} done. Chains: ${c.posted} posted with ${c.cars} cars, ${c.booked} booked with ${c.bookedCars} cars at ${(c.booked > 0 ? c.ratios / c.booked : 0).toFixed(2)} × their cars' typical, ${c.undone} taken apart.`
  }

  private context(tightening = 1): Context {
    return { map: this.setup.map, level: this.setup.level, forecasts: this.forecasts, tightening }
  }
}

export const lean: StrategyKind<LeanParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Lean(setup, params),
}
