/** Pacing (the param `pace`): one price on capacity that a controller moves during the week, as a budget pacer
 * does in an ad auction. The budget is the drivers' capacity, the plan says how much of it the week should have
 * used by each hour, and the charge on every quote's cost rises when the week is ahead of the plan and falls when
 * it is behind.
 *
 * The plan is read from the 40 best weeks of ten server seeds (the four with the highest margin of the 14 saved
 * `lean` weeks of `supply-1` to `supply-10`, level 8, each at least 93% on time; mean €17,431, 96.9% on time):
 *
 * - Volume: 0.52 orders per driver over the week (0.46 to 0.58 by seed, and not related to the number of drivers),
 *   won in the shares of `DAY_SHARE`, evenly between 09:30 and 18:30 of each day.
 * - Fees: the mean of all bookings so far, × typical, is at `FEE_PLAN` at each midnight.
 * - Lateness: up to `LATE_PLAN` of the orders done.
 *
 * The plan's volume is not the same in every world: drivers are known at the start, their willingness is not. A
 * seed whose bookings paid 0.01 × typical over the plan at the planned volume had its best load 1.2% to 1.9% lower
 * (ten seeds, correlation −0.68 on Tuesday evening and −0.51 on Wednesday), so the fees paid move the target, and
 * so does a late share over the plan.
 *
 * Everything here is a function of the counts that `index.ts` feeds in the order of the events, so a rebuilt week
 * has the same charge. */
import { DAY, HOUR } from '../../ops/index.ts'

/** The orders per driver that the plan wins in a week. */
const LOAD_PLAN = 0.52
/** The share of the week's orders that the plan wins on each day, Monday to Friday. */
const DAY_SHARE = [0.227, 0.253, 0.185, 0.202, 0.133]
/** The minutes of a day between which the plan wins its orders, evenly (measured: 7% of a day's wins by 10:00,
 * 51% by 14:00, 92% by 18:00). */
const DAY_FROM = 9.5 * HOUR
const DAY_TO = 18.5 * HOUR
/** The mean fee of all bookings so far × typical, at the start of Monday and at each midnight from Tuesday on. */
const FEE_PLAN = [0.79, 0.81, 0.885, 0.916, 0.935, 0.955]
/** The fee mean starts as if this many bookings had paid the plan, so the first bookings of Monday move it little. */
const FEE_PRIOR = 20
/** What the target loses for each 1 × typical that bookings pay over the plan (measured: 1.2 to 1.9). */
const FEE_WEIGHT = 1.5
/** The late share of the plan, and what the target loses for each unit over it. The fit of supply and demand has
 * 0.143 of late share for each order per driver, which is 13 for a unit; 10 is a guess under it, not measured. */
const LATE_PLAN = 0.04
const LATE_WEIGHT = 10
/** The scarcity signals move the target by no more than this either way. */
const TARGET_LOW = 0.7
const TARGET_HIGH = 1.25
/** The miss is counted against the plan so far and this share of the week's plan, so that the few orders of Monday
 * morning cannot throw the charge: 0.1 is 40 orders in the median world. */
const PLAN_PRIOR = 0.1
/** The update: the charge is the plan's × exp(GAIN × `pace` × the miss), where the miss is the share by which the
 * orders won are over the target so far. With 2, a week 10% ahead pays 22% more for capacity. Not measured. */
const GAIN = 2
/** The charge stays between these × the plan's: with `taxLoad` 0.47 that is 0.12 to 0.49 of the cost, inside what
 * the server has played as a fixed `tax` (0.04 won 523 orders a week and 0.40 won 367), so no bound declines a day. */
const CHARGE_LOW = 0.5
const CHARGE_HIGH = 2

const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))

/** The days of the plan that are over at the minute `at`, with the part of the day it is in: 1.5 on Tuesday at
 * 14:00, 5 from Friday 18:30 on. */
function daysDone(at: number): number {
  const day = Math.floor(at / DAY)
  if (day >= DAY_SHARE.length) return DAY_SHARE.length
  return Math.max(0, day) + clamp((at - day * DAY - DAY_FROM) / (DAY_TO - DAY_FROM), 0, 1)
}

/** The share of the week's orders that the plan has won by the minute `at`. */
export function planShare(at: number): number {
  const done = daysDone(at)
  const day = Math.floor(done)
  let share = 0
  for (let d = 0; d < day; d++) share += DAY_SHARE[d] ?? 0
  return share + (DAY_SHARE[day] ?? 0) * (done - day)
}

/** The mean fee × typical that the plan's bookings have paid by the minute `at`. */
export function planFee(at: number): number {
  const done = daysDone(at)
  const day = Math.min(Math.floor(done), FEE_PLAN.length - 2)
  const from = FEE_PLAN[day] ?? 1
  const to = FEE_PLAN[day + 1] ?? from
  return from + (to - from) * (done - day)
}

export class Pacer {
  private readonly drivers: number
  private readonly gain: number
  private wins = 0
  private bookings = 0
  private ratios = 0
  /** The lowest and highest charge of the week × the plan's, and the last one, for the summary. */
  private low = 1
  private high = 1
  private last = 1
  private traced = -1

  /** `drivers`: the drivers of the world. `pace`: the param, which scales the gain. */
  constructor(drivers: number, pace: number) {
    this.drivers = Math.max(1, drivers)
    this.gain = GAIN * pace
  }

  /** An order was won. */
  won(): void {
    this.wins++
  }

  /** A gig was booked at `ratio` × the typical fees of its cars. */
  booked(ratio: number): void {
    this.bookings++
    this.ratios += ratio
  }

  /** The plan's volume in this world at the minute `at`, × the plan's: under 1 when the bookings so far pay more
   * than the plan or more orders are late than it allows (`lateShare`), over 1 when drivers come cheaper. */
  target(at: number, lateShare: number): number {
    const plan = planFee(at)
    const paid = (this.ratios + FEE_PRIOR * plan) / (this.bookings + FEE_PRIOR)
    const late = Math.max(0, lateShare - LATE_PLAN)
    return clamp(1 - FEE_WEIGHT * (paid - plan) - LATE_WEIGHT * late, TARGET_LOW, TARGET_HIGH)
  }

  /** The share by which the orders won are over the target so far (under it when negative). */
  miss(at: number, lateShare: number): number {
    const share = planShare(at)
    const planned = LOAD_PLAN * this.target(at, lateShare) * share
    return (this.wins / this.drivers - planned) / (LOAD_PLAN * (share + PLAN_PRIOR))
  }

  /** The load that the charge of `taxLoad` is taken at, in the place of the load the week is heading for: the
   * plan's, × exp(gain × the miss), inside the bounds. */
  load(at: number, lateShare: number): number {
    const miss = this.miss(at, lateShare)
    const charge = clamp(Math.exp(this.gain * miss), CHARGE_LOW, CHARGE_HIGH)
    this.low = Math.min(this.low, charge)
    this.high = Math.max(this.high, charge)
    this.last = charge
    this.trace(at, lateShare, miss, charge)
    return LOAD_PLAN * charge
  }

  /** With LEAN_PACE_TRACE set: one line an hour on stderr, to see the charge move over a week. */
  private trace(at: number, lateShare: number, miss: number, charge: number): void {
    const hour = Math.floor(at / HOUR)
    if (!process.env.LEAN_PACE_TRACE || hour === this.traced) return
    this.traced = hour
    const paid = this.bookings > 0 ? this.ratios / this.bookings : 0
    process.stderr.write(
      `pace day ${Math.floor(hour / 24)} ${String(hour % 24).padStart(2, '0')}:00 won ${this.wins} plan ${(LOAD_PLAN * planShare(at) * this.drivers).toFixed(0)} paid ${paid.toFixed(2)} plan ${planFee(at).toFixed(2)} late ${lateShare.toFixed(3)} target ${this.target(at, lateShare).toFixed(2)} miss ${miss.toFixed(2)} charge ${charge.toFixed(2)}\n`,
    )
  }

  summary(): string {
    return `Pace: charge ${this.low.toFixed(2)} to ${this.high.toFixed(2)} × the plan's, ${this.last.toFixed(2)} at the last quote.`
  }
}
