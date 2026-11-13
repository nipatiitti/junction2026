/** The fee models' view of our work: the `FeeGig` of a request's option before it is won and of an order's cars,
 * the deadline warning's ramp, and admission's tightening from the late share. */
import type { DeliveryOption, FeeStep, Leg, Order, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type FeeGig, type FeeParams, type FeeState, featuresOf, fewDriversNear } from '../../models/fees/index.ts'
import { feeAt } from '../../models/fees/plan.ts'
import { driveMinutes } from '../../ops/index.ts'
import type { Setup } from '../../strategy.ts'
import type { BidPriceParams } from './params.ts'

/** Under this share of orders on time, a team is not ranked. */
const UNRANKED_LATE = 0.1

/** A request's option, as a gig posted when it arrives: its typical fee, the option's list price for the price, and
 * the last pickup that still makes the deadline. */
export function requestFeeGig(request: PriceRequest, option: DeliveryOption, setup: Setup): FeeGig {
  return {
    typicalCents: request.referenceFeeCents,
    priceCents: option.listPriceCents,
    lastPickupAt: option.deadline - driveMinutes(setup.map, request.legs),
    ...where(request.legs, option.deadline, request.arrivedAt, setup),
    seen: false,
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

/** The higher of two schedules at every minute: it never falls when neither does. */
export function higher(a: FeeStep[], b: FeeStep[], level: number): FeeStep[] {
  const times = [...new Set([...a, ...b].map((step) => step.at))].sort((x, y) => x - y)
  const steps: FeeStep[] = []
  for (const at of times) {
    const feeCents = Math.round(Math.max(feeAt(a, at), feeAt(b, at)))
    if (feeCents > (steps.at(-1)?.feeCents ?? 0)) steps.push({ at, feeCents })
  }
  return level === 1 ? steps.slice(-1).map((step) => ({ ...step, at: times[0] ?? step.at })) : steps.slice(0, 48)
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
