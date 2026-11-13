/** The fee side of our work: the `FeeGig` of a request's option before it is won and of an order's cars, the
 * schedules (the ramp that dispatch.py is on time with, the deadline warning's ramp, the climb of a gig left open),
 * and admission's tightening from the late share. */
import type { DeliveryOption, FeeStep, Leg, Order, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type FeeGig, type FeeParams, type FeeState, featuresOf, fewDriversNear } from '../../models/fees/index.ts'
import { feeAt } from '../../models/fees/plan.ts'
import { DAY, driveMinutes, HOUR } from '../../ops/index.ts'
import type { Setup } from '../../strategy.ts'
import type { BidPriceParams } from './params.ts'

/** Under this share of orders on time, a team is not ranked. */
const UNRANKED_LATE = 0.1
/** The ramp's early raises: this long after the post, this share of the way from the opening fee to the top. */
const RAISES: [number, number][] = [
  [HOUR, 0.1],
  [3 * HOUR, 0.3],
]
/** With less than this before the top is due, the ramp opens closer to its top. */
const URGENT_SPAN = 8 * HOUR
const MAX_STEPS = 48

/** A request's option, as a gig posted when it arrives: its typical fee, the option's list price for the price, and
 * the last pickup that still makes the deadline. `lateWeight` scales the cost of a late car (the dealer's trust). */
export function requestFeeGig(request: PriceRequest, option: DeliveryOption, lateWeight: number, setup: Setup): FeeGig {
  return {
    typicalCents: request.referenceFeeCents,
    priceCents: option.listPriceCents,
    lastPickupAt: option.deadline - driveMinutes(setup.map, request.legs),
    ...where(request.legs, option.deadline, request.arrivedAt, setup),
    seen: false,
    lateWeight,
  }
}

/** The cars `legs` of an order, posted at `at`: their share of the request's typical fee and of the price. */
export function orderFeeGig(
  order: Order,
  request: PriceRequest,
  legs: readonly number[],
  experienced: boolean,
  at: number,
  seen: boolean,
  lateWeight: number,
  setup: Setup,
): FeeGig {
  const share = legs.length / Math.max(1, order.legs.length)
  const cars = legs.flatMap((leg) => order.legs[leg] ?? [])
  return {
    typicalCents: request.referenceFeeCents * share,
    priceCents: order.priceCents * share,
    lastPickupAt: order.lastPickupAt,
    ...where(cars, order.deadline, at, setup),
    experienced,
    seen,
    lateWeight,
  }
}

/** The pickup region, the fee features and the audience of some cars. */
function where(legs: Leg[], deadline: number, at: number, setup: Setup) {
  const delivery = legs[0]?.delivery.placeId ?? ''
  return {
    region: legs[0]?.pickup.placeId ?? '',
    features: featuresOf(legs, deadline, at, fewDriversNear(delivery, setup.roster, setup.map)),
    experienced: legs.some((leg) => leg.car.premium),
  }
}

/** From the deadline warning on, the fee is at least `topRatio` × typical, rising every half hour to `urgentTop` ×
 * typical two hours later: a car left undelivered costs twice its price. */
export const urgentRamp = (now: number, typicalCents: number, p: BidPriceParams): FeeStep[] =>
  [0, 1, 2, 3, 4].map((k) => ({
    at: now + k * 30,
    feeCents: typicalCents * (p.topRatio + ((p.urgentTop - p.topRatio) * k) / 4),
  }))

/** The schedule that dispatch.py is on time with: `openFee` × typical, raised early (to about 1.06 after an hour and
 * 1.38 after three), and `topFee` × typical `topLeadHours` before the last pickup (22:00 the evening before when that
 * falls at night). Closer to the top when little time is left. Before the top no step goes above what the car
 * earns; the top stays under the price plus what a late car costs, and under three prices. */
export function ramp(gig: FeeGig, now: number, p: BidPriceParams, level: number): FeeStep[] {
  const { typicalCents: typical, priceCents: price } = gig
  const worth = Math.min(Math.max(price, typical), 3 * price)
  const top = Math.max(1, Math.min(p.topFee * typical, worth + price, 3 * price))
  const topAt = beforeNight(gig.lastPickupAt - p.topLeadHours * HOUR, now)
  const span = topAt - now
  if (span <= HOUR) return valid([{ at: now, feeCents: top }], level)
  const urgency = Math.max(0, 1 - span / URGENT_SPAN)
  const opening = Math.min(p.openFee * typical + (top - p.openFee * typical) * urgency, top)
  const cap = Math.max(opening, Math.min(top, worth))
  const raises = RAISES.map(([after, share], k) => ({
    at: beforeNight(Math.min(now + after, now + (span * (k + 1)) / 3), now),
    feeCents: Math.min(cap, opening + (top - opening) * share),
  }))
  return valid([{ at: now, feeCents: opening }, ...raises, { at: topAt, feeCents: top }], level)
}

/** A gig left open after its schedule ended: from `from` cents, `climbStep` × typical more every hour, up to
 * `climbTop` × typical but never above twice the price, what leaving the car costs. */
export function climb(from: number, now: number, gig: FeeGig, p: BidPriceParams, level: number): FeeStep[] {
  const cap = Math.max(from, Math.min(p.climbTop * gig.typicalCents, 2 * gig.priceCents))
  const step = Math.max(1, p.climbStep * gig.typicalCents)
  const steps: FeeStep[] = []
  for (let k = 0; k < MAX_STEPS && (steps.at(-1)?.feeCents ?? 0) < cap; k++)
    steps.push({ at: now + k * HOUR, feeCents: Math.min(cap, from + step * (k + 1)) })
  return valid(steps, level)
}

/** The higher of two schedules at every minute: it never falls when neither does. */
export function higher(a: FeeStep[], b: FeeStep[], level: number): FeeStep[] {
  const times = [...new Set([...a, ...b].map((step) => step.at))].sort((x, y) => x - y)
  const steps: FeeStep[] = []
  for (const at of times) {
    const feeCents = Math.round(Math.max(feeAt(a, at), feeAt(b, at)))
    if (feeCents > (steps.at(-1)?.feeCents ?? 0)) steps.push({ at, feeCents })
  }
  return level === 1 ? steps.slice(-1).map((step) => ({ ...step, at: times[0] ?? step.at })) : steps.slice(0, MAX_STEPS)
}

/** Whole minutes and cents, times in order, fees never falling, 1 to 48 steps, the first only at level 1. */
function valid(steps: FeeStep[], level: number): FeeStep[] {
  const out: FeeStep[] = []
  for (const step of [...steps].sort((a, b) => a.at - b.at)) {
    const at = Math.round(step.at)
    const feeCents = Math.max(1, Math.round(step.feeCents), out.at(-1)?.feeCents ?? 1)
    const last = out.at(-1)
    if (last && at <= last.at) last.feeCents = feeCents
    else if (!last || feeCents > last.feeCents) out.push({ at, feeCents })
  }
  return out.slice(0, level === 1 ? 1 : MAX_STEPS)
}

/** A step due at night (23:00 to 07:00) comes at 22:00 the evening before, but not before now. */
function beforeNight(at: number, now: number): number {
  const minute = at % DAY
  if (minute >= 23 * HOUR) return Math.max(now, at - minute + 22 * HOUR)
  if (minute < 7 * HOUR) return Math.max(now, at - minute - DAY + 22 * HOUR)
  return at
}

/** Admission's tightening (`canServe`) from the projected late share, as `mu` counts it: 1 at the target, falling
 * to 0.25 as the share nears the 10% that loses the ranking. */
export function tightening(state: FeeState, params: FeeParams): number {
  const { lateTarget, pseudoOrders, warnRisk } = params.learn
  const atRisk = state.warned.length
  const share = (state.late + warnRisk * atRisk + lateTarget * pseudoOrders) / (state.delivered + atRisk + pseudoOrders)
  const room = Math.max(0.01, UNRANKED_LATE - lateTarget)
  return Math.min(1, Math.max(0.25, 1 - (0.75 * (share - lateTarget)) / room))
}
