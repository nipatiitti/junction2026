/** The booking hazard: bookings per open daytime hour of a gig, by its fee, the hours to its last pickup and
 * whether drivers have seen it (finding 8), times what the week has taught. */
import { DAY, HOUR } from '../../time.ts'
import { clamp, type FeeParams } from './params.ts'
import type { FeeState } from './state.ts'

const WAKE = 7 * HOUR // drivers read the app from 07:00
const SLEEP = 23 * HOUR // to 23:00

/** The band of hours to the last pickup that `leadMinutes` falls in. */
export function bandOf(leadMinutes: number, params: FeeParams): number {
  const { leadHours } = params.priors.hazard
  let band = 0
  while (band + 1 < leadHours.length && leadMinutes >= leadHours[band + 1] * HOUR) band++
  return band
}

/** The prior: the table of src/params/fees.json, linear in the fee between its points, zero at no fee, flat
 * above the last point, and stepped in bands of the hours to the last pickup. `fee` is over the expected fee. With
 * `hazardFit`, a seen gig follows the fresh row's shape too (the brief: "a fifth of it once viewed"), and each band
 * and state takes its fitted scale, so a raise helps a seen gig and short leads are not overrated. */
export function priorHazard(fee: number, leadMinutes: number, seen: boolean, params: FeeParams): number {
  const { feeGrid, fresh, seen: viewed, fit } = params.priors.hazard
  const band = bandOf(leadMinutes, params)
  const fitted = params.flags.hazardFit && fit !== undefined
  const scale = fitted ? ((seen ? fit.seen : fit.fresh)[band] ?? 1) : 1
  return scale * shape(fee, (seen && !fitted ? viewed : fresh)[band], feeGrid)
}

/** A row of the table at `fee`. */
function shape(fee: number, row: number[], feeGrid: number[]): number {
  if (!(fee > 0)) return 0
  if (fee <= feeGrid[0]) return (row[0] * fee) / feeGrid[0]
  for (let i = 1; i < feeGrid.length; i++) {
    if (fee <= feeGrid[i]) {
      const t = (fee - feeGrid[i - 1]) / (feeGrid[i] - feeGrid[i - 1])
      return row[i - 1] + t * (row[i] - row[i - 1])
    }
  }
  return row[row.length - 1]
}

/** What the week has taught: bookings seen over bookings the prior expected in the same lead band and state,
 * starting from the prior. */
export function hazardScale(seen: boolean, leadMinutes: number, state: FeeState, params: FeeParams): number {
  const tally = (seen ? state.hazard.seen : state.hazard.fresh)[bandOf(leadMinutes, params)]
  const { booked, expected } = tally ?? { booked: 0, expected: 0 }
  const k = params.learn.pseudoBookings
  return clamp((k + booked) / (k + expected), params.learn.hazardScale)
}

/** Bookings per open daytime hour at `fee` over the expected fee, `leadMinutes` before the last pickup. */
export function acceptHazard(fee: number, leadMinutes: number, seen: boolean, state: FeeState, params: FeeParams) {
  return priorHazard(fee, leadMinutes, seen, params) * hazardScale(seen, leadMinutes, state, params)
}

/** The share of bookings that a driver drops or misses, learned from the prior rate. */
export function dropShare(state: FeeState, params: FeeParams): number {
  const { drop, noShow } = params.priors.rates
  const k = params.learn.dropPseudo
  return Math.min(0.9, (k * (drop + noShow) + state.drops) / (k + state.bookings))
}

/** The hazard at `at` over the daytime one: drivers rarely look at night or at the weekend. */
export function clockFactor(at: number, params: FeeParams): number {
  const { night, weekend } = params.priors.hazard
  const minute = at % DAY
  return (minute < WAKE || minute >= SLEEP ? night : 1) * (Math.floor(at / DAY) % 7 >= 5 ? weekend : 1)
}

/** A stretch of a gig's open time, short enough that its fee, lead band and clock hold. */
export type Slice = {
  at: number
  hours: number
  lead: number // minutes to the last pickup at its start
  clock: number // clockFactor
  fresh: number // the share of it that is fresh
}

/** The first daytime minute at or after `at`. */
export function awake(at: number): number {
  const minute = at % DAY
  if (minute < WAKE) return at - minute + WAKE
  if (minute >= SLEEP) return at - minute + DAY + WAKE
  return at
}

/** The slices of [from, to), cut on the slice grid. A gig is fresh for its first `freshMinutes` of daytime
 * from `freshFrom` (its post, or its first view); `freshFrom` null means seen throughout. */
export function slicesOf(
  from: number,
  to: number,
  lastPickupAt: number,
  freshFrom: number | null,
  params: FeeParams,
): Slice[] {
  const size = params.plan.sliceMinutes
  const freshStart = freshFrom === null ? Infinity : awake(freshFrom)
  const freshEnd =
    freshFrom === null
      ? Infinity
      : Math.min(freshStart + params.plan.freshMinutes, freshStart - (freshStart % DAY) + SLEEP)
  const slices: Slice[] = []
  for (let at = from; at < to; ) {
    const end = Math.min(to, (Math.floor(at / size) + 1) * size)
    const overlap = Math.max(0, Math.min(end, freshEnd) - Math.max(at, freshStart))
    slices.push({
      at,
      hours: (end - at) / HOUR,
      lead: lastPickupAt - at,
      clock: clockFactor(at, params),
      fresh: overlap / (end - at),
    })
    at = end
  }
  return slices
}
