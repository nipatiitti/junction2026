/** The planned raises of a single-car gig from a table (`feeTable`), in place of `open`, `early` and the three
 * raises of the params. `analysis/lean_fee_table.py` writes the table (feetable.json): it fits, on the saved weeks
 * and the fee probes, the chance that a gig has found its driver by a share of its planning time at a fee, and
 * solves a dynamic program over (share of the planning time, fee shown) for each class of gig and kind of pickup
 * day. The schedule is still built by `stepped` (fees.ts), so the planning time, the jitter, the weekend rule and
 * the top are the same; the urgent and the late climb do not use the table. */
import { readFileSync } from 'node:fs'
import { DAY, HOUR } from '../../ops/index.ts'
import { awake, planBy, rested, type Steps } from './fees.ts'

/** [the early fee or 0, the opening fee, then [share of the planning time, fee] for each raise], fees × typical. */
type Entry = [number, number, ...[number, number][]]
type Table = { table: Record<string, Entry> }

/** As in fees.ts (`PLAN_AHEAD`, `PLAN_GONE`) and in the fit (`SHORT`). */
const PLAN_AHEAD = 28 * HOUR
const PLAN_GONE = 3 * HOUR
const SHORT = 6 * HOUR

let loaded: Table | undefined
const load = (): Table => {
  loaded ??= JSON.parse(readFileSync(new URL('./feetable.json', import.meta.url), 'utf-8')) as Table
  return loaded
}

/** The class of a gig posted at `now` (`gig_class` of the fit). A: collected today, with under six hours to plan.
 * B: today, with more. C: planned by 21:00 the evening before, posted that day. D: posted the day before, planned
 * on the day. E: posted earlier. F: posted over 28 waking hours before the end of its planning time, so it holds
 * its opening fee first. A gig that raises on the Monday after the weekend (`rest`) plans on that day: A or B. */
export function classOf(now: number, lastPickup: number, rest: boolean): string {
  const start = rest ? rested(now, lastPickup) : undefined
  const usual = planBy(now, lastPickup)
  if (start !== undefined) {
    const plan = usual >= start ? usual : Math.max(start, lastPickup - PLAN_GONE)
    return plan - start < SHORT ? 'A' : 'B'
  }
  const left = awake(now, usual)
  if (left > PLAN_AHEAD) return 'F'
  const lead = Math.floor(lastPickup / DAY) - Math.floor(now / DAY)
  if (lead <= 0) return left < SHORT ? 'A' : 'B'
  if (lead === 1) return usual < Math.floor(lastPickup / DAY) * DAY ? 'C' : 'D'
  return 'E'
}

/** The pickup day's kind: 0 Monday to Thursday, 1 Friday, 2 after the weekend. */
const weekOf = (lastPickup: number): number => {
  const day = Math.floor(lastPickup / DAY)
  return day < 4 ? 0 : day === 4 ? 1 : 2
}

/** The opening fee, the early fee and the raises of the table for a gig posted at `now`, for `stepped`; undefined
 * when the table has no entry, and the caller keeps its own. */
export function tableSteps(
  now: number,
  lastPickup: number,
  rest: boolean,
): Pick<Steps, 'open' | 'early' | 'raises'> | undefined {
  const entry = load().table[`${classOf(now, lastPickup, rest)}${weekOf(lastPickup)}`]
  if (!entry) return undefined
  const [early, open, ...raises] = entry
  return { early, open, raises }
}
