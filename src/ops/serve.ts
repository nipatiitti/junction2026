/** Whether we can deliver a request's option on time, before we quote it, so a strategy declines it or quotes a
 * slower option instead of winning a late order. Two checks:
 * - the slack of strategies/admission (`option_slack`): the deadline less the ready time (at least an hour from
 *   now) and the drive, against the 5 hours that its thresholds were tuned for;
 * - whether the car can arrive at all, as the world decides it: collected when it is ready, released and its site
 *   open, delivered while the delivery site is open, by the deadline (moved by a later ready time) and by the
 *   note's deadline. This replaces the note check of `Desk.quote`, and it is a hard limit only: on the saved weeks,
 *   asking the 5 hours of it declined 165 cars that arrived on time for 1 that was late. */
import type { DeliveryOption, PriceRequest } from '../../vendor/spread-typescript/types.ts'
import { dayOf, HOUR, nextOpen, shiftByBusinessDays } from './calendar.ts'
import { charging, needsCharging } from './charging.ts'
import { lowBattery } from './gig.ts'
import { type Context, driveMinutes, minutes } from './map.ts'
import { NO_FACTS, type NoteFacts, readNote } from './note.ts'

/** A driver needs at least this long from now to see the gig and reach the pickup. */
export const LEAD = HOUR
/** An option needs this much time to spare beyond the work, or we do not offer it (strategies/admission). */
export const MIN_SLACK = 5 * HOUR
/** The earliest option with this much to spare is the one to quote. */
export const COMFORTABLE_SLACK = 9 * HOUR
/** Fetching transfer plates and a charging stop, in minutes (RULES.md, "Gigs"). */
export const PLATES_MINUTES = 30
export const CHARGING_MINUTES = 40

/** The verdict on one option. `slack` is admission's minutes to spare beyond the drive; -Infinity when the car
 * cannot arrive on time at all. */
export type Service = { ok: boolean; slack: number; reason: string }

/** Whether we can deliver `option` of `request` on time, with the slack that admission asks for. A request it
 * cannot read is declined. */
export function canServe(request: PriceRequest, option: DeliveryOption, now: number, context: Context): Service {
  try {
    return judge(request, option, now, context, readNote(request.note, request.arrivedAt))
  } catch {
    return { ok: false, slack: -Infinity, reason: 'cannot read the request' }
  }
}

/** The option to quote, or null to decline: the earliest that leaves a comfortable slack, else the last one that
 * we can serve. Up to level 3 every quote wins the request's first option, whichever option it prices, so there
 * only the first option counts (issues #108 and #116). A request it cannot read is declined. */
export function pickOption(request: PriceRequest, now: number, context: Context): DeliveryOption | null {
  try {
    const facts = readNote(request.note, request.arrivedAt)
    const options = (context.level ?? 8) <= 3 ? request.options.slice(0, 1) : request.options
    const served = options
      .map((option) => ({ option, ...judge(request, option, now, context, facts) }))
      .filter((verdict) => verdict.ok)
    const comfortable = served.find((verdict) => verdict.slack >= COMFORTABLE_SLACK / tightening(context))
    return (comfortable ?? served.at(-1))?.option ?? null
  } catch {
    return null
  }
}

/** Admission widens its limits as it tightens: 1 at the on-time target, 0.25 at the delivery minimum. */
const tightening = (context: Context): number => {
  const value = context.tightening ?? 1
  return Number.isFinite(value) ? Math.min(1, Math.max(0.25, value)) : 1
}

function judge(
  request: PriceRequest,
  option: DeliveryOption,
  now: number,
  context: Context,
  facts: NoteFacts,
): Service {
  const finish = earliestFinish(request, now, context, facts)
  const stated = request.legs[0]?.pickup.window.from ?? now
  // A car ready a day or more later than the request says moves the deadline by the same days.
  const deadline = shiftByBusinessDays(option.deadline, dayOf(stated), dayOf(Math.max(stated, facts.readyAt ?? 0)))
  if (!(finish.all <= deadline)) return { ok: false, slack: -Infinity, reason: 'cannot arrive by the deadline' }
  if (facts.deadline !== null && !(finish.first <= facts.deadline))
    return { ok: false, slack: -Infinity, reason: "cannot arrive by the note's deadline" }
  const ready = Math.max(now + LEAD, ...request.legs.map((leg) => leg.pickup.window.from))
  const slack = option.deadline - ready - driveMinutes(context.map, request.legs)
  const needed = MIN_SLACK / Math.max(tightening(context), 0.5)
  const spare = `${(slack / HOUR).toFixed(1)} h to spare`
  return slack >= needed
    ? { ok: true, slack, reason: spare }
    : { ok: false, slack, reason: `${spare}, ${needed / HOUR} h needed` }
}

/** When a driver who leaves now can deliver the first car, and all of them, one after the other: collected when
 * the car is ready, released and its site open, delivered when the delivery site is open (a car left at a closed
 * site counts when it opens). A private seller's slot that has ended by then never extends: Infinity. */
function earliestFinish(
  request: PriceRequest,
  now: number,
  context: Context,
  facts: NoteFacts,
): { first: number; all: number } {
  let at = now + LEAD
  let first = Infinity
  let here: string | undefined
  request.legs.forEach(({ car, pickup, delivery }, leg) => {
    const noted = leg === 0 ? facts : NO_FACTS
    if (here !== undefined) at += minutes(context.map, here, pickup.placeId)
    at = Math.max(at, pickup.window.from, noted.readyAt ?? 0, noted.releasedAt ?? 0)
    if (leg === 0 && pickup.privateAddress && at > pickup.window.to) at = Infinity
    at = nextOpen(at, pickup.hours, noted.pickupHours)
    at += minutes(context.map, pickup.placeId, delivery.placeId)
    const charge = needsCharging(car, pickup.placeId, delivery.placeId, context)
    if (lowBattery(car) && !charge) charging.quotesSpared++
    at += (noted.plates ? PLATES_MINUTES : 0) + (charge ? CHARGING_MINUTES : 0)
    at = nextOpen(at, delivery.hours, noted.deliveryHours)
    if (leg === 0) first = at
    here = delivery.placeId
  })
  return { first, all: request.legs.length > 0 ? at : Infinity }
}
