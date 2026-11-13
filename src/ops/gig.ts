/** The shape of a gig for an order's cars: its stops with their windows and flags, and who may take it, under
 * every handling rule of RULES.md that costs a fine or a failed visit. Also how to post a car again after a
 * setback, and when to post a car that is ready days later. Ported from dispatch.py (`stops_for`, `audience_for`,
 * `retry_from`, `Desk.post`, `Desk.retry`, `Desk.repost`). */
import type {
  Audience,
  Car,
  Order,
  PriceRequest,
  StopRef,
  TimeWindow,
  VisitFailedEvent,
} from '../../vendor/spread-typescript/types.ts'
import { DAY, dayOf, HOUR, isWeekend } from './calendar.ts'
import { type Context, driveMinutes, minutes } from './map.ts'
import { earliestPickup, NO_FACTS, type NoteFacts } from './note.ts'
import { deliveryWindow, pickupWindow, snowAt } from './windows.ts'

/** A gig with more than one car may plan at most this much driving (RULES.md, rule 2). */
export const MAX_SHARED_DRIVE = 12 * HOUR
/** An electric car under this charge gets a charging stop (rule 3). */
export const LOW_CHARGE = 30
/** After a visit that found the car not ready or the site closed, the next pickup waits at least this long. */
export const RETRY_WAIT = 2 * HOUR
/** A car ready two or more days later is posted at this hour of the business day before (issue #106). */
export const EARLY_POST = 8 * HOUR

/** What the setbacks of a car have taught: how to post it again. */
export type Retry = {
  pickupFrom: number // no pickup before this minute: the car was not ready, or the site closed
  manualLicence: boolean // a visit failed on the licence
  plates: boolean // a visit failed for want of plates
  late: boolean // a window passed with no driver: keep only the pickup window the car needs, so it can still go
}

export const FIRST_TRY: Retry = Object.freeze({ pickupFrom: 0, manualLicence: false, plates: false, late: false })

/** A gig to post, but its fee schedule. */
export type GigShape = { stops: StopRef[]; audience: Audience }

/** What can set a car back: the reason of a `visit_failed`, or a `gig_expired`. */
export type Setback = VisitFailedEvent['reason'] | 'expired'

/** The gigs that carry the order's cars `legs`: one, or one for each car of a trade-in over the 12-hour limit.
 * Each car has a pickup and a delivery, in order, so a trade-in's old car is collected right after the new car is
 * delivered. A stop has its own window only when the note or a setback makes it narrower, and none that has ended
 * by `now`, so the world never refuses the post. A delivered car, or a leg the order does not have, is left out;
 * an order it cannot read gives no gig. */
export function gigShape(
  order: Order,
  legs: readonly number[],
  facts: NoteFacts,
  retry: Retry,
  now: number,
  context: Context,
): GigShape[] {
  try {
    return shapes(order, legs, facts, retry, now, context)
  } catch {
    return []
  }
}

function shapes(
  order: Order,
  legs: readonly number[],
  facts: NoteFacts,
  retry: Retry,
  now: number,
  context: Context,
): GigShape[] {
  const cars = [...new Set(legs)]
    .filter((leg) => order.legs[leg] && order.deliveredAt[leg] == null)
    .sort((a, b) => a - b)
  const shape = (cars: number[]): GigShape => ({
    stops: withoutWindows(
      cars.flatMap((leg) => stopsFor(order, leg, leg === 0 ? facts : NO_FACTS, retry, now, context)),
      now,
    ),
    audience: audienceFor(order, cars, facts, retry),
  })
  if (cars.length === 0) return []
  const together = driveMinutes(
    context.map,
    cars.map((leg) => order.legs[leg]),
  )
  return cars.length > 1 && together > MAX_SHARED_DRIVE ? cars.map((leg) => shape([leg])) : [shape(cars)]
}

/** A pickup and a delivery for one car. The note speaks of the first car only (strategies/notes/README.md). */
function stopsFor(order: Order, leg: number, noted: NoteFacts, retry: Retry, now: number, context: Context): StopRef[] {
  const { car, pickup, delivery } = order.legs[leg]
  const snow = noted.summerTyres ? snowAt(context.forecasts ?? [], [pickup.placeId, delivery.placeId]) : []
  let pickupAt = pickupWindow(pickup.window, pickup.hours, noted, now, retry.pickupFrom, snow)
  // A private seller's slot never extends: a window outside it would be refused, so the slot itself applies.
  if (pickup.privateAddress && pickupAt)
    pickupAt = pickupAt.from > pickup.window.to ? null : { ...pickupAt, to: Math.min(pickupAt.to, pickup.window.to) }
  const base: TimeWindow = { from: delivery.window.from, to: Math.max(delivery.window.from, order.deadline) }
  const noteDelivery = deliveryWindow(base, delivery.hours, noted)
  // When a driver who collects the car as early as the window allows cannot meet the note, the car is late whatever:
  // deliver it when the driver can.
  const arrival =
    Math.max(now, pickupAt?.from ?? pickup.window.from) + minutes(context.map, pickup.placeId, delivery.placeId)
  const deliverBy = arrival > noteDelivery.to ? base : noteDelivery
  const first: StopRef = {
    orderId: order.id,
    leg,
    kind: 'pickup',
    withPlates: retry.plates || noted.plates,
    withCharging: lowBattery(car),
    ...(pickupAt && { window: pickupAt }),
  }
  const second: StopRef = { orderId: order.id, leg, kind: 'delivery' }
  const narrower = deliverBy.from > base.from || deliverBy.to < base.to
  // After a window passed, the delivery runs to the end of the world, so the car can still arrive, late.
  return [first, narrower && !retry.late ? { ...second, window: deliverBy } : second]
}

/** Who may take the cars: a premium car needs an experienced driver (€150 a car), and a manual car, by the note
 * or a failed visit, a manual licence. */
function audienceFor(order: Order, legs: readonly number[], facts: NoteFacts, retry: Retry): Audience {
  return {
    experienced: legs.some((leg) => order.legs[leg]?.car.premium === true),
    manualLicence: retry.manualLicence || (legs.includes(0) && facts.manual),
  }
}

/** An electric car below 30% charge: a charging stop on the way. */
export const lowBattery = (car: Car): boolean =>
  car.electric && car.chargePercent !== null && car.chargePercent < LOW_CHARGE

/** Leaves out the stop windows that end before `before`, so the world's window applies: once the order's window
 * has ended, it runs to the end of the world. */
export const withoutWindows = (stops: readonly StopRef[], before: number): StopRef[] =>
  stops.map(({ window, ...stop }) => (window && window.to >= before ? { ...stop, window } : stop))

/** The order's cars not delivered yet. */
export const undelivered = (order: Order): number[] =>
  order.legs.map((_, leg) => leg).filter((leg) => order.deliveredAt[leg] == null)

/** How to post a car again after a setback, from what earlier setbacks taught (`before`):
 * - `not_ready`, `closed`: the pickup waits two hours, or, when the dealer moved the deadline for a car that is
 *   late, until the car should be ready by the same delay;
 * - `licence`: a manual licence; `no_plates`: fetch plates;
 * - `expired`: a window passed with no driver, so the car goes without the windows that it no longer needs.
 * A reason it does not know changes nothing. */
export function retryAfter(
  setback: Setback,
  order: Order,
  request: PriceRequest | undefined,
  leg: number,
  now: number,
  before: Retry = FIRST_TRY,
): Retry {
  switch (setback) {
    case 'not_ready':
    case 'closed':
      return { ...before, pickupFrom: Math.max(before.pickupFrom, retryFrom(order, request, leg, now)) }
    case 'licence':
      return { ...before, manualLicence: true }
    case 'no_plates':
      return { ...before, plates: true }
    case 'expired':
      return { ...before, late: true }
    default:
      return before
  }
}

function retryFrom(order: Order, request: PriceRequest | undefined, leg: number, now: number): number {
  try {
    const promised = request?.options.find((option) => option.kind === order.option)?.deadline ?? order.deadline
    const delay = Math.max(0, order.deadline - promised)
    const later = (order.legs[leg]?.pickup.window.from ?? now) + delay
    return Number.isFinite(later) ? Math.max(now + RETRY_WAIT, later) : now + RETRY_WAIT
  } catch {
    return now + RETRY_WAIT
  }
}

/** The minute to post an order's cars: now, or, for a car ready two or more days later, 08:00 on the business day
 * before, so the post reaches drivers when they plan that day (issue #106; not benched yet). Never later than a
 * day before the last pickup, and now for an order it cannot read. */
export function postAt(order: Order, now: number, facts: NoteFacts = NO_FACTS): number {
  try {
    const leg = undelivered(order)[0] ?? 0
    const ready = Math.max(order.legs[leg].pickup.window.from, leg === 0 ? (earliestPickup(facts) ?? 0) : 0)
    if (!(dayOf(ready) - dayOf(now) >= 2)) return now
    let day = dayOf(ready) - 1
    while (isWeekend(day)) day--
    const at = Math.min(day * DAY + EARLY_POST, order.lastPickupAt - DAY)
    return Number.isFinite(at) ? Math.max(now, at) : now
  } catch {
    return now
  }
}
