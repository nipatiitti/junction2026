/** The chain book: which of our open cars go out together, and what happens to a chain that no driver takes. It
 * holds every piece of chain state, so index.ts only asks it five things: what a request costs as part of a chain
 * (`share`), whether a new car waits for a partner (`hold`), what to post and withdraw now (`actions`), what a gig's
 * fee schedule counts in (`typical`), and what the world answered (`sent`, `booked`, `expired`). */
import type {
  Action,
  ActionResult,
  DeliveryOption,
  Order,
  PriceRequest,
  StopRef,
  WorldMap,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  type Context,
  driveMinutes,
  earliestPickup,
  FIRST_TRY,
  gigShape,
  HOUR,
  type NoteFacts,
  readNote,
} from '../../ops/index.ts'
import type { Books, GigNeed } from '../../strategy.ts'
import { bestChainWith, type Car, type Chain, type ChainParams, findChains } from './chains.ts'
import { awake, BOOK_AHEAD, planBy, slow } from './fees.ts'

export type PlannerParams = ChainParams & {
  chains: boolean
  open: number
  chainHours: number
  holdHours: number
  chainPatience: number
  chainBid: boolean
  /** Plan by the drivers' day (fees.ts, `planBy`): no hold and no chain in the last hours before it. */
  spread: boolean
}

/** What the planner asks of the strategy: the context for reading a gig's shape, and whether a car had a setback or
 * its gig was given back by a driver (such cars stay single). */
export type Host = { context(): Context; troubled(orderId: string, gigId?: string): boolean }

const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')
const keyOf = (stops: readonly StopRef[]): string => stops.map((s) => `${s.orderId}/${s.leg}/${s.kind}`).join(' ')

export class Planner {
  /** The chains decided: the key of their stops -> the chain; and, once posted, gig id -> the chain and its minute. */
  private readonly planned = new Map<string, Chain>()
  private readonly posted = new Map<string, { chain: Chain; at: number }>()
  /** Our car's order id -> the pending request whose bid counts on it as a chain partner. */
  private readonly claims = new Map<string, string>()
  /** The orders that were in a chain no driver took: they stay single. */
  private readonly single = new Set<string>()
  /** Order id -> the minute it first waited for a partner; and the orders whose wait is over. */
  private readonly heldSince = new Map<string, number>()
  private readonly released = new Set<string>()
  private readonly tally = { posted: 0, cars: 0, booked: 0, bookedCars: 0, ratios: 0, undone: 0 }

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

  /** What an option's car costs as part of the best chain with the cars we hold or have open, over its cost alone:
   * the chain's worth to a driver over its cars' typical fees, or 1 when it fits no chain. The partners are claimed
   * for this request until the dealer answers (`release`), so one car of ours does not cheapen several bids. */
  share(request: PriceRequest, option: DeliveryOption, facts: NoteFacts, books: Books): number {
    const leg = request.legs[0]
    if (!this.on || !this.p.chainBid) return 1
    if (!leg || request.legs.length !== 1 || leg.car.premium || leg.pickup.privateAddress) return 1
    const drive = driveMinutes(this.map, [leg])
    const due = Math.min(option.deadline, facts.deadline ?? Infinity)
    const room = (this.p.chainHours + 4) * HOUR
    if (!Number.isFinite(drive) || due - drive < books.now + room) return 1
    const car: Car = {
      gigId: undefined,
      orderId: request.id,
      from: leg.pickup.placeId,
      to: leg.delivery.placeId,
      ready: Math.max(leg.pickup.window.from, earliestPickup(facts) ?? 0),
      collectBy: Math.min(leg.pickup.window.to, due - drive),
      due: leg.delivery.privateAddress ? Math.min(due, leg.delivery.window.to) : due,
      drive,
      typical: request.referenceFeeCents,
      pickupHours: leg.pickup.hours,
      deliveryHours: leg.delivery.hours,
      stops: [],
      audience: { experienced: false, manualLicence: facts.manual },
    }
    const free = this.openCars(books).filter((other) => (this.claims.get(other.orderId) ?? request.id) === request.id)
    const chain = bestChainWith(car, free, this.map, books.now, this.p)
    if (!chain || chain.startBy - books.now < room) return 1
    for (const other of chain.cars) if (other !== car) this.claims.set(other.orderId, request.id)
    return chain.typical / chain.singles
  }

  /** The dealer answered a request: its claims on our cars end. */
  release(requestId: string): void {
    for (const [orderId, by] of this.claims) if (by === requestId) this.claims.delete(orderId)
  }

  /** Takes apart the chains that no driver took in time, and posts the new chains among the open single cars: each
   * car's own gig leaves the app, and one gig carries them all. */
  actions(books: Books): Action[] {
    if (!this.on) return []
    const p = this.p
    const now = books.now
    const actions: Action[] = []
    for (const [gigId, { chain, at }] of this.posted) {
      const live = chain.cars.some((car) => books.gigsOf(car.orderId).includes(gigId))
      if (!live) this.posted.delete(gigId)
      const patient = !(p.chainPatience > 0) || awake(at, now) < p.chainPatience * HOUR // hours drivers could see it
      // With `spread`, its cars go back to single gigs while drivers still plan the day of its last start.
      const planned = !p.spread || awake(now, planBy(now, chain.startBy)) >= 3 * HOUR
      if (!live || books.booked.has(gigId) || (patient && planned && now < chain.startBy - p.chainHours * HOUR))
        continue
      for (const car of chain.cars) this.single.add(car.orderId)
      this.posted.delete(gigId)
      this.tally.undone++
      actions.push({ type: 'withdraw', gigId }) // the harness posts each car again, as a single gig
    }
    const found = findChains(this.openCars(books), this.map, now, p)
    for (const chain of found.filter((c) => c.startBy - now >= (p.chainHours + 3) * HOUR).slice(0, 5)) {
      // The first pickup ends at the chain's last start: a driver who starts later misses a later car's window.
      const stops = chain.cars.flatMap((car) => car.stops)
      const first = stops[0]
      if (p.spread && first && !first.window && chain.startBy > chain.cars[0]!.ready)
        stops[0] = { ...first, window: { from: chain.cars[0]!.ready, to: chain.startBy } }
      this.planned.set(keyOf(stops), chain)
      for (const car of chain.cars) if (car.gigId) actions.push({ type: 'withdraw', gigId: car.gigId })
      actions.push({
        type: 'post',
        stops,
        audience: { experienced: false, manualLicence: chain.cars.some((car) => car.audience.manualLicence) },
        schedule: slow(now, chain.typical, chain.startBy - BOOK_AHEAD, p.open, 1.3),
      })
    }
    return actions
  }

  /** A new car that may join a chain waits `holdHours` for a partner, while it has time to spare after the wait:
   * half of the single gigs book within half an hour, before a partner can arrive. */
  hold(need: GigNeed, books: Books): boolean {
    const { order } = need
    const p = this.p
    if (!this.on || !(p.holdHours > 0)) return false
    if ((need.why !== 'won' && need.why !== 'lost') || this.released.has(order.id)) return false
    if (!this.chainable(order, books) || books.gigsOf(order.id).length > 0) return false
    const since = this.heldSince.get(order.id) ?? books.now
    this.heldSince.set(order.id, since)
    // With `spread`, only while drivers have 5 waking hours left to plan it after the wait.
    const planned = !p.spread || awake(books.now, planBy(books.now, order.lastPickupAt)) >= (p.holdHours + 5) * HOUR
    const holds =
      planned && books.now < since + p.holdHours * HOUR && books.now < order.lastPickupAt - (p.chainHours + 6) * HOUR
    if (!holds) this.released.add(order.id)
    return holds
  }

  /** What a posted chain is worth to its driver, in cents: the unit of its fee schedule. Undefined for other gigs. */
  typical(stops: readonly StopRef[]): number | undefined {
    return this.planned.get(keyOf(stops))?.typical
  }

  /** The world's answer to a post: a chain that it refuses leaves its cars to single gigs. */
  sent(action: Action, result: ActionResult, books: Books): void {
    const chain = action.type === 'post' ? this.planned.get(keyOf(action.stops)) : undefined
    if (!chain) return
    if (!result.ok) for (const car of chain.cars) this.single.add(car.orderId)
    else {
      this.posted.set(result.id, { chain, at: books.now })
      this.tally.posted++
      this.tally.cars += chain.cars.length
    }
  }

  /** A driver booked a gig at `ratio` × its cars' typical fees. */
  booked(gigId: string, ratio: number): void {
    const chain = this.posted.get(gigId)?.chain
    if (!chain) return
    this.tally.booked++
    this.tally.bookedCars += chain.cars.length
    this.tally.ratios += ratio
  }

  /** A gig's window ended without a driver: a chain's cars stay single from here. */
  expired(gigId: string, stops: readonly StopRef[]): void {
    if (this.posted.has(gigId)) for (const stop of pickups(stops)) this.single.add(stop.orderId)
  }

  summary(): string {
    const c = this.tally
    const ratio = (c.booked > 0 ? c.ratios / c.booked : 0).toFixed(2)
    return `Chains: ${c.posted} posted with ${c.cars} cars, ${c.booked} booked with ${c.bookedCars} cars at ${ratio} × their cars' typical, ${c.undone} taken apart.`
  }

  /** Whether an order's car may join a chain: one car, no setback, no warning, a dealer's yard, and time left. */
  private chainable(order: Order, books: Books): boolean {
    const leg = order.legs[0]
    if (!leg || order.legs.length !== 1 || order.deliveredAt[0] !== null || books.urgent.has(order.id)) return false
    if (this.single.has(order.id) || this.host.troubled(order.id)) return false
    if (leg.car.premium || leg.pickup.privateAddress) return false
    return books.now <= order.lastPickupAt - (this.p.chainHours + 3) * HOUR
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
      if (!leg || !request || more.length > 0 || !this.chainable(order, books)) continue
      if (!gigId && !(this.heldSince.has(order.id) && !this.released.has(order.id))) continue
      if (gigId && (books.booked.has(gigId) || this.host.troubled(order.id, gigId))) continue
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
}
