/** flatFees: drivers learn our gigs rise "the booked fee over the first fee that a driver viewed", and a repost at a
 * higher fee counts as a raise (HANDBOOK.md, "How drivers learn"). So one fee held flat from posting to
 * `flatUntilHours` before the last pickup, `flatOpen` × the solver's expected fee, then one step to `flatTop` ×
 * typical. A repost of the same cars keeps the per-car flat fee of the order's first gig, read back from our log. */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import type { FeeGig } from '../../models/fees/index.ts'
import { HOUR } from '../../ops/index.ts'
import type { OurGig } from './log.ts'
import type { BidPriceParams } from './params.ts'

export const flatCount = { posted: 0, kept: 0, skipped: 0 }

/** The flat fee of an order's earlier gig, per car: the first step of the first gig we posted for it. */
function earlierPerCar(gigs: ReadonlyMap<string, OurGig>, orderId: string): number | undefined {
  for (const gig of gigs.values())
    if (gig.orderId === orderId && gig.legs.length > 0 && gig.schedule[0])
      return gig.schedule[0].feeCents / gig.legs.length
  return undefined
}

/** The flat schedule for `gig` from `now`, given the solver's expected fee for it. */
export function flatSchedule(
  gig: FeeGig,
  now: number,
  expectedFeeCents: number,
  legs: number,
  orderId: string,
  gigs: ReadonlyMap<string, OurGig>,
  p: Pick<BidPriceParams, 'flatOpen' | 'flatUntilHours' | 'flatTop'>,
  level: number,
): FeeStep[] {
  const earlier = earlierPerCar(gigs, orderId)
  const cap = Math.max(1, 3 * gig.priceCents)
  let fee = Math.min(cap, p.flatOpen * expectedFeeCents)
  if (earlier !== undefined) {
    fee = earlier * legs
    flatCount.kept++
  } else flatCount.posted++
  fee = Math.max(1, Math.round(fee))
  const top = Math.round(Math.min(cap, Math.max(fee, p.flatTop * gig.typicalCents)))
  const topAt = Math.round(gig.lastPickupAt - p.flatUntilHours * HOUR)
  const start = Math.round(now)
  if (level === 1 || topAt <= start) return [{ at: start, feeCents: topAt <= start ? top : fee }]
  return top > fee
    ? [
        { at: start, feeCents: fee },
        { at: topAt, feeCents: top },
      ]
    : [{ at: start, feeCents: fee }]
}
