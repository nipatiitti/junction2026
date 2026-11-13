/** Turns a note's facts into stop windows, so a driver arrives when the car can be collected and delivers by the
 * note's deadline, inside the real opening hours. A port of strategies/notes/plan.py. */
import type { ForecastEvent, OpeningHours, TimeWindow } from '../../vendor/spread-typescript/types.ts'
import { DAY, dayOf, HOUR, openOn } from './calendar.ts'
import type { NoteFacts } from './note.ts'
import { earliestPickup } from './note.ts'

/** Real drives vary around the road minutes, and a site is closed from its closing minute on: a window inside real
 * hours ends this long before closing, and a day with less than this left after the start is skipped. */
export const MARGIN = HOUR

/** Snow announced by a `forecast` event: the places and the minutes it falls there. */
export type Snowfall = Pick<ForecastEvent, 'from' | 'to' | 'placeIds'>

/** The snowfalls at any of the places. */
export const snowAt = (forecasts: readonly Snowfall[], places: readonly string[]): Snowfall[] =>
  forecasts.filter((snow) => snow.placeIds.some((place) => places.includes(place)))

/** The first minute from `start` on that is not inside a snowfall. */
export function afterSnow(start: number, snow: readonly Snowfall[]): number {
  for (let moved = true; moved; ) {
    moved = false
    for (const { from, to } of snow)
      if (from <= start && start < to) {
        start = to
        moved = true
      }
  }
  return start
}

/** The pickup window that the note needs from `now` on, or null when the order's own window will do.
 * - The car is ready, or released after payment, at the note's earliest pickup, and not before `notBefore`.
 * - When the note gives the site's real hours, the window is one day inside them: the first day from the start on
 *   when the site is open for long enough, ending `MARGIN` before closing. The driver plans by the stated hours, so
 *   a longer window could bring them after the real closing time.
 * - A car on summer tyres cannot be collected while snow falls at either end: the window starts after it. */
export function pickupWindow(
  stated: TimeWindow,
  hours: OpeningHours | null,
  facts: NoteFacts,
  now: number,
  notBefore = 0,
  snow: readonly Snowfall[] = [],
): TimeWindow | null {
  let earliest = Math.max(earliestPickup(facts) ?? 0, notBefore)
  if (facts.summerTyres && snow.length > 0) earliest = afterSnow(Math.max(earliest, now, stated.from), snow)
  const real = hours ? facts.pickupHours : null
  if (earliest <= now && !real) return null // the car is ready by now, and the stated hours are the real ones
  const start = Math.max(stated.from, earliest, now)
  if (hours && real) {
    for (let day = dayOf(start); day < dayOf(start) + 14; day++) {
      const open = openOn(day, hours, real)
      if (!open) continue
      const from = Math.max(start, day * DAY + open[0])
      const to = day * DAY + open[1] - MARGIN
      if (to - from >= MARGIN) return { from, to }
    }
    return null
  }
  // A window moved past the stated one (a retry after it ended) stays open a day, so a driver can still book it.
  return start <= stated.from ? null : { from: start, to: Math.max(stated.to, start + DAY) }
}

/** The delivery window by the note: it ends at a tighter deadline, and `MARGIN` before the real closing time on its
 * last day, so the driver does not arrive after closing and wait. It never ends before it starts. */
export function deliveryWindow(base: TimeWindow, hours: OpeningHours | null, facts: NoteFacts): TimeWindow {
  let end = Math.min(base.to, facts.deadline ?? Infinity)
  const open = hours && facts.deliveryHours ? openOn(dayOf(end), hours, facts.deliveryHours) : null
  if (open) end = Math.min(end, dayOf(end) * DAY + open[1] - MARGIN)
  return end >= base.from ? { from: base.from, to: end } : base
}
