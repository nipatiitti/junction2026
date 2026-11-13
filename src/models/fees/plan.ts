/** The fee schedule of a gig and its expected cost `c`, from one function (Design 2).
 *
 * A gig is open from now to its last pickup, in slices of an hour. In each slice a driver books it at the
 * hazard of its fee, and keeps it unless they drop it. A car still without a driver at the last pickup is late:
 * it pays the fee of a late car and its refunds. The search finds the schedule of least expected cost among
 * those that open at one fee of a grid, raise at most twice at the start of any slice, and reach the top fee
 * a few hours before the last pickup. A dynamic programme over (slice, fee, raises left) finds that schedule
 * exactly, in well under a millisecond. */
import type { FeeStep } from '../../../vendor/spread-typescript/types.ts'
import { DAY, HOUR } from '../../time.ts'
import { type Features, feeExtra } from './extras.ts'
import { acceptHazard, dropShare, type Slice, slicesOf } from './hazard.ts'
import { clamp, type FeeParams } from './params.ts'
import type { FeeState } from './state.ts'

/** What a schedule is planned from, for the cars of one gig: a won order's, or a request's not yet won. */
export type FeeGig = {
  typicalCents: number // the typical fee for the gig's cars
  priceCents: number // the order's price for them (for a request: the option's price)
  lastPickupAt: number // the order's `lastPickupAt` (for a request: its estimate)
  region: string // the pickup place id
  features: Features
  experienced: boolean // the audience is experienced drivers only
  seen: boolean // drivers have seen the order before: a repost, a retry, after a drop or a deadline warning
  lateWeight?: number // scales the refunds of a late car, for what lateness costs besides them (a dealer's trust); 1 by default
}

export type FeeCost = {
  feeCents: number // expected fee paid, the fee of a late car included
  lateCents: number // expected refunds and penalty, times mu
  costCents: number // (feeCents + lateCents) × lambda: the `c` of the quote side
  bookShare: number // the chance that a driver books and keeps the gig before its last pickup
  paidIfBookedCents: number // the fee expected when a driver books: what the learners compare a booking with
}

export type FeePlan = FeeCost & { schedule: FeeStep[] }

/** The capacity multiplier of the gig's pickup region and day, times the experienced drivers' one. */
export function lambdaOf(
  gig: Pick<FeeGig, 'region' | 'lastPickupAt' | 'experienced'>,
  state: FeeState,
  params: FeeParams,
) {
  if (!params.flags.capacity) return 1
  const region = state.lambda[`${gig.region}/${Math.floor(gig.lastPickupAt / DAY)}`] ?? state.lambda[gig.region] ?? 1
  return clamp(region * (gig.experienced ? state.lambdaExperienced : 1), params.learn.lambda)
}

/** The on-time multiplier on the lateness cost. */
export const muOf = (state: FeeState, params: FeeParams): number =>
  params.flags.onTime ? clamp(state.mu, params.learn.mu) : 1

/** The fee the hazard's ratios are over: the typical fee times the gig's extras. */
export const basisOf = (gig: FeeGig, state: FeeState, params: FeeParams): number =>
  Math.max(1, gig.typicalCents * feeExtra(gig.features, state, params))

/** The schedule for `gig` from `now`, and its expected cost. */
export function planFees(gig: FeeGig, now: number, state: FeeState, params: FeeParams): FeePlan {
  const schedule = params.flags.solver ? solve(gig, now, state, params) : ramp(gig, now, params)
  return { schedule, ...costOf(schedule, gig, now, state, params) }
}

/** The expected cost of any schedule for `gig` from `now`. */
export function costOf(schedule: FeeStep[], gig: FeeGig, now: number, state: FeeState, params: FeeParams): FeeCost {
  const basis = basisOf(gig, state, params)
  const late = lateCost(gig, basis, state, params)
  const keep = 1 - dropShare(state, params)
  let open = 1 // the chance that no driver holds it yet
  let paid = 0
  for (const slice of slicesFor(gig, now, params)) {
    const fee = feeAt(schedule, slice.at)
    const stay = Math.exp(-hazard(fee / basis, slice, state, params) * keep * slice.hours * slice.clock)
    paid += open * (1 - stay) * fee
    open *= stay
  }
  const lastFee = schedule[schedule.length - 1]?.feeCents ?? 0
  const feeCents = paid + open * Math.max(lastFee, late.fee)
  const lateCents = open * late.refund
  return {
    feeCents,
    lateCents,
    costCents: (feeCents + lateCents) * lambdaOf(gig, state, params),
    bookShare: 1 - open,
    paidIfBookedCents: open < 1 ? paid / (1 - open) : Math.max(lastFee, late.fee),
  }
}

/** The least-cost schedule on the grid. */
function solve(gig: FeeGig, now: number, state: FeeState, params: FeeParams): FeeStep[] {
  const { plan } = params
  const basis = basisOf(gig, state, params)
  const cap = plan.priceCap * gig.priceCents
  const late = lateCost(gig, basis, state, params)
  const top = Math.min(cap, plan.topRatio * basis)
  if (now >= gig.lastPickupAt) return valid([{ at: now, feeCents: Math.min(cap, Math.max(top, late.fee)) }], params)

  const fees = feeGrid(basis, cap, params)
  const slices = slicesFor(gig, now, params)
  const T = slices.length
  const F = fees.length
  const R = params.level === 1 ? 0 : plan.raises
  // From the top slice on, the fee is at least the top fee: the car must not be left behind.
  const topAt = beforeNight(gig.lastPickupAt - plan.topLeadMinutes, now)
  const topIndex = slices.findIndex((slice) => slice.at >= topAt)
  const topSlice = R === 0 || topIndex < 0 ? T : topIndex
  const topIndexFee = fees.findIndex((fee) => fee >= top - 0.5)
  const firstTop = topIndexFee < 0 ? F - 1 : topIndexFee
  const keep = 1 - dropShare(state, params)
  const stay = slices.map((slice) =>
    fees.map((fee) => Math.exp(-hazard(fee / basis, slice, state, params) * keep * slice.hours * slice.clock)),
  )

  // Backwards over the slices. next[k][j]: the expected cost from the next slice on, at fee j with k raises
  // left; at the last pickup, that of a late car. hold[k][j]: the same from this slice on, holding fee j through
  // it. raiseTo[t][k][j]: the fee to raise to at the start of slice t (j itself to hold).
  let next = Array.from({ length: R + 1 }, () => fees.map((fee) => Math.max(fee, late.fee) + late.refund))
  let hold = next
  const raiseTo: number[][][] = new Array(T)
  for (let t = T - 1; t >= 0; t--) {
    const p = stay[t]
    const after = next
    hold = after.map((cost) =>
      fees.map((fee, j) => (t >= topSlice && j < firstTop ? Infinity : (1 - p[j]) * fee + p[j] * cost[j])),
    )
    const raises = hold.map((row, k) => bestRaises(row, hold[k - 1]))
    raiseTo[t] = raises
    next = hold.map((row, k) => row.map((cost, j) => (raises[k][j] === j ? cost : hold[k - 1][raises[k][j]])))
  }

  // Open at the best fee to hold through the first slice, then raise where the programme chose to.
  let j = hold[R].indexOf(Math.min(...hold[R]))
  const steps: FeeStep[] = [{ at: now, feeCents: fees[j] }]
  for (let t = 1, k = R; t < T && k > 0; t++) {
    const to = raiseTo[t][k][j]
    if (to !== j) {
      steps.push({ at: slices[t].at, feeCents: fees[to] })
      j = to
      k--
    }
  }
  return valid(steps, params)
}

/** For each fee j, the higher fee whose cost with one raise less (`fewer`) beats holding j, or j itself. A
 * running minimum from the top fee down. */
function bestRaises(hold: number[], fewer: number[] | undefined): number[] {
  const to = hold.map((_, j) => j)
  if (!fewer) return to
  let best = -1
  for (let j = hold.length - 1; j >= 0; j--) {
    if (best >= 0 && fewer[best] < hold[j]) to[j] = best
    if (best < 0 || fewer[j] < fewer[best]) best = j
  }
  return to
}

/** The fees the search tries, in cents: the grid over the basis, up to the price cap. */
function feeGrid(basis: number, cap: number, params: FeeParams): number[] {
  const { from, to, step } = params.plan.fees
  const fees: number[] = []
  for (let i = 0; from + i * step <= to + 1e-9; i++) {
    const fee = (from + i * step) * basis
    if (fee <= cap) fees.push(fee)
  }
  return fees.length > 0 ? fees : [cap]
}

const slicesFor = (gig: FeeGig, now: number, params: FeeParams): Slice[] =>
  slicesOf(now, gig.lastPickupAt, gig.lastPickupAt, gig.seen ? null : now, params)

/** The hazard of a slice: fresh for its fresh share, seen for the rest. */
function hazard(ratio: number, slice: Slice, state: FeeState, params: FeeParams): number {
  const fresh = slice.fresh > 0 ? slice.fresh * acceptHazard(ratio, slice.lead, false, state, params) : 0
  return fresh + (1 - slice.fresh) * acceptHazard(ratio, slice.lead, true, state, params)
}

/** A car without a driver at its last pickup: the fee that moves it late, and its refunds times mu and the gig's
 * late weight. */
function lateCost(gig: FeeGig, basis: number, state: FeeState, params: FeeParams) {
  const { feeRatio, costShare } = params.priors.late
  return {
    fee: Math.min(params.plan.priceCap * gig.priceCents, feeRatio * basis),
    refund: muOf(state, params) * costShare * gig.priceCents * (gig.lateWeight ?? 1),
  }
}

/** The fixed ramp of src/dispatch.ts: the typical fee, 10% more every hour up to 1.5 times; from the deadline
 * warning on, 1.5 times, then a quarter more every half hour up to 2.5 times. */
function ramp(gig: FeeGig, now: number, params: FeeParams): FeeStep[] {
  const steep = now >= gig.lastPickupAt - 3 * HOUR
  const steps = steep
    ? [0, 1, 2, 3, 4].map((k) => ({ at: now + k * 30, feeCents: gig.typicalCents * (1.5 + k / 4) }))
    : [0, 1, 2, 3, 4, 5].map((k) => ({ at: now + k * HOUR, feeCents: gig.typicalCents * (1 + k / 10) }))
  return valid(steps, params)
}

/** The fee in the app at `at`: the latest step that has started, or the first before it starts. */
export const feeAt = (schedule: FeeStep[], at: number): number =>
  schedule.reduce((fee, step) => (step.at <= at ? step.feeCents : fee), schedule[0]?.feeCents ?? 0)

/** A step due at night (23:00 to 07:00) comes at 22:00 the evening before, but not before now. */
function beforeNight(at: number, now: number): number {
  const minute = at % DAY
  if (minute >= 23 * HOUR) return Math.max(now, at - minute + 22 * HOUR)
  if (minute < 7 * HOUR) return Math.max(now, at - minute - DAY + 22 * HOUR)
  return at
}

/** Whole minutes and cents, at least 1 cent, times in order, fees never falling, 1 to 48 steps, one at level 1. */
function valid(steps: FeeStep[], params: FeeParams): FeeStep[] {
  const schedule: FeeStep[] = []
  for (const step of steps) {
    const at = Math.round(step.at)
    const feeCents = Math.max(1, Math.round(step.feeCents), schedule[schedule.length - 1]?.feeCents ?? 1)
    const last = schedule[schedule.length - 1]
    if (last && at <= last.at) last.feeCents = feeCents
    else if (!last || feeCents > last.feeCents) schedule.push({ at, feeCents })
  }
  return schedule.slice(0, params.level === 1 ? 1 : 48)
}
