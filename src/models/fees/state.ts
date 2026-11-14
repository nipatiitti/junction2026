/** What the fee models learn during a week: plain JSON, rebuilt by replaying the events (learn.ts). */
import type { FeeStep } from '../../../vendor/spread-typescript/types.ts'
import { FEATURES, type Feature, type FeeParams } from './params.ts'

/** Bookings seen against the bookings the prior hazard expected over the same open hours. */
export type Tally = { booked: number; expected: number }

/** A gig the learners follow from its post. */
export type FollowedGig = {
  orderIds: string[]
  region: string // pickup place id
  day: number // day of its last pickup, from Monday 0
  experienced: boolean
  features: Feature[] // the features it has
  basisCents: number // typical fee × feature extras at the post: the fee ratios are over this
  expectedCents: number // the fee the plan expected if a driver books
  lastPickupAt: number
  schedule: FeeStep[]
  postedAt: number
  seen: boolean // drivers had seen the order before this post
  open: boolean
  since: number // open hours counted up to here
}

export type FeeState = {
  gigs: Record<string, FollowedGig>
  hazard: { fresh: Tally[]; seen: Tally[] } // one tally for each band of hours to the last pickup
  extras: Record<Feature, number>
  logRatio: number // running mean of log(fee paid / fee expected) over every booking
  lambda: Record<string, number> // `${region}/${day}`, and `${region}` for its latest day
  lambdaExperienced: number
  mu: number
  bookings: number
  drops: number // drops and no-shows
  delivered: number
  late: number
  warned: string[] // orders whose deadline warning came and that no driver holds
}

export function newFeeState(params: FeeParams): FeeState {
  const { extras } = params.priors
  const start = (name: Feature) => (params.flags.measuredExtras ? extras[name].measured : extras[name].start)
  return {
    gigs: {},
    hazard: { fresh: tallies(params), seen: tallies(params) },
    extras: Object.fromEntries(FEATURES.map((name) => [name, start(name)])) as Record<Feature, number>,
    logRatio: 0,
    lambda: {},
    lambdaExperienced: 1,
    mu: 1,
    bookings: 0,
    drops: 0,
    delivered: 0,
    late: 0,
    warned: [],
  }
}

const tallies = (params: FeeParams): Tally[] => params.priors.hazard.leadHours.map(() => ({ booked: 0, expected: 0 }))
