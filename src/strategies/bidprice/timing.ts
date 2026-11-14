/** postTiming: when to post an order's first gig. RULES.md: a driver books a gig for a later day only when they know
 * they will work that day, and most know only the next day; HANDBOOK.md: a driver hears of each order once, reads no
 * notification from 23:00 to 07:00, and a gig that ages on the board books worse. So an order whose first pickup is
 * two or more days away is held until `postHour` on `postDaysAhead` days before the pickup day, never at night, and
 * never later than `postLeadHours` before the last pickup; an order won after that moment posts at once. A pure
 * function of the order and the minute it was won, so a rebuild holds the same orders. */
import type { Order } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, dayOf, HOUR } from '../../ops/calendar.ts'

export type TimingParams = { postHour: number; postDaysAhead: number; postLeadHours: number }

/** No driver reads a notification from 23:00 to 07:00. */
const NIGHT_FROM = 23 * HOUR
const NIGHT_TO = 7 * HOUR

/** The minute to post the order's first gig, won at `wonAt`: `wonAt` itself when nothing is held. */
export function firstPostAt(order: Order, wonAt: number, p: TimingParams): number {
  try {
    const leg = order.legs.findIndex((_, i) => order.deliveredAt[i] == null)
    if (leg < 0) return wonAt
    const ready = order.legs[leg]!.pickup.window.from
    if (dayOf(ready) - dayOf(wonAt) < 2) return wonAt
    let at = (dayOf(ready) - p.postDaysAhead) * DAY + p.postHour * HOUR
    at = Math.min(at, order.lastPickupAt - p.postLeadHours * HOUR)
    // Never at night: back to 22:59 of the evening before.
    const inDay = ((at % DAY) + DAY) % DAY
    if (inDay < NIGHT_TO) at = at - inDay - (DAY - NIGHT_FROM) - 1
    else if (inDay >= NIGHT_FROM) at = at - inDay + NIGHT_FROM - 1
    return Number.isFinite(at) && at > wonAt ? at : wonAt
  } catch {
    return wonAt
  }
}
