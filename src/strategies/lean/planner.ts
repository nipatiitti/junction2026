/** The chain book: which of our open cars go out together, and what happens to a chain that no driver takes. It
 * holds every piece of chain state, so index.ts only asks it four things: whether a new car waits for a partner
 * (`hold`), what to post and withdraw now (`actions`), what a gig's fee schedule counts in (`typical`), and what the
 * world answered (`sent`, `booked`, `expired`). */
import type { Action, ActionResult, Order, StopRef, WorldMap } from '../../../vendor/spread-typescript/spread.ts'
import { type Context, DAY, driveMinutes, FIRST_TRY, gigShape, HOUR, readNote } from '../../ops/index.ts'
import type { Books, GigNeed } from '../../strategy.ts'
import { type Car, type Chain, type ChainParams, findChains } from './chains.ts'
import { awake, BOOK_AHEAD, planBy, slow } from './fees.ts'

export type PlannerParams = ChainParams & {
  chains: boolean
  open: number
  chainHours: number
  holdHours: number
  chainPatience: number
  /** Plan by the drivers' day (fees.ts, `planBy`): no hold and no chain in the last hours before it. */
  spread: boolean
  chainLast: number
}

/** A chain books 69% of the time when it is posted from Monday to Thursday, has `PICK_LEAD` hours to its first
 * last pickup and holds a car that no driver has seen; 23% of the time otherwise (28 server weeks, 2,430 chains).
 * A chain that fails costs its cars 1.06 × typical and their one notification, so only the first kind is posted,
 * and a car waits for a partner only while such a chain is still possible. */
const PICK_LEAD = 20 * HOUR
const FRIDAY = 4

/** What the planner asks of the strategy: the context for reading a gig's shape, and whether a car had a setback or
 * its gig was given back by a driver (such cars stay single). */
export type Host = { context(): Context; troubled(orderId: string, gigId?: string): boolean }

const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')
const keyOf = (stops: readonly StopRef[]): string => stops.map((s) => `${s.orderId}/${s.leg}/${s.kind}`).join(' ')

export class Planner {
  /** The chains decided: the key of their stops -> the chain; and, once posted, gig id -> the chain and its minute. */
  private readonly planned = new Map<string, Chain>()
  private readonly posted = new Map<string, { chain: Chain; at: number }>()
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
      const planned = !p.spread || awake(now, planBy(now, chain.startBy)) >= p.chainLast * HOUR
      if (!live || books.booked.has(gigId) || (patient && planned && now < chain.startBy - p.chainHours * HOUR))
        continue
      for (const car of chain.cars) this.single.add(car.orderId)
      this.posted.delete(gigId)
      this.tally.undone++
      actions.push({ type: 'withdraw', gigId }) // the harness posts each car again, as a single gig
    }
    const found = findChains(this.openCars(books), this.map, now, p)
    const timely = found.filter((c) => c.startBy - now >= (p.chainHours + 3) * HOUR)
    for (const chain of timely.filter((c) => this.likely(c, now)).slice(0, 5)) {
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

  /** Whether a chain is of the kind that books (see `PICK_LEAD`). */
  private likely(chain: Chain, now: number): boolean {
    if (Math.floor(now / DAY) >= FRIDAY) return false
    if (Math.min(...chain.cars.map((car) => car.collectBy)) - now < PICK_LEAD) return false
    return chain.cars.some((car) => !car.gigId)
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
    // Only while a chain with this car could still be posted after the wait.
    const pickable =
      Math.floor(books.now / DAY) < FRIDAY && books.now < order.lastPickupAt - PICK_LEAD - p.holdHours * HOUR
    const holds = planned && pickable && books.now < since + p.holdHours * HOUR
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
