/** Modifiers: the rules that the Python systems of `strategies/` measured on their own weeks (`headroom`, `dawn_fees`,
 * `lead_cost`, `lane_fee`, `all_in`, `pair_first`), as switches on the lean strategy. Each is off by default and
 * changes one decision, so a bench can play it alone. README.md lists them with where each number comes from. */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, HOUR } from '../../ops/index.ts'

// ------------------------------------------------------------------------------------------------ the lead cost

/** `strategies/lead_cost`: what a delivered order cost over its typical fee (fees, failed visits, refunds), by the
 * hours from the dealer's decision to the last pickup (rows) and to the car's ready time (columns), on 9,139 orders.
 * A car to collect within 14 hours costs about twice its typical fee; a car ready the next day costs 1.03. */
const LAST_PICKUP_HOURS = [8, 14, 24, 36, 60]
const READY_HOURS = [3, 8]
const COST = [
  [2.4, 2.4, 2.4],
  [1.77, 1.77, 1.77],
  [1.44, 1.25, 1.06],
  [1.25, 1.1, 1.03],
  [1.25, 1.1, 1.05],
  [1.2, 1.1, 1.13],
]
const PRIVATE_PICKUP = [1.05, 1.3, 1.3]
const PRIVATE_DELIVERY = [1.03, 1.1, 1.1]

/** The cost of an option over its typical fee by its lead times, in minutes. */
export function leadCost(
  toLastPickup: number,
  toReady: number,
  privatePickup: boolean,
  privateDelivery: boolean,
): number {
  const row = LAST_PICKUP_HOURS.findIndex((hours) => toLastPickup < hours * HOUR)
  const column = READY_HOURS.findIndex((hours) => toReady < hours * HOUR)
  const c = column < 0 ? READY_HOURS.length : column
  const cell = COST[row < 0 ? LAST_PICKUP_HOURS.length : row]?.[c] ?? 1.25
  return cell * (privatePickup ? (PRIVATE_PICKUP[c] ?? 1.3) : 1) * (privateDelivery ? (PRIVATE_DELIVERY[c] ?? 1.1) : 1)
}

// ------------------------------------------------------------------------------------------------ the dawn fees

/** `strategies/dawn_fees` with the values of `strategies/all_in`: drivers plan their day at 06:00, and the morning
 * takes what the app shows. A gig opens at 0.9 × typical, rises once to 1.0 an hour later and holds that through
 * every evening and night. From its last dawn (the last 06:00 that leaves 3 hours to the last pickup) it climbs from
 * 1.05 in hourly steps to the top, 7 hours before the last pickup. When the top is due before that dawn, it rises to
 * 1.4 at 20:00 the evening before and reaches the top at 07:00. A gig with no dawn to wait for opens at 1.1 and
 * climbs to the top in 15-minute steps within 2 hours. */
const OPEN = 0.9
const HOLD = 1
const PATIENCE = HOUR
const DAWN_AT = 6 * HOUR
const DAWN = 1.05
const TIGHT = 1.4
const REACH = 3 * HOUR
const TRAVEL = 7 * HOUR
const SPRINT_OPEN = 1.1

export function dawn(now: number, typical: number, lastPickup: number, top: number, floor = 0): FeeStep[] {
  const points: [number, number][] = []
  let lastDawn = Math.floor((lastPickup - REACH - DAWN_AT) / DAY) * DAY + DAWN_AT
  if (lastDawn <= now) lastDawn = -Infinity
  if (lastDawn === -Infinity) {
    // The sprint: no morning to wait for.
    const end = Math.max(now + 15, Math.min(now + 2 * HOUR, lastPickup - REACH))
    const steps = Math.max(1, Math.round((end - now) / 15))
    for (let i = 0; i <= steps; i++)
      points.push([now + ((end - now) * i) / steps, SPRINT_OPEN * (top / SPRINT_OPEN) ** (i / steps)])
  } else {
    points.push([now, OPEN])
    const raise = now + PATIENCE
    if (raise % DAY < 22 * HOUR && Math.floor(raise / DAY) === Math.floor(now / DAY) && raise < lastDawn)
      points.push([raise, HOLD])
    const topAt = lastPickup - TRAVEL
    if (topAt < lastDawn + HOUR) {
      const evening = lastDawn - 10 * HOUR // 20:00 the evening before
      points.push([Math.max(evening, now + 1), TIGHT], [lastDawn, TIGHT], [lastDawn + HOUR, top])
    } else {
      const steps = Math.max(1, Math.round((topAt - lastDawn) / HOUR))
      for (let i = 0; i <= steps; i++)
        points.push([lastDawn + ((topAt - lastDawn) * i) / steps, DAWN * (top / DAWN) ** (i / steps)])
    }
  }
  const steps: FeeStep[] = []
  for (const [minute, ratio] of points.sort((a, b) => a[0] - b[0])) {
    const at = Math.max(now, Math.round(minute))
    const feeCents = Math.max(1, Math.round(Math.max(ratio, floor) * typical), steps.at(-1)?.feeCents ?? 0)
    const last = steps.at(-1)
    if (last && at <= last.at) last.feeCents = feeCents
    else if (!last || feeCents > last.feeCents) steps.push({ at, feeCents })
  }
  return steps.slice(0, 48)
}

// --------------------------------------------------------------------------------------------- the price maximum

/** `strategies/headroom`: no price goes above a maximum that the week moves. It starts at 1.39 × list; each quote
 * priced at it raises it by 0.6% when it wins and lowers it by 0.6% when it loses, between 1.20 and 1.62, so it
 * settles where half of the quotes at it win. The competitor cuts its prices for a dealer whose requests we mostly
 * win, so the maximum also keeps us from teaching it to. */
export class PriceCap {
  private log = Math.log(1.39)

  /** The maximum as a multiple of the list price, lifted by the dealer's trust (1% for each order on time). */
  multiple(trust: number): number {
    return Math.exp(this.log) * (1 + trust / 100)
  }

  /** Learns from a quote: when it was priced at the maximum, a win raises the maximum and a loss lowers it. */
  learn(multiple: number, trust: number, won: boolean): void {
    if (Math.abs(multiple / this.multiple(trust) - 1) > 0.005) return
    this.log = Math.min(Math.log(1.62), Math.max(Math.log(1.2), this.log + 0.012 * ((won ? 1 : 0) - 0.5)))
  }
}
