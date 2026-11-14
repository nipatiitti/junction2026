/** The fee models' parameters: the priors measured from the saved weeks (src/params/fees.json, written by
 * `uv run python -m analysis.priors_fees`), the flags, and the constants of the search and the learners. */
import { readFileSync } from 'node:fs'

/** The features of a gig that make drivers ask more than the typical fee (findings 9 and 10). */
export const FEATURES = [
  'privatePickup',
  'privateDelivery',
  'tradeIn',
  'premium',
  'weekendDelivery',
  'postedFriday',
  'fewDriversNear',
] as const
export type Feature = (typeof FEATURES)[number]

/** What src/params/fees.json holds. Every value is a ratio or a rate, none keyed to a seed, a driver or a place. */
export type FeePriors = {
  hazard: {
    feeGrid: number[] // fee over the expected fee (typical × extras)
    leadHours: number[] // lower edges of the bands of hours to the last pickup
    fresh: number[][] // bookings per open daytime hour, [lead band][fee], before drivers have seen the order
    seen: number[][] // the same once drivers have viewed the order and left it
    night: number // the hazard from 23:00 to 07:00, as a share of the daytime one
    weekend: number // on Saturday and Sunday
    /** With `hazardFit`: the hazard is the fresh row times this, [lead band], fresh or seen: what booked over the
     * fresh row's expectation in the saved bidprice weeks (`analysis/hazard_check.py`). */
    fit?: { fresh: number[]; seen: number[] }
  }
  extras: Record<Feature, { start: number; measured: number }>
  rates: { drop: number; noShow: number; cancel: number } // per booking, per booking, per order won
  late: { costShare: number; feeRatio: number } // a late order's refunds and penalty over its price; its fee over typical
}

export type FeeFlags = {
  solver: boolean // plan the schedule by the search; false: the fixed ramp of src/dispatch.ts
  extras: boolean // scale the fee by the learned feature multipliers
  measuredExtras: boolean // start the feature multipliers at the measured values instead of 1
  capacity: boolean // scale the cost by lambda
  onTime: boolean // scale the lateness cost by mu
  cold: boolean // every prior neutral
  hazardFit: boolean // the fresh row times the fitted scale of each lead band, fresh or seen; false: the explore table
}

export type FeeParams = {
  level: number // level 1 takes one step
  flags: FeeFlags
  priors: FeePriors
  plan: {
    fees: { from: number; to: number; step: number } // the fees the search tries, over the expected fee: from the fee probe's median, the cheapest driver of an idle market
    raises: number // at most this many raises after the opening fee
    topRatio: number // the least last step, over the expected fee, so the car is not left behind
    topLeadMinutes: number // that step is due this long before the last pickup (22:00 the evening before at night)
    priceCap: number // no fee above this many times the order's price: an undelivered car costs three
    freshMinutes: number // daytime minutes a new gig is fresh: most views come in the first minutes
    sliceMinutes: number
  }
  learn: {
    pseudoBookings: number // weight of the prior hazard, in expected bookings
    hazardScale: [number, number]
    etaExtras: number
    extras: [number, number]
    etaLambda: number
    rho: number // the fee paid over the fee expected that leaves lambda where it is
    warnPenalty: number // g = 1 + this at a deadline warning
    lambda: [number, number]
    etaMu: number
    lateTarget: number // the late share mu aims at
    pseudoOrders: number // orders at the target share that the late share starts from
    warnRisk: number // the chance that a warned order still without a driver ends late
    mu: [number, number]
    dropPseudo: number // bookings at the prior drop rate that the learned rate starts from
  }
}

const PRIORS: FeePriors = JSON.parse(readFileSync(new URL('../../params/fees.json', import.meta.url), 'utf8'))

/** Priors that know nothing of the world: one hazard for every lead and both states, rising with the fee from
 * half the typical fee; no night, weekend, feature or drop effect; a late car costs the 2-24 hour refund and the
 * starter's steep top. The learners take it from there. */
function neutral(priors: FeePriors): FeePriors {
  const { feeGrid, leadHours } = priors.hazard
  const curve = feeGrid.map((fee) => Math.max(0, fee - 0.5))
  const table = leadHours.map(() => curve)
  const extras = Object.fromEntries(FEATURES.map((name) => [name, { start: 1, measured: 1 }])) as FeePriors['extras']
  return {
    hazard: { feeGrid, leadHours, fresh: table, seen: table, night: 1, weekend: 1 },
    extras,
    rates: { drop: 0, noShow: 0, cancel: 0 },
    late: { costShare: 0.25, feeRatio: 2.5 },
  }
}

export const DEFAULT_FLAGS: FeeFlags = {
  solver: true,
  extras: true,
  measuredExtras: false,
  capacity: true,
  onTime: true,
  cold: false,
  hazardFit: true,
}

/** The parameters for one world. */
export function feeParams(level: number, flags: Partial<FeeFlags> = {}): FeeParams {
  const all = { ...DEFAULT_FLAGS, ...flags }
  return {
    level,
    flags: all,
    priors: all.cold ? neutral(PRIORS) : PRIORS,
    plan: {
      fees: { from: 0.75, to: 2.5, step: 0.05 },
      raises: 2,
      topRatio: 1.5,
      topLeadMinutes: 6 * 60,
      priceCap: 3,
      freshMinutes: 60,
      sliceMinutes: 60,
    },
    learn: {
      pseudoBookings: 10,
      hazardScale: [0.33, 3],
      etaExtras: 0.05,
      extras: [0.8, 1.6],
      etaLambda: 0.1,
      rho: 1,
      warnPenalty: 0.5,
      lambda: [0.8, 1.6],
      etaMu: 0.02,
      lateTarget: 0.05,
      pseudoOrders: 20,
      warnRisk: 0.5,
      mu: [0.5, 2],
      dropPseudo: 50,
    },
  }
}

/** A multiplier inside its range; anything not finite is 1, the neutral value. */
export const clamp = (x: number, [lo, hi]: readonly [number, number]): number =>
  Math.min(hi, Math.max(lo, Number.isFinite(x) ? x : 1))
