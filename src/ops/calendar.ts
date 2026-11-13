/** World time: whole minutes from Monday 00:00 of the first week. Day 0 is that Monday. */
import type { OpeningHours } from '../../vendor/spread-typescript/types.ts'

export const HOUR = 60
export const DAY = 24 * HOUR
export const SATURDAY = 5
export const SUNDAY = 6

export const dayOf = (minute: number): number => Math.floor(minute / DAY)
export const weekday = (day: number): number => ((day % 7) + 7) % 7
export const isWeekend = (day: number): boolean => weekday(day) >= SATURDAY

/** A site's weekday hours as a note gives them, in minutes from midnight. A missing side keeps the stated value. */
export type Hours = { opens?: number; closes?: number }

/** The opening and closing minute of a site on a day, from midnight, or null when it is closed all day. A note
 * changes the weekday hours only: Saturday keeps its stated hours (the reveals show notes never change them). */
export function openOn(day: number, hours: OpeningHours, real: Hours | null = null): [number, number] | null {
  if (weekday(day) === SATURDAY) return hours.saturday ? [hours.saturday.opens, hours.saturday.closes] : null
  if (!hours.weekdays.includes(weekday(day))) return null
  return [real?.opens ?? hours.opens, real?.closes ?? hours.closes]
}

/** The first minute from `at` on when the site is open: `at` itself at a private address (no hours), and
 * Infinity when it does not open within two weeks. A site is closed from its closing minute on. */
export function nextOpen(at: number, hours: OpeningHours | null, real: Hours | null = null): number {
  if (!hours || !Number.isFinite(at)) return at
  for (let day = dayOf(at); day < dayOf(at) + 14; day++) {
    const open = openOn(day, hours, real)
    if (!open) continue
    const from = Math.max(at, day * DAY + open[0])
    if (from < day * DAY + open[1]) return from
  }
  return Infinity
}

/** The deadline moved by as many business days as there are from `fromDay` to `toDay`: a car ready a day or more
 * later than the request says moves the order's deadline (RULES.md, "Your account"). The saved weeks show one
 * day for one day; across a weekend the shift counts business days, which is the earlier of the two readings. */
export function shiftByBusinessDays(deadline: number, fromDay: number, toDay: number): number {
  let shift = 0
  for (let day = fromDay + 1; day <= toDay; day++) if (!isWeekend(day)) shift++
  let day = dayOf(deadline)
  while (shift > 0) {
    day++
    if (!isWeekend(day)) shift--
  }
  return day * DAY + (deadline - dayOf(deadline) * DAY)
}
