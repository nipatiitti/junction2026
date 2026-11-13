/** The starter's gigs: the note windows, a retry that waits for the car, and rising fees that turn steep at the
 * deadline warning. The harness also posts these when a strategy fails. */
import type {
  FeeStep,
  Note,
  Order,
  PostAction,
  PriceRequest,
  StopRef,
  TimeWindow,
} from '../../../vendor/spread-typescript/spread.ts'
import type { Books, GigNeed, GigPlan } from '../../strategy.ts'
import { HOUR } from '../../time.ts'
import { windowFromNote } from './notes.ts'

/** How to post a leg again after a failed visit. */
type Retry = { pickupFrom: number; manualLicence: boolean; plates: boolean }
const FIRST_TRY: Retry = { pickupFrom: 0, manualLicence: false, plates: false }

export function starterGig(need: GigNeed, books: Books, level: number): GigPlan {
  const { order, previous } = need
  const request = books.requests.get(order.id)!
  const fees = (cars: number) => feesFor(order, request, cars, books, level)
  // A repost: one of its windows has ended, perhaps at a site's closing time before the window's own end, so it goes
  // without its own stop windows. An urgent reprice keeps the gig and takes the steep fees.
  if (previous) {
    const stops = need.why === 'repost' ? withoutWindows(previous.stops, Infinity) : previous.stops
    return { stops, audience: previous.audience, schedule: fees(pickups(previous)) }
  }
  const retry = need.failed ? retryAfter(need.failed, order, request, need.legs[0]!, books.now) : FIRST_TRY
  // A premium car needs an experienced driver: the fine is €150 a car.
  const audience = { experienced: order.legs.some((leg) => leg.car.premium), manualLicence: retry.manualLicence }
  const stops = withoutWindows(stopsFor(order, need.legs, request.note, retry), books.now)
  return { stops, audience, schedule: fees(need.legs.length) }
}

/** The fees for some of the order's cars from now: rising, or steep once its deadline warning has come. */
function feesFor(order: Order, request: PriceRequest, cars: number, books: Books, level: number): FeeStep[] {
  const fee = (request.referenceFeeCents * cars) / order.legs.length
  return books.urgent.has(order.id) ? steep(books.now, fee, level) : rising(books.now, fee, level)
}

function retryAfter(reason: GigNeed['failed'], order: Order, request: PriceRequest, leg: number, now: number): Retry {
  const carNotThere = reason === 'not_ready' || reason === 'closed'
  const pickupFrom = carNotThere ? retryFrom(order, request, leg, now) : 0
  return { pickupFrom, manualLicence: reason === 'licence', plates: reason === 'no_plates' }
}

/** When to try a car again after a visit found it not ready or the site closed: two hours on, or,
 * when the dealer moved the deadline for a car that is late, when the car should be ready by the
 * same delay. */
function retryFrom(order: Order, request: PriceRequest, leg: number, now: number): number {
  const promised = request.options.find((option) => option.kind === order.option)?.deadline ?? order.deadline
  const delay = Math.max(0, order.deadline - promised)
  return Math.max(now + 2 * HOUR, order.legs[leg]!.pickup.window.from + delay)
}

/** The cars a post carries. */
const pickups = (action: PostAction): number => action.stops.filter((stop) => stop.kind === 'pickup').length

/** Leaves out the stop windows that end before `before`, so the world's window applies: once the order's
 * window has ended, it runs to the end of the world. */
const withoutWindows = (stops: StopRef[], before: number): StopRef[] =>
  stops.map((stop) => (stop.window && stop.window.to < before ? { ...stop, window: undefined } : stop))

/** The fee at once, then 10% of it more every hour: six steps, up to 1.5 times. Level 1 takes one fee only. */
const rising = (now: number, fee: number, level: number): FeeStep[] =>
  (level === 1 ? [0] : [0, 1, 2, 3, 4, 5]).map((k) => ({
    at: now + k * HOUR,
    feeCents: Math.max(1, Math.round(fee * (1 + k / 10))),
  }))

/** 1.5 times the fee at once, then a quarter of it more every half hour, up to 2.5 times. Level 1 takes one fee only. */
const steep = (now: number, fee: number, level: number): FeeStep[] =>
  (level === 1 ? [0] : [0, 1, 2, 3, 4]).map((k) => ({
    at: now + k * 30,
    feeCents: Math.max(1, Math.round(fee * (1.5 + k / 4))),
  }))

/** A pickup and a delivery for each leg. An electric car under 30% gets a charging stop.
 * A stop has its own window only when the note or the retry makes it narrower. Without
 * one, the world plans the pickup in the order's window and the delivery by the deadline. */
function stopsFor(order: Order, legs: number[], note: Note | null, retry: Retry): StopRef[] {
  return legs.flatMap((leg): StopRef[] => {
    const { car, pickup, delivery } = order.legs[leg]!
    const noted = windowFromNote(note, pickup.window, 'pickup')
    const start = Math.max(noted.from, retry.pickupFrom)
    const pickupWindow = { from: start, to: Math.max(noted.to, start) }
    const deliveryBase = { from: delivery.window.from, to: Math.max(delivery.window.from, order.deadline) }
    const deliveryWindow = windowFromNote(note, deliveryBase, 'delivery')
    const lowBattery = car.electric && car.chargePercent !== null && car.chargePercent < 30
    const first: StopRef = {
      orderId: order.id,
      leg,
      kind: 'pickup',
      withPlates: retry.plates,
      withCharging: lowBattery,
    }
    const second: StopRef = { orderId: order.id, leg, kind: 'delivery' }
    return [narrower(first, pickupWindow, pickup.window), narrower(second, deliveryWindow, deliveryBase)]
  })
}

const narrower = (stop: StopRef, window: TimeWindow, base: TimeWindow): StopRef =>
  window.from > base.from || window.to < base.to ? { ...stop, window } : stop
