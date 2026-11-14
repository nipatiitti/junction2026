/** The chain book: which of our open cars go out together, and what happens to a chain that no driver takes. It
 * holds every piece of chain state, so index.ts only asks it four things: whether a new car waits for a partner
 * (`hold`), what to post and withdraw now (`actions`), what a gig's fee schedule counts in (`typical`), and what the
 * world answered (`sent`, `booked`, `expired`). */
import type { Action, ActionResult, Order, StopRef, WorldMap } from '../../../vendor/spread-typescript/spread.ts'
import { type Context, DAY, driveMinutes, FIRST_TRY, gigShape, HOUR, readNote } from '../../ops/index.ts'
import type { Books, GigNeed } from '../../strategy.ts'
import { type Car, type Chain, type ChainModel, type ChainParams, draw, findChains, spreadLevel } from './chains.ts'
import { awake, BOOK_AHEAD, planBy, slow } from './fees.ts'

export type PlannerParams = ChainParams & {
  chains: boolean
  open: number
  holdHours: number
  chainPatience: number
  chainTries: number
  chainOpen: number
  chainSpread: number
  chainAlone: number
  chainOffers: number
  chainOfferSpread: number
  pickLead: number
  chainLast: number
}

/** A chain books 69% of the time when it is posted from Monday to Thursday, has `pickLead` hours to its first
 * last pickup and holds a car that no driver has seen; 23% of the time otherwise (28 server weeks, 2,430 chains).
 * A chain that fails costs its cars 1.06 × typical and their one notification, so only the first kind is posted,
 * and a car waits for a partner only while such a chain is still possible. Requests end on Friday evening, so
 * from Friday on no new car comes. */
const FRIDAY = 4
/** Whether a chain whose first last pickup is `collectBy` is of that kind when posted at the minute `at`. */
const postable = (collectBy: number, at: number, pickLead: number): boolean =>
  Math.floor(at / DAY) < FRIDAY && collectBy - at >= pickLead * HOUR
/** Direct offers of an open chain (the rules: an offer is open 10 minutes, three open per gig, three per driver
 * per day, none read at night). A driver gets one `OFFER_AFTER` minutes after their view, and only once per chain. */
const [OFFER_OPEN, OFFERS_PER_GIG, OFFERS_PER_DAY, OFFER_AFTER] = [10, 3, 3, 3]
const [OFFER_FROM, OFFER_TO] = [7 * HOUR, 21 * HOUR]
/** The offer levels that `chainOfferSpread` draws from, × the fee that the app shows. */
const OFFER_LEVELS = [1, 1.15, 1.3]
/** The most chains posted in one tick. */
const MAX_POSTS = 5

/** What the planner asks of the strategy: the context for reading a gig's shape, and whether a car had a setback or
 * not (such cars stay single). */
export type Host = {
  context(): Context
  troubled(orderId: string, gigId?: string): boolean
  homes: ReadonlyMap<string, number> // place id -> the drivers who live there
  load(): number // the bookings so far per driver
  model: ChainModel | undefined // chains.ts: prices and ranks the chains by their chance to book
}

/** A chain in the app, as its post action and the world's answer tell it. */
type Posted = { orders: string[]; startBy: number; typical: number; at: number }

const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')
const keyOf = (stops: readonly StopRef[]): string => stops.map((s) => `${s.orderId}/${s.leg}/${s.kind}`).join(' ')
const offerKey = (gigId: string, driverId: string): string => `${gigId}\n${driverId}`

export class Planner {
  /** The chains in the app: gig id -> its cars' orders, its last start, its fee unit and the minute of its post.
   * All of it is read from the post action and its answer (`sent`), so a rebuild from the journal has it too. */
  private readonly posted = new Map<string, Posted>()
  /** The key of a posted chain's stops -> what the chain is worth to its driver, in cents. */
  private readonly units = new Map<string, number>()
  /** Order id -> the chains it was in that no driver took: after `chainTries` of them it stays single. */
  private readonly fails = new Map<string, number>()
  /** Order id -> the minute it was won: its wait for a partner counts from there. */
  private readonly wonAt = new Map<string, number>()
  /** Order id -> the first view of any of its gigs: the chain model's `fresh` is no view before the chain's post. */
  private readonly seenAt = new Map<string, number>()
  /** Gig id of a posted chain -> the drivers who viewed it and the minute, and the drivers we offered it to. */
  private readonly views = new Map<string, Map<string, number>>()
  /** Gig and driver -> the minute their unanswered offer was planned; only live actions need this pending state. */
  private readonly pendingOffers = new Map<string, number>()
  private readonly offered = new Map<string, Map<string, number>>()
  /** Driver id and day -> the offers we sent them that day. */
  private readonly asked = new Map<string, number>()
  private readonly tally = { posted: 0, cars: 0, booked: 0, bookedCars: 0, ratios: 0, undone: 0, offers: 0, taken: 0 }

  private readonly p: PlannerParams
  private readonly map: WorldMap
  private readonly on: boolean
  private readonly host: Host

  constructor(p: PlannerParams, map: WorldMap, on: boolean, host: Host) {
    this.p = p
    this.map = map
    this.on = on
    this.host = host
  }

  /** Takes apart the chains that no driver took in time, and posts the new chains among the open single cars: each
   * car's own gig leaves the app, and one gig carries them all. */
  actions(books: Books): Action[] {
    if (!this.on) return []
    const p = this.p
    const now = books.now
    const actions: Action[] = []
    for (const [gigId, { orders, startBy, at }] of this.posted) {
      const live = orders.some((orderId) => books.gigsOf(orderId).includes(gigId))
      if (!live) this.posted.delete(gigId)
      const patient = !(p.chainPatience > 0) || awake(at, now) < p.chainPatience * HOUR // hours drivers could see it
      if (!live || books.booked.has(gigId) || (patient && this.mayBeOpen(startBy, now))) continue
      // The harness posts each car again, as a single gig. `sent` marks the cars once the world has taken the gig out.
      actions.push({ type: 'withdraw', gigId })
    }
    const leaving = new Set(actions.map((action) => (action.type === 'withdraw' ? action.gigId : '')))
    actions.push(...this.offers(books, leaving))
    // A chain needs a car that no driver has seen, so without one there is nothing to search.
    const cars = this.openCars(books).filter((car) => postable(car.collectBy, now, p.pickLead))
    if (!cars.some((car) => !car.gigId)) return actions
    const worth = (c: Chain) => this.likely(c, now) && this.mayBeOpen(c.startBy, now, p.chainPatience)
    for (const chain of findChains(cars, this.map, now, p, worth, this.scene()).slice(0, MAX_POSTS)) {
      // The first pickup ends at the chain's last start: a driver who starts later misses a later car's window.
      // `sent` reads the last start back from this window.
      const stops = chain.cars.flatMap((car) => car.stops)
      const [first, lead] = [stops[0], chain.cars[0]]
      if (first && lead && chain.startBy > lead.ready)
        stops[0] = { ...first, window: { from: lead.ready, to: chain.startBy } }
      for (const car of chain.cars) if (car.gigId) actions.push({ type: 'withdraw', gigId: car.gigId })
      actions.push({
        type: 'post',
        stops,
        audience: { experienced: false, manualLicence: chain.cars.some((car) => car.audience.manualLicence) },
        schedule: slow(now, chain.typical * this.level(chain), chain.startBy - BOOK_AHEAD, p.open),
      })
    }
    return actions
  }

  /** Direct offers of the open chains to drivers who viewed them and did not book, at `chainOffers` × the fee in
   * the app: a driver who holds out for more gets it, and the app's fee stays for the others. With
   * `chainOfferSpread` each chain draws its offer level from `OFFER_LEVELS`, which measures what such offers do. */
  private offers(books: Books, leaving: ReadonlySet<string>): Action[] {
    const p = this.p
    const now = books.now
    const actions: Action[] = []
    if (!(p.chainOffers > 0 || p.chainOfferSpread > 0) || now % DAY < OFFER_FROM || now % DAY >= OFFER_TO)
      return actions
    for (const [gigId, chain] of this.posted) {
      const post = books.posts.get(gigId)
      if (
        !post ||
        leaving.has(gigId) ||
        books.booked.has(gigId) ||
        !chain.orders.some((id) => books.gigsOf(id).includes(gigId))
      )
        continue
      const sent = this.offered.get(gigId) ?? new Map<string, number>()
      let free = OFFERS_PER_GIG - [...sent.values()].filter((at) => now < at + OFFER_OPEN).length
      const drawn = OFFER_LEVELS[Math.floor(draw(`${chain.orders.join(' ')} offer`) * OFFER_LEVELS.length)] ?? 1
      const level = p.chainOfferSpread > 0 ? drawn : p.chainOffers
      const shown = post.schedule.reduce(
        (fee, step) => (step.at <= now ? step.feeCents : fee),
        post.schedule[0]?.feeCents ?? 0,
      )
      for (const [driverId, at] of this.views.get(gigId) ?? []) {
        if (free <= 0) break
        const day = `${driverId} ${Math.floor(now / DAY)}`
        if (sent.has(driverId) || now < at + OFFER_AFTER || (this.asked.get(day) ?? 0) >= OFFERS_PER_DAY) continue
        actions.push({ type: 'offer', gigId, driverId, feeCents: Math.round(shown * level) })
        this.pendingOffers.set(offerKey(gigId, driverId), now)
        this.asked.set(day, (this.asked.get(day) ?? 0) + 1)
        sent.set(driverId, now)
        free--
      }
      this.offered.set(gigId, sent)
    }
    return actions
  }

  /** A driver viewed a gig. Every order's first view is kept for the chain model; a posted chain's viewers can also
   * get direct offers. */
  viewed(gigId: string, driverId: string, at: number, books: Books): void {
    for (const stop of pickups(books.posts.get(gigId)?.stops ?? [])) {
      const previous = this.seenAt.get(stop.orderId)
      if (previous === undefined || at < previous) this.seenAt.set(stop.orderId, at)
    }
    if (!this.posted.has(gigId)) return
    const seen = this.views.get(gigId) ?? new Map<string, number>()
    if (!seen.has(driverId)) seen.set(driverId, at)
    this.views.set(gigId, seen)
  }

  /** A driver took our direct offer of a chain. */
  took(gigId: string): void {
    if (this.posted.has(gigId)) this.tally.taken++
  }

  /** What a chain's fees are × its worth to a driver: `chainOpen`, and with `chainSpread` one of `SPREAD_LEVELS`
   * drawn from its cars' orders, which measures how the fee moves the chance to book. */
  private level(chain: Chain): number {
    const key = chain.cars.map((car) => car.orderId).join(' ')
    return this.p.chainOpen * spreadLevel(key, this.p.chainSpread) * chain.level
  }

  private scene() {
    const { homes, model } = this.host
    return { homes, load: this.host.load(), open: this.p.open, alone: this.p.chainAlone, model }
  }

  /** Whether a chain is of the kind that books (see `postable`). */
  private likely(chain: Chain, now: number): boolean {
    const collectBy = Math.min(...chain.cars.map((car) => car.collectBy))
    return postable(collectBy, now, this.p.pickLead) && chain.cars.some((car) => !car.gigId)
  }

  /** Whether a chain with the last start `startBy` may be in the app at `now`, and for `more` waking hours after:
   * while drivers have `chainLast` waking hours left to plan the day of its last start (fees.ts, `planBy`). After
   * that its cars go back
   * to single gigs, which need that time for their raises. The same rule posts a chain, withdraws it, and decides
   * whether a car waits for one, so no chain is posted that the next tick takes apart. */
  private mayBeOpen(startBy: number, now: number, more = 0): boolean {
    return awake(now, planBy(now, startBy)) >= (this.p.chainLast + more) * HOUR
  }

  /** A new car that may join a chain waits `holdHours` for a partner, while it has time to spare after the wait:
   * half of the single gigs book within half an hour, before a partner can arrive. */
  hold(need: GigNeed, books: Books): boolean {
    if (need.why !== 'won' && need.why !== 'lost') return false
    return this.waits(need.order, books)
  }

  /** Whether a car without a gig waits for a partner now. It depends only on the order, the minute it was won and
   * the clock, so a strategy rebuilt mid-week decides as the one before it. */
  private waits(order: Order, books: Books): boolean {
    const p = this.p
    if (!this.on || !(p.holdHours > 0)) return false
    if (!this.chainable(order, books) || books.gigsOf(order.id).length > 0) return false
    const since = this.wonAt.get(order.id) ?? books.now
    if (books.now >= since + p.holdHours * HOUR) return false
    // Only while a chain with this car could still be posted, and stay its `chainPatience`, after the wait.
    const collectBy = Math.min(order.legs[0]?.pickup.window.to ?? Infinity, order.lastPickupAt)
    return (
      postable(collectBy, books.now + p.holdHours * HOUR, p.pickLead) &&
      this.mayBeOpen(order.lastPickupAt, books.now, p.holdHours + p.chainPatience)
    )
  }

  /** An order was won at the minute `at`. */
  won(orderId: string, at: number): void {
    this.wonAt.set(orderId, at)
  }

  /** What a posted chain is worth to its driver, in cents: the unit of its fee schedule. Undefined for other gigs. */
  typical(stops: readonly StopRef[]): number | undefined {
    return this.units.get(keyOf(stops))
  }

  /** The world's answer to a chain's post, offer or withdrawal. A chain that it refuses, or that we took out, counts
   * as a failed try for each of its cars. Successful offers are also rebuilt from the journal; offers planned in this
   * process already have their limits recorded. */
  sent(action: Action, result: ActionResult, books: Books): void {
    if (action.type === 'offer') {
      const { gigId, driverId } = action
      const key = offerKey(gigId, driverId)
      const plannedAt = this.pendingOffers.get(key)
      const sent = this.offered.get(gigId)
      const known = sent?.has(driverId) ?? false
      const day = (at: number) => `${driverId} ${Math.floor(at / DAY)}`
      const reserve = (at: number, amount: number) => {
        const bucket = day(at)
        this.asked.set(bucket, Math.max(0, (this.asked.get(bucket) ?? 0) + amount))
      }
      if (!result.ok) {
        // Undo the exact planning-day reservation. A replayed refusal has no live reservation to undo.
        if (plannedAt !== undefined) {
          this.pendingOffers.delete(key)
          sent?.delete(driverId)
          reserve(plannedAt, -1)
        }
        return
      }
      this.tally.offers++
      // Both a delayed live answer and its journal replay use the answer's minute. The day can differ from planning.
      if (plannedAt !== undefined) {
        this.pendingOffers.delete(key)
        reserve(plannedAt, -1)
        reserve(books.now, 1)
      }
      if (known) {
        sent?.set(driverId, books.now)
        return
      }
      const restored = sent ?? new Map<string, number>()
      restored.set(driverId, books.now)
      this.offered.set(gigId, restored)
      if (plannedAt === undefined) reserve(books.now, 1)
      return
    }
    if (action.type === 'withdraw') {
      const chain = this.posted.get(action.gigId)
      if (!chain || !result.ok) return
      for (const orderId of chain.orders) this.failed(orderId)
      this.posted.delete(action.gigId)
      this.tally.undone++
      return
    }
    if (action.type !== 'post') return
    const orders = [...new Set(pickups(action.stops).map((stop) => stop.orderId))]
    if (orders.length < 2) return
    if (!result.ok) {
      for (const orderId of orders) this.failed(orderId)
      return
    }
    // The opening fee is `open` × the chain's worth, and the first pickup's window ends at its last start.
    const typical = (action.schedule[0]?.feeCents ?? 0) / this.p.open
    const lastPickups = orders.map((orderId) => books.orders.get(orderId)?.lastPickupAt ?? Infinity)
    const startBy = action.stops[0]?.window?.to ?? Math.min(...lastPickups)
    this.posted.set(result.id, { orders, startBy, typical, at: books.now })
    this.units.set(keyOf(action.stops), typical)
    this.tally.posted++
    this.tally.cars += orders.length
  }

  /** A driver booked a gig at `ratio` × its cars' typical fees. */
  booked(gigId: string, ratio: number): void {
    const chain = this.posted.get(gigId)
    if (!chain) return
    this.tally.booked++
    this.tally.bookedCars += chain.orders.length
    this.tally.ratios += ratio
  }

  /** A gig's window ended without a driver: a chain's cars stay single from here. */
  expired(gigId: string, stops: readonly StopRef[]): void {
    if (this.posted.has(gigId)) for (const stop of pickups(stops)) this.failed(stop.orderId)
  }

  /** A chain with this order's car found no driver. */
  private failed(orderId: string): void {
    this.fails.set(orderId, (this.fails.get(orderId) ?? 0) + 1)
  }

  summary(): string {
    const c = this.tally
    const ratio = (c.booked > 0 ? c.ratios / c.booked : 0).toFixed(2)
    return `Chains: ${c.posted} posted with ${c.cars} cars, ${c.booked} booked with ${c.bookedCars} cars at ${ratio} × their cars' typical, ${c.undone} taken apart${c.offers > 0 ? `, ${c.offers} offers with ${c.taken} taken` : ''}.`
  }

  /** Whether an order's car may join a chain: one car, no setback, no warning, and a dealer's yard. */
  private chainable(order: Order, books: Books, gigId?: string): boolean {
    const leg = order.legs[0]
    if (!leg || order.legs.length !== 1 || order.deliveredAt[0] !== null || books.urgent.has(order.id)) return false
    if ((this.fails.get(order.id) ?? 0) >= this.p.chainTries || this.host.troubled(order.id, gigId)) return false
    return !leg.car.premium && !leg.pickup.privateAddress
  }

  /** Our open cars that may join a chain: the cars that wait for a partner, and the single gigs that any driver may
   * take and none holds. */
  private openCars(books: Books): Car[] {
    const now = books.now
    const cars: Car[] = []
    for (const order of books.orders.values()) {
      const leg = order.legs[0]
      const request = books.requests.get(order.id)
      const [gigId, ...more] = books.gigsOf(order.id)
      if (!leg || !request || more.length > 0 || !this.chainable(order, books, gigId)) continue
      if (!gigId && !this.waits(order, books)) continue
      if (gigId && books.booked.has(gigId)) continue
      const post = gigId
        ? books.posts.get(gigId)
        : gigShape(order, [0], readNote(request.note, request.arrivedAt), FIRST_TRY, now, this.host.context())[0]
      if (!post || post.stops.length !== 2 || post.audience.experienced) continue
      const [pickup, delivery] = post.stops as [StopRef, StopRef]
      const drive = driveMinutes(this.map, [leg])
      if (pickup.kind !== 'pickup' || delivery.kind !== 'delivery' || !Number.isFinite(drive)) continue
      cars.push({
        gigId,
        orderId: order.id,
        fresh: (this.seenAt.get(order.id) ?? now) >= now,
        from: leg.pickup.placeId,
        to: leg.delivery.placeId,
        ready: pickup.window?.from ?? leg.pickup.window.from,
        collectBy: Math.min(pickup.window?.to ?? leg.pickup.window.to, order.lastPickupAt),
        due: delivery.window?.to ?? (leg.delivery.privateAddress ? leg.delivery.window.to : order.deadline),
        drive,
        typical: request.referenceFeeCents,
        pickupHours: leg.pickup.hours,
        deliveryHours: leg.delivery.hours,
        deliveryFrom: leg.delivery.privateAddress ? leg.delivery.window.from : 0,
        stops: [pickup, delivery],
        audience: post.audience,
      })
    }
    return cars
  }
}
