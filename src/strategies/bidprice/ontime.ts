/** `onTimeOps`: most late orders are gigs that sat open with few views until past their last pickup. From
 * `onTimeLeadHours` before the last pickup, an open gig that no driver holds goes at once to at least `onTimeFee` ×
 * typical (never over three prices) and climbs from there, instead of waiting for its schedule to end. */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import type { FeeGig } from '../../models/fees/index.ts'
import { HOUR } from '../../ops/index.ts'
import { climb, higher } from './fees.ts'
import type { BidPriceParams } from './params.ts'

type P = Pick<BidPriceParams, 'onTimeOps' | 'onTimeLeadHours' | 'onTimeFee' | 'climbStep' | 'climbTop'>

/** The push fee for this gig now, or 0 when the gig needs no push. */
export function pushFee(gig: FeeGig, fee: number, now: number, p: P): number {
  if (!p.onTimeOps || gig.lastPickupAt - now > p.onTimeLeadHours * HOUR) return 0
  const target = Math.min(p.onTimeFee * gig.typicalCents, 3 * gig.priceCents)
  return target > fee * 1.01 ? Math.round(target) : 0
}

/** `schedule` raised to the push fee from now, climbing from there. */
export function pushed(schedule: FeeStep[], gig: FeeGig, target: number, now: number, p: P, level: number): FeeStep[] {
  return higher(schedule, climb(target, now, gig, p, level), level)
}
