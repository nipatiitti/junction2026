/** The fee extras: one learned multiplier on the typical fee for each feature of a gig (findings 9 and 10). */
import type { Leg } from '../../../vendor/spread-typescript/types.ts'
import { DAY } from '../../time.ts'
import { clamp, FEATURES, type Feature, type FeeParams } from './params.ts'
import type { FeeState } from './state.ts'

export type Features = Record<Feature, boolean>

/** The features of the cars `legs` of an order due at `deadline`, posted at `at`. `fewDriversNear` comes from
 * `fewDriversNear` in supply.ts, for the delivery place. */
export function featuresOf(legs: Leg[], deadline: number, at: number, fewDriversNear: boolean): Features {
  return {
    privatePickup: legs.some((leg) => leg.pickup.privateAddress),
    privateDelivery: legs.some((leg) => leg.delivery.privateAddress),
    tradeIn: legs.length > 1,
    premium: legs.some((leg) => leg.car.premium),
    weekendDelivery: Math.floor(deadline / DAY) >= 5, // due after Friday: the drive is on Saturday or the next Monday
    postedFriday: Math.floor(at / DAY) === 4,
    fewDriversNear,
  }
}

export const featureList = (features: Features): Feature[] => FEATURES.filter((name) => features[name])

/** The product of the multipliers of the gig's features; 1 with the extras flag off. */
export function feeExtra(features: Features, state: FeeState, params: FeeParams): number {
  if (!params.flags.extras) return 1
  return featureList(features).reduce((product, name) => product * clamp(state.extras[name], params.learn.extras), 1)
}
