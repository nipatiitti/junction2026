/** Price posture (`posture`): the cost scale follows the world's spare driver capacity instead of a fixed
 * `costScale`. It starts from the roster against `postureRoster` (a world with more drivers starts lower), then
 * rises with the won orders that wait for a booking over `postureComfort` and with the deadline warnings of the last
 * day over the orders won in it, the late brake. Only the late brake and the backlog push it up, so it never fights
 * the on-time controller `mu`, which also raises the cost when lateness rises. A pure function of the observed
 * events, so a rebuild gives the same scale. */
import type { DeskEvent } from '../../../vendor/spread-typescript/spread.ts'

export type PostureParams = {
  posture: boolean
  postureMin: number
  postureMax: number
  postureStart: number
  /** The roster size of an average level-8 world, and how far the start moves per 1 of roster share over it. */
  postureRoster: number
  postureRosterK: number
  /** Won orders not yet booked that are comfortable; each one over adds `postureLoadK`. */
  postureComfort: number
  postureLoadK: number
  /** Deadline warnings over the orders won, in the last day: the scale adds `postureWarnK` × that share. */
  postureWarnK: number
}

export type Posture = {
  start: number
  waiting: Set<string>
  wins: number[]
  warns: number[]
  /** The scale at the end of each day seen, for the summary. */
  days: number[]
  day: number
}

const DAY = 1440

export function newPosture(drivers: number, p: PostureParams): Posture {
  const start = p.postureStart - p.postureRosterK * (drivers / p.postureRoster - 1)
  return { start, waiting: new Set(), wins: [], warns: [], days: [], day: 0 }
}

export function observePosture(
  s: Posture,
  event: DeskEvent,
  gigOrder: (gigId: string) => string | undefined,
  p: PostureParams,
): void {
  while (event.at >= (s.day + 1) * DAY) {
    s.days.push(postureScale(s, (s.day + 1) * DAY, p))
    s.day++
  }
  if (event.kind === 'order_won') {
    s.waiting.add(event.order.id)
    s.wins.push(event.at)
  } else if (event.kind === 'gig_booked') {
    const order = gigOrder(event.gigId)
    if (order) s.waiting.delete(order)
  } else if (event.kind === 'order_cancelled') s.waiting.delete(event.orderId)
  else if (event.kind === 'deadline_close') s.warns.push(event.at)
}

export function postureScale(s: Posture, now: number, p: PostureParams): number {
  const since = now - DAY
  const wins = s.wins.filter((t) => t > since).length
  const warns = s.warns.filter((t) => t > since).length
  const load = Math.max(0, s.waiting.size - p.postureComfort) * p.postureLoadK
  const warn = wins > 0 ? (warns / wins) * p.postureWarnK : 0
  return Math.min(p.postureMax, Math.max(p.postureMin, s.start + load + warn))
}

export const POSTURE_DEFAULTS: PostureParams = {
  posture: false,
  postureMin: 1,
  postureMax: 1.25,
  postureStart: 1.15,
  postureRoster: 670,
  postureRosterK: 2,
  postureComfort: 15,
  postureLoadK: 0.005,
  postureWarnK: 1,
}
