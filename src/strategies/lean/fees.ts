/** Fee schedules. The measured facts: the lowest fee that books a gig within three hours is 0.76 × the typical fee
 * at the median, and two bookers in three had seen the gig before at a lower fee and waited for the rise. So a gig
 * holds one fee and raises it a few times over the hours in which drivers plan its day (`stepped`); a chain holds
 * and then creeps (`slow`); and only when the time runs out does a fee climb fast (`fast`). Every time in a
 * schedule counts waking minutes: a raise at night shows to nobody. Fees are ratios of the gig's typical fee until
 * `schedule` turns them into cents. */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, HOUR } from '../../ops/index.ts'

/** The slow schedule holds its opening fee for half of the time a gig has, this long at most. */
const HOLD = 6 * HOUR
/** After the hold, the fee creeps on to this × typical when four fifths of the time are gone, in at most this many
 * steps, this many minutes apart or more. None of the three is measured: with `chainPatience` a chain leaves the
 * app before its first step. */
const LAST = 1.3
const CREEP_BY = 0.8
const CREEP_STEPS = 10
const STEP = 20
/** Drivers read the app between these minutes of the day. The rules say 07:00 to 23:00; late orders found their
 * driver "in the evening", so the planning day ends at 21:00 here. */
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

/** The slow schedule from `now`, for chains: `open` × typical for half of the awake time to `bookBy` (HOLD at most),
 * then up to LAST when CREEP_BY of the time is gone. */
export function slow(now: number, typical: number, bookBy: number, open: number): FeeStep[] {
  const time = awake(now, bookBy)
  const points: [number, number][] = [[now, open]]
  const [begin, end, last] = [Math.min(time / 2, HOLD), CREEP_BY * time, Math.max(open, LAST)]
  const steps = last > open ? Math.min(CREEP_STEPS, Math.floor((end - begin) / STEP)) : 0
  for (let i = 1; i <= steps; i++)
    points.push([later(now, begin + ((end - begin) * i) / steps), open + ((last - open) * i) / steps])
  return schedule(points, typical)
}

/** What `stepped` needs: the opening fee, the early fee (0 for none), each raise as the share of the planning time
 * after which it comes and the fee it raises to, the top, and the jitter (0 to 1). All fees × typical. */
export type Steps = { open: number; early: number; raises: [number, number][]; top: number; jitter: number }

/** With `jitter` 1 a raise moves by up to half of this many minutes either way and by up to half of this share in
 * size, drawn from the gig's seed, so that drivers cannot time a second look. */
const JITTER_MINUTES = 40
const JITTER_SIZE = 0.1
/** The raises take at most this many waking minutes before `planBy` (two days): a gig far ahead holds its opening
 * fee until then. */
const PLAN_AHEAD = 28 * HOUR
/** A gig for a later day shows its early fee for this many waking minutes: the cheapest driver for tomorrow needs
 * less than the opening fee, and takes about that long to see it. */
const EARLY = 60
/** A gig that drivers plan the evening before gets its top at 07:00 on the day, and this long before its last
 * pickup at the latest. */
const TOP_AHEAD = 3 * HOUR

/** The stepped schedule from `now`: the opening fee (never under `shown`, the fee the car showed before), each raise
 * after its share of the waking time that drivers have to plan the gig (`planBy`), and the top when that time is
 * over. A driver who looks twice sees the same fee, so waiting for a rise pays only near the end. A raise whose
 * time has passed folds into the opening; the caller does not use this schedule when the planning time is over. */
export function stepped(
  now: number,
  typical: number,
  lastPickup: number,
  shown: number,
  seed: string,
  { open, early, raises, top, jitter }: Steps,
): FeeStep[] {
  const random = rng(seed)
  const points: [number, number][] = [[now, Math.max(open, shown)]]
  // Only a gig that has shown no fee yet: a driver who gave a gig back books it only for more.
  if (early > 0 && early < open && shown <= 0 && Math.floor(lastPickup / DAY) > Math.floor(now / DAY)) {
    points[0] = [now, early]
    points.push([later(now, EARLY), open])
  }
  const plan = planBy(now, lastPickup)
  const left = awake(now, plan)
  const time = Math.min(left, PLAN_AHEAD)
  const from = later(now, left - time)
  const add = (at: number, to: number) => {
    if (at <= now) points[0] = [now, Math.max(points[0]?.[1] ?? 0, to)]
    else points.push([at, to])
  }
  for (const [share, ratio] of raises) {
    // Each gig raises at its own minutes and by its own size.
    const shift = (random() - 0.5) * JITTER_MINUTES * jitter
    const size = 1 + (random() - 0.5) * JITTER_SIZE * jitter
    add(later(from, share * time) + shift, ratio * size)
  }
  // The top at `plan` on the day itself, or at 07:00 on the day for a gig that drivers plan the evening before.
  const evening = plan <= lastPickup - PLAN_LATE - HOUR
  add(evening ? Math.min(later(plan, 1), lastPickup - TOP_AHEAD) : plan, top)
  return schedule(
    points.sort((a, b) => a[0] - b[0]),
    typical,
  )
}

/** The minute by which a gig should have its driver. Drivers plan a day the evening before: 53 of 103 late orders
 * of five server weeks had a last pickup before 16:00, got their raises that morning and found a driver only in
 * the evening after. So a gig to collect before PLAN_MORNING should book by 21:00 the evening before, and a later
 * one PLAN_LATE before its last pickup. With under PLAN_EVENING waking minutes of that evening left, PLAN_GONE
 * before the last pickup. Only the 16:00 is measured. */
const PLAN_MORNING = 16 * HOUR
const PLAN_LATE = 5 * HOUR
const PLAN_GONE = 3 * HOUR
const PLAN_EVENING = HOUR
export function planBy(now: number, lastPickup: number): number {
  const evening = Math.floor(lastPickup / DAY) * DAY - (DAY - SLEEP)
  if (lastPickup % DAY >= PLAN_MORNING) return lastPickup - PLAN_LATE
  return awake(now, evening) >= PLAN_EVENING ? evening : lastPickup - PLAN_GONE
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

/** A fast climb has at most this many steps. */
const MAX_FAST = 40

/** The fast schedule from `now`: `open` × typical at once, then `step` × typical more every `every` waking minutes
 * up to `cap` × typical. */
export function fast(now: number, typical: number, open: number, step: number, every: number, cap: number): FeeStep[] {
  const points: [number, number][] = []
  const first = Math.min(open, cap)
  for (let i = 0; i < MAX_FAST; i++) {
    const ratio = Math.min(cap, first + i * step)
    points.push([i === 0 ? now : later(now, i * every), ratio])
    if (ratio >= cap) break
  }
  return schedule(points, typical)
}

/** Whole steps in time order whose fee never falls, 48 at most (the API's limit). */
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
