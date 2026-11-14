/** What a won order really costs, the `c` that joins the two sides (Designs 2 to 4 in one number): the fee finally
 * paid for its cars after every raise, drop, reprice and urgent schedule, and its late refunds and penalty.
 *
 * The prior is src/params/cost.json, written by `python3 analysis/cost_fit.py --write` from the saved weeks of
 * bidprice and dispatch.py: the mean fee over typical and late cost over price by option and hours from the win to the
 * last pickup, times one multiplier for each feature known at quote time. The week then teaches the ratio of what it
 * pays to that prior, a ratio of sums, so a gap of 0.95 against 1.35 closes within tens of gigs:
 * - fees for each band of hours (shrunk to the ratio over every band), from the bookings that hold and from each gig
 *   still open at a fee above the prior's, at the fee in the app: the dear tail counts before it books;
 * - late cost over the orders whose last pickup has passed, from the ledger, or a provisional refund for an order
 *   with no car collected yet: the late orders count before their refunds post.
 * Plain data, rebuilt from the events and the actions sent. */
import { readFileSync } from 'node:fs'
import type { FeeStep, Leg } from '../../../vendor/spread-typescript/spread.ts'
import { feeAt } from '../../models/fees/plan.ts'
import type { Option } from '../../models/quote/index.ts'
import { DAY, HOUR } from '../../time.ts'

const FEATURES = ['premium', 'private', 'tradeIn', 'friday', 'fewNear'] as const
type Feature = (typeof FEATURES)[number]

export type CostPrior = {
  leadHours: number[] // lower edges of the bands of hours from the win to the last pickup
  fee: Record<Option, number[]> // mean fee paid over typical, [band]
  late: Record<Option, number[]> // mean late refunds and penalty over price, [band]
  feeMultiplier: Record<Feature, number>
  lateMultiplier: Record<Feature, number>
}

export const readCostPrior = (): CostPrior =>
  JSON.parse(readFileSync(new URL('../../params/cost.json', import.meta.url), 'utf8')) as CostPrior

/** What is known of an order's cost when it is quoted. */
export type Kind = { option: Option; band: number; features: Feature[] }

/** The kind of some cars quoted or won at `now`, whose last pickup is `lastPickupAt`. */
export function kindOf(
  legs: readonly Leg[],
  option: Option,
  now: number,
  lastPickupAt: number,
  fewNear: boolean,
  prior: CostPrior,
): Kind {
  const hours = (lastPickupAt - now) / HOUR
  const band = Math.max(
    0,
    prior.leadHours.findLastIndex((edge) => hours >= edge),
  )
  const ready = Math.max(now, legs[0]?.pickup.window.from ?? now)
  const has: Record<Feature, boolean> = {
    premium: legs.some((leg) => leg.car.premium),
    private: legs.some((leg) => leg.pickup.privateAddress || leg.delivery.privateAddress),
    tradeIn: legs.length > 1,
    friday: Math.floor(ready / DAY) % 7 === 4,
    fewNear,
  }
  return { option, band, features: FEATURES.filter((name) => has[name]) }
}

/** The prior's fee over typical and late cost over price for a kind. */
export function priorOf(kind: Kind, prior: CostPrior): { fee: number; late: number } {
  const times = (multiplier: Record<Feature, number>) =>
    kind.features.reduce((product, name) => product * (multiplier[name] ?? 1), 1)
  return {
    fee: (prior.fee[kind.option]?.[kind.band] ?? 1.3) * times(prior.feeMultiplier),
    late: (prior.late[kind.option]?.[kind.band] ?? 0.03) * times(prior.lateMultiplier),
  }
}

type Sums = { real: number; expected: number }

/** An order won: its band, the prior's fee in cents for all its cars, its late cost and price in cents, its last
 * pickup, whether a car has been collected, whether its ledger has settled it, and what lateness cost. */
type OrderCost = {
  band: number
  feeCents: number
  lateCents: number
  priceCents: number
  cars: number
  lastPickupAt: number
  picked: boolean
  settled: boolean
  lateReal: number
}

/** A gig of ours: its order and cars, its schedule, and whether it is open (no driver holds it, it can be booked). */
type GigCost = { orderId: string; cars: number; schedule: FeeStep[]; open: boolean }

export type CostState = {
  /** The fee paid against the prior's fee, for each band, over the bookings that hold now. */
  fee: Sums[]
  orders: Record<string, OrderCost>
  /** Each booking that holds: its order's band, fee paid and the prior's fee for its cars. */
  bookings: Record<string, { band: number; real: number; expected: number }>
  gigs: Record<string, GigCost>
}

export function newCostState(prior: CostPrior): CostState {
  return { fee: prior.leadHours.map(() => ({ real: 0, expected: 0 })), orders: {}, bookings: {}, gigs: {} }
}

/** How fast the week moves the prior: its weight, in gigs or orders of the prior's own cost. */
export type CostLearning = { learn: boolean; pseudoGigs: number }

const RANGE: [number, number] = [0.5, 3]
const clamp = (x: number) => Math.min(RANGE[1], Math.max(RANGE[0], Number.isFinite(x) ? x : 1))
/** What an order whose last pickup passed with no car collected will refund, until its ledger says: the 2-24 hour
 * step of RULES.md. */
const PROVISIONAL_LATE = 0.25

/** What this week pays over the prior's fee, for a band: the band's own ratio, shrunk to the ratio over every band
 * (that ratio itself for `band` null). The prior weighs `pseudoGigs` gigs of the mean order's prior fee. */
export function feeRatio(state: CostState, band: number | null, learning: CostLearning, now: number): number {
  if (!learning.learn) return 1
  const sums = state.fee.map((s) => ({ ...s }))
  for (const gig of Object.values(state.gigs)) {
    const order = state.orders[gig.orderId]
    if (!gig.open || !order || order.settled) continue
    const fee = feeAt(gig.schedule, now)
    const expected = (order.feeCents * gig.cars) / Math.max(1, order.cars)
    const own = sums[order.band]
    if (own && fee > expected) {
      own.real += fee
      own.expected += expected
    }
  }
  const all = sums.reduce((sum, s) => ({ real: sum.real + s.real, expected: sum.expected + s.expected }), {
    real: 0,
    expected: 0,
  })
  const k = learning.pseudoGigs * mean(state, 'feeCents')
  const overall = (all.real + k) / (all.expected + k)
  if (band === null) return clamp(overall)
  const own = sums[band] ?? { real: 0, expected: 0 }
  return clamp((own.real + k * overall) / (own.expected + k))
}

/** What this week's late orders cost over the prior's late cost, over the orders whose last pickup has passed. The
 * prior weighs `pseudoGigs` orders of the mean prior late cost. */
export function lateRatio(state: CostState, learning: CostLearning, now: number): number {
  if (!learning.learn) return 1
  let real = 0
  let expected = 0
  for (const order of Object.values(state.orders)) {
    if (order.lastPickupAt >= now) continue
    expected += order.lateCents
    real += order.settled || order.picked ? order.lateReal : PROVISIONAL_LATE * order.priceCents
  }
  const k = learning.pseudoGigs * mean(state, 'lateCents')
  return clamp((real + k) / (expected + k))
}

const mean = (state: CostState, key: 'feeCents' | 'lateCents'): number => {
  const orders = Object.values(state.orders)
  return orders.length > 0 ? orders.reduce((sum, order) => sum + order[key], 0) / orders.length : 1
}

/** Remembers an order won, with the prior's cost of its kind. */
export function remember(
  state: CostState,
  orderId: string,
  kind: Kind,
  typicalCents: number,
  priceCents: number,
  cars: number,
  lastPickupAt: number,
  prior: CostPrior,
): void {
  const { fee, late } = priorOf(kind, prior)
  state.orders[orderId] = {
    band: kind.band,
    feeCents: fee * typicalCents,
    lateCents: late * priceCents,
    priceCents,
    cars,
    lastPickupAt,
    picked: false,
    settled: false,
    lateReal: 0,
  }
}

/** A gig of ours that the world accepted. */
export function posted(state: CostState, gigId: string, orderId: string, cars: number, schedule: FeeStep[]): void {
  state.gigs[gigId] = { orderId, cars, schedule, open: !state.bookings[gigId] }
}

/** A gig's new schedule. */
export function repriced(state: CostState, gigId: string, schedule: FeeStep[]): void {
  const gig = state.gigs[gigId]
  if (gig) gig.schedule = schedule
}

/** A gig that can no longer be booked: expired, withdrawn or done. */
export function closed(state: CostState, gigId: string): void {
  const gig = state.gigs[gigId]
  if (gig) gig.open = false
}

/** A booking of a gig that carries `cars` cars of the order, at `feeCents`. */
export function booked(state: CostState, gigId: string, orderId: string, cars: number, feeCents: number): void {
  const order = state.orders[orderId]
  if (!order) return
  unbooked(state, gigId)
  const gig = state.gigs[gigId]
  if (gig) gig.open = false
  const expected = (order.feeCents * cars) / Math.max(1, order.cars)
  state.bookings[gigId] = { band: order.band, real: feeCents, expected }
  const sums = state.fee[order.band]
  if (sums) {
    sums.real += feeCents
    sums.expected += expected
  }
}

/** A driver gave the gig back: that booking will not be paid, and the gig is open again. */
export function unbooked(state: CostState, gigId: string): void {
  const gig = state.gigs[gigId]
  if (gig) gig.open = true
  const booking = state.bookings[gigId]
  if (!booking) return
  delete state.bookings[gigId]
  const sums = state.fee[booking.band]
  if (sums) {
    sums.real -= booking.real
    sums.expected -= booking.expected
  }
}

/** A car of the order has been collected. */
export function picked(state: CostState, orderId: string): void {
  const order = state.orders[orderId]
  if (order) order.picked = true
}

/** The order's last pickup moved (a change, snow, a delivered leg). */
export function moved(state: CostState, orderId: string, lastPickupAt: number): void {
  const order = state.orders[orderId]
  if (order) order.lastPickupAt = lastPickupAt
}

export function cancelled(state: CostState, orderId: string): void {
  delete state.orders[orderId]
}

/** A ledger line of an order: its revenue line (delivered), a late refund, or the penalty of a car never delivered. */
export function settled(state: CostState, orderId: string, line: string, cents: number): void {
  const order = state.orders[orderId]
  if (!order) return
  if (line === 'revenue' || line === 'undelivered_penalty') order.settled = true
  if (line === 'late_refund' || line === 'undelivered_penalty') order.lateReal += Math.abs(cents)
}
