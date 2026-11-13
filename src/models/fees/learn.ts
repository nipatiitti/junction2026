/** The learners: one function that folds each world event into the fee state. Replaying a week's events from
 * `newFeeState` rebuilds the state, and the state is plain JSON.
 *
 * - The hazard scale: bookings seen over bookings the prior hazard expected for the same open hours.
 * - The fee extras: each feature's multiplier moves with the booked fee over the expected fee of gigs with it,
 *   against that ratio over every gig.
 * - lambda (Design 3): `lambda × exp(eta × (g − rho))` for the pickup region and day, and for experienced
 *   drivers, where g is the fee paid over the fee expected, or 1 plus a penalty at a deadline warning.
 * - mu (Design 4): the same step on the projected late share over its target. */
import type {
  DeadlineCloseEvent,
  FeeStep,
  GigBookedEvent,
  GigDroppedEvent,
  GigExpiredEvent,
  LedgerEvent,
  NoShowEvent,
  OrderCancelledEvent,
} from '../../../vendor/spread-typescript/types.ts'
import { featureList } from './extras.ts'
import { DAY, priorHazard, slicesOf } from './hazard.ts'
import { clamp, type FeeParams } from './params.ts'
import { basisOf, costOf, type FeeGig, feeAt } from './plan.ts'
import { type FeeState, type FollowedGig, newFeeState } from './state.ts'

/** What the learners read: our own actions as the world accepted them, and the world's events. Every other
 * event may be passed too, and changes nothing. */
export type FeeEvent =
  | { kind: 'gig_posted'; at: number; gigId: string; orderIds: string[]; gig: FeeGig; schedule: FeeStep[] }
  | { kind: 'gig_repriced'; at: number; gigId: string; schedule: FeeStep[] }
  | { kind: 'gig_withdrawn'; at: number; gigId: string }
  | GigBookedEvent
  | GigDroppedEvent
  | NoShowEvent
  | GigExpiredEvent
  | DeadlineCloseEvent
  | OrderCancelledEvent
  | LedgerEvent

/** Folds one event into `state` (in place) and returns it. */
export function learn(state: FeeState, event: FeeEvent | { kind: string }, params: FeeParams): FeeState {
  const e = event as FeeEvent
  switch (e.kind) {
    case 'gig_posted':
      state.gigs[e.gigId] = follow(e.gig, e.orderIds, e.schedule, e.at, state, params)
      break
    case 'gig_repriced':
      withGig(state, e.gigId, (gig) => {
        accrue(gig, e.at, state, params)
        gig.schedule = e.schedule
      })
      break
    case 'gig_withdrawn':
    case 'gig_expired':
      withGig(state, e.gigId, (gig) => close(gig, e.at, state, params))
      break
    case 'order_cancelled':
      for (const { gigId } of e.gigs) withGig(state, gigId, (gig) => close(gig, e.at, state, params))
      state.warned = state.warned.filter((id) => id !== e.orderId)
      break
    case 'gig_booked':
      withGig(state, e.gigId, (gig) => booked(gig, e.at, e.feeCents, state, params))
      break
    case 'gig_dropped':
    case 'no_show':
      withGig(state, e.gigId, (gig) => {
        state.drops++
        Object.assign(gig, { open: true, seen: true, since: e.at })
      })
      break
    case 'deadline_close':
      warned(e.orderId, state, params)
      break
    case 'ledger':
      if (e.line.kind === 'revenue' && e.line.orderId) {
        state.delivered++
        state.warned = state.warned.filter((id) => id !== e.line.orderId)
        stepMu(state, params)
      } else if (e.line.kind === 'late_refund' || e.line.kind === 'undelivered_penalty') {
        state.late++
        stepMu(state, params)
      }
      break
  }
  return state
}

/** The state after `events`, from the start of the week. */
export const replay = (events: Iterable<FeeEvent | { kind: string }>, params: FeeParams): FeeState => {
  const state = newFeeState(params)
  for (const event of events) learn(state, event, params)
  return state
}

function follow(
  gig: FeeGig,
  orderIds: string[],
  schedule: FeeStep[],
  at: number,
  state: FeeState,
  params: FeeParams,
): FollowedGig {
  return {
    orderIds,
    region: gig.region,
    day: Math.floor(gig.lastPickupAt / DAY),
    experienced: gig.experienced,
    features: featureList(gig.features),
    basisCents: basisOf(gig, state, params),
    expectedCents: costOf(schedule, gig, at, state, params).paidIfBookedCents,
    lastPickupAt: gig.lastPickupAt,
    schedule,
    postedAt: at,
    seen: gig.seen,
    open: true,
    since: at,
  }
}

function withGig(state: FeeState, gigId: string, act: (gig: FollowedGig) => void): void {
  const gig = state.gigs[gigId]
  if (gig) act(gig)
}

/** Counts the bookings the prior hazard expected while the gig was open, up to `until`. */
function accrue(gig: FollowedGig, until: number, state: FeeState, params: FeeParams): void {
  if (!gig.open || until <= gig.since) return
  for (const slice of slicesOf(gig.since, until, gig.lastPickupAt, gig.seen ? null : gig.postedAt, params)) {
    const fee = feeAt(gig.schedule, slice.at) / gig.basisCents
    const exposure = slice.hours * slice.clock
    state.hazard.fresh.expected += slice.fresh * exposure * priorHazard(fee, slice.lead, false, params)
    state.hazard.seen.expected += (1 - slice.fresh) * exposure * priorHazard(fee, slice.lead, true, params)
  }
  gig.since = until
}

function close(gig: FollowedGig, at: number, state: FeeState, params: FeeParams): void {
  accrue(gig, at, state, params)
  gig.open = false
}

function booked(gig: FollowedGig, at: number, feeCents: number, state: FeeState, params: FeeParams): void {
  const fresh = !gig.seen && (slicesOf(at, at + 1, gig.lastPickupAt, gig.postedAt, params)[0]?.fresh ?? 0) > 0
  close(gig, at, state, params)
  state.hazard[fresh ? 'fresh' : 'seen'].booked++
  state.bookings++
  state.warned = state.warned.filter((id) => !gig.orderIds.includes(id))

  const { learn: l } = params
  const g = Math.min(4, Math.max(0.25, feeCents / Math.max(1, gig.expectedCents)))
  // Each feature against the mean over every gig, so a world that is dear everywhere moves no feature.
  state.logRatio += l.etaExtras * (Math.log(g) - state.logRatio)
  const relative = g / Math.exp(state.logRatio)
  for (const name of gig.features)
    state.extras[name] = clamp(state.extras[name] * Math.exp(l.etaExtras * (relative - 1)), l.extras)
  stepLambda(gig, g, state, params)
}

/** A deadline warning: the order's region and day get g = 1 + the penalty. */
function warned(orderId: string, state: FeeState, params: FeeParams): void {
  if (!state.warned.includes(orderId)) state.warned.push(orderId)
  const gig = Object.values(state.gigs).findLast((gig) => gig.orderIds.includes(orderId))
  if (gig) stepLambda(gig, 1 + params.learn.warnPenalty, state, params)
  stepMu(state, params)
}

function stepLambda(gig: FollowedGig, g: number, state: FeeState, params: FeeParams): void {
  const { etaLambda, rho, lambda: range } = params.learn
  const step = Math.exp(etaLambda * (g - rho))
  const region = state.lambda[`${gig.region}/${gig.day}`] ?? state.lambda[gig.region] ?? 1
  state.lambda[`${gig.region}/${gig.day}`] = state.lambda[gig.region] = clamp(region * step, range)
  if (gig.experienced) state.lambdaExperienced = clamp(state.lambdaExperienced * step, range)
}

/** mu follows the projected late share: late orders, and warned orders still without a driver at their risk,
 * starting from `pseudoOrders` orders at the target. */
function stepMu(state: FeeState, params: FeeParams): void {
  const { lateTarget, pseudoOrders, warnRisk, etaMu, mu } = params.learn
  const atRisk = state.warned.length
  const share = (state.late + warnRisk * atRisk + lateTarget * pseudoOrders) / (state.delivered + atRisk + pseudoOrders)
  state.mu = clamp(state.mu * Math.exp(etaMu * (share / lateTarget - 1)), mu)
}
