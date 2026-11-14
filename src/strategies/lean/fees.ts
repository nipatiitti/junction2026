/** Fee schedules. The measured fact: the lowest fee that books a gig within three hours is 0.76 × the typical fee
 * at the median, 0.59 to 1.02 for four gigs in five, and nothing but who happens to be free explains the rest. So a
 * gig opens low and climbs slowly through that range while drivers are awake, and pays what its own driver needs,
 * not what the dearest one does. Only when the time runs out does it climb fast. */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, HOUR } from '../../ops/index.ts'

/** The opening fee and the end of the slow climb, × typical. With both the same, the fee holds flat until the
 * creep: drivers who learn that our fees rise wait for the rise. */
export type Shape = { open: number; climbTo: number }
/** The slow climb takes this long, in minutes that drivers are awake; a gig with less time opens higher. */
export const CLIMB = 6 * HOUR
/** After the climb, the fee creeps on to this × typical, and from there to the top by the last minute to book. */
const LAST = 1.3
/** Minutes between two steps of the climb. */
const STEP = 20
/** Drivers read the app between these minutes of the day. */
const WAKE = 7 * HOUR
const SLEEP = 21 * HOUR
/** A gig needs a driver this long before its last pickup, to reach the car. */
export const BOOK_AHEAD = 90
/** With less time than this left to book, only a fast climb finds a driver. */
export const SHORT = 45

/** The minutes from `from` to `to` when drivers are awake. */
export function awake(from: number, to: number): number {
  let sum = 0
  for (let day = Math.floor(from / DAY); day <= Math.floor(to / DAY); day++)
    sum += Math.max(0, Math.min(to, day * DAY + SLEEP) - Math.max(from, day * DAY + WAKE))
  return sum
}

/** The minute that lies `minutes` awake minutes after `from`. */
function later(from: number, minutes: number): number {
  for (let day = Math.floor(from / DAY), left = minutes; day < Math.floor(from / DAY) + 30; day++) {
    const start = Math.max(from, day * DAY + WAKE)
    const room = day * DAY + SLEEP - start
    if (room <= 0) continue
    if (room >= left) return start + left
    left -= room
  }
  return from + minutes
}

/** The slow climb takes half of the time a gig has, CLIMB at most. */
const climbOf = (time: number): number => Math.min(time / 2, CLIMB)

/** The fee, × typical, that a gig opens at when it has `time` awake minutes to find its driver: `open` with a
 * full climb ahead, higher with less. */
export const openingFor = (time: number, shape: Shape): number =>
  shape.open + Math.max(0, shape.climbTo - 0.1 - shape.open) * Math.max(0, 1 - climbOf(time) / CLIMB)

/** The slow schedule from `now`: the opening fee until `from` (for a car that is ready days later), then up to
 * `climbTo` over the climb, on to LAST when four fifths of the time are gone, and to `top` at `bookBy`. One gig in ten
 * needs more than the climb gives, and it must find its driver before the last pickup, not at it. */
export function slow(
  now: number,
  typical: number,
  bookBy: number,
  shape: Shape,
  from = now,
  floor = 0,
  top = 2,
): FeeStep[] {
  const start = Math.max(now, from)
  const time = awake(start, bookBy)
  const open = Math.max(openingFor(time, shape), floor)
  const points: [number, number][] = [[now, open]]
  const phase = (begin: number, end: number, low: number, high: number, most: number, every: number) => {
    const steps = high > low ? Math.min(most, Math.floor((end - begin) / every)) : 0
    for (let i = 1; i <= steps; i++)
      points.push([later(start, begin + ((end - begin) * i) / steps), low + ((high - low) * i) / steps])
  }
  const climb = climbOf(time)
  const climbed = Math.max(open, shape.climbTo)
  phase(0, climb, open, climbed, 18, STEP)
  phase(climb, 0.8 * time, climbed, Math.max(climbed, LAST), 10, STEP)
  phase(0.8 * time, time, Math.max(climbed, LAST), Math.max(climbed, LAST, top), 12, 10)
  return schedule(points, typical)
}

/** The stepped schedule: the opening fee, then a raise only at a few fixed hours before the last pickup. A driver
 * who looks twice sees the same fee, so waiting for a rise pays only near the end. Steps that have passed fold into
 * the opening. */
const STEPS: [number, number][] = [
  [24, 1.05],
  [16, 1.25],
  [10, 1.55],
  [6, 2],
]
export function stepped(
  now: number,
  typical: number,
  lastPickup: number,
  open: number,
  floor = 0,
  jitter = 0,
  seed = '',
): FeeStep[] {
  const random = rng(seed)
  const points: [number, number][] = [[now, Math.max(open, floor)]]
  for (const [hours, ratio] of STEPS) {
    // Each gig raises at its own minutes and by its own size, so a driver cannot plan a second look for the raise.
    const at = lastPickup - hours * HOUR + (random() - 0.5) * 3 * HOUR * jitter
    const to = ratio * (1 + (random() - 0.5) * 0.1 * jitter)
    if (at <= now) points[0] = [now, Math.max(points[0]?.[1] ?? 0, to)]
    else points.push([at, to])
  }
  return schedule(points, typical)
}

/** A small seeded generator (mulberry32 over a string hash): the same numbers for the same seed, so a strategy
 * rebuilt in the final draws the same schedule. */
function rng(seed: string): () => number {
  let a = 0
  for (let i = 0; i < seed.length; i++) a = (Math.imul(a ^ seed.charCodeAt(i), 2654435761) + i) | 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** The fast schedule from `now`: `open` × typical at once, then `step` × typical more every `every` minutes up to
 * `cap` × typical. */
export function fast(now: number, typical: number, open: number, step: number, every: number, cap: number): FeeStep[] {
  const points: [number, number][] = []
  const first = Math.min(open, cap)
  for (let i = 0; i < 40; i++) {
    const ratio = Math.min(cap, first + i * step)
    points.push([now + i * every, ratio])
    if (ratio >= cap) break
  }
  return schedule(points, typical)
}

/** Whole steps in time order whose fee never falls, 48 at most. */
function schedule(points: [number, number][], typical: number): FeeStep[] {
  const steps: FeeStep[] = []
  for (const [minute, ratio] of points) {
    const at = Math.round(minute)
    const feeCents = Math.max(1, Math.round(ratio * typical), steps.at(-1)?.feeCents ?? 0)
    const last = steps.at(-1)
    if (last && at <= last.at) last.feeCents = feeCents
    else if (!last || feeCents > last.feeCents) steps.push({ at, feeCents })
  }
  return steps.slice(0, 48)
}

/** The fee that a schedule shows at `now`. */
export function feeAt(steps: readonly FeeStep[], now: number): number {
  let fee = steps[0]?.feeCents ?? 0
  for (const step of steps) if (step.at <= now) fee = step.feeCents
  return fee
}
