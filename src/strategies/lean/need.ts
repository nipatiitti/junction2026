/** What a gig needs: the fee that books it. The model (cost.json) is fitted once on the fee probes, each of which
 * found the lowest flat fee that booked one fresh gig within three hours (analysis/ml/README.md). It gives that fee
 * as a share of the typical fee, with the scatter that stays, and the chance that no fee up to 1.8 x typical books
 * the gig in that time. Both come from what the desk sees: the typical fee, when the car is ready, the hour and the
 * day, the time left, the kind of work, where this week's drivers live, and how many of our gigs are booked and open. */
import { readFileSync } from 'node:fs'
import { DAY, HOUR } from '../../ops/index.ts'

type Weights = Record<string, number>
const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))

export type NeedModel = { sd: number; fee: Weights; never: Weights }

/** A gig as the model sees it, at the minute `at` (a quote or a posting). */
export type Work = {
  typicalCents: number
  at: number
  readyAt: number
  lastPickupAt: number
  driveMinutes: number
  privatePickup: boolean
  privateDelivery: boolean
  premium: boolean
  electric: boolean
  tradeIn: boolean
  /** Drivers of this week's list who live at the pickup place and at the delivery place, and all of them. */
  homePickup: number
  homeDelivery: number
  drivers: number
  /** Our gigs that a driver has booked so far this week, and the ones open without a driver now. */
  booked: number
  open: number
  /** For the order model: the option's deadline, whether the dealer wrote a note, and our orders won so far in the
   * week and today. */
  deadline: number
  hasNote: boolean
  won: number
  wonToday: number
}

/** The lowest fee that books: its log over the typical fee (`mu`) with scatter `sd`, and the chance of none. */
export type Need = { mu: number; sd: number; never: number }

/** The order model (order.json), fitted on the real orders of the saved weeks: what a won order costs to serve, over
 * its typical fee (fees, failed visits, waiting), and the chance that it arrives late. */
export type OrderModel = { meanCost: number; meanLate: number; cost: Weights; late: Weights }
export type Outlook = { cost: number; late: number }

export const loadOrders = (): OrderModel =>
  JSON.parse(readFileSync(new URL('./order.json', import.meta.url), 'utf-8')) as OrderModel

/** What the order model expects of this work, won now: its cost over the mean order's (1 = as dear as the mean
 * order), and its chance to be late. */
export function outlook(model: OrderModel, work: Work): Outlook {
  const offset = Math.floor(work.readyAt / DAY) - Math.floor(work.at / DAY)
  const hour = (work.at % DAY) / HOUR
  const day = Math.floor(work.at / DAY)
  const today = offset <= 0 ? 1 : 0
  const drive = work.driveMinutes / 60
  const logTypical = Math.log(Math.max(1, work.typicalCents) / 5000)
  const toLast = (work.lastPickupAt - work.at) / HOUR
  const long = clamp(drive - 3, 0, 6) / 6
  const x: Weights = {
    log_typical: logTypical,
    log_typical_sq: logTypical * logTypical,
    pickup_today: today,
    pickup_later: offset >= 2 ? 1 : 0,
    hour: (hour - 13) / 5,
    today_late_hour: (today * clamp(hour - 12, 0, 6)) / 6,
    long_drive: long,
    very_long_drive: clamp(drive - 5, 0, 4) / 4,
    short_drive: drive < 0.75 ? 1 : 0,
    today_long_drive: today * long,
    time_to_last_pickup: Math.log(clamp(toLast, 1, 96) / 24),
    tight: toLast < 8 ? 1 : 0,
    room: Math.log(clamp((work.deadline - work.readyAt) / HOUR, 2, 120) / 24),
    monday: day === 0 ? 1 : 0,
    thursday: day === 3 ? 1 : 0,
    friday: day === 4 ? 1 : 0,
    private_pickup: work.privatePickup ? 1 : 0,
    private_delivery: work.privateDelivery ? 1 : 0,
    premium: work.premium ? 1 : 0,
    electric: work.electric ? 1 : 0,
    trade_in: work.tradeIn ? 1 : 0,
    has_note: work.hasNote ? 1 : 0,
    home_pickup: Math.log(1 + work.homePickup) / 5,
    home_delivery: Math.log(1 + work.homeDelivery) / 5,
    drivers: Math.log(Math.max(1, work.drivers) / 777),
    won_so_far: work.won / 300,
    won_today: work.wonToday / 80,
    open_gigs: clamp(work.open, 0, 120) / 40,
  }
  const sum = (weights: Weights): number =>
    Object.entries(x).reduce((total, [key, value]) => total + (weights[key] ?? 0) * value, weights.base ?? 0)
  return { cost: clamp(sum(model.cost) / model.meanCost, 0.5, 3), late: 1 / (1 + Math.exp(-sum(model.late))) }
}

export const loadNeed = (): NeedModel =>
  JSON.parse(readFileSync(new URL('./cost.json', import.meta.url), 'utf-8')) as NeedModel

export function need(model: NeedModel, work: Work): Need {
  const offset = Math.max(0, Math.floor(work.readyAt / DAY) - Math.floor(work.at / DAY))
  const hour = (work.at % DAY) / HOUR
  const day = Math.floor(work.at / DAY)
  const today = offset === 0 ? 1 : 0
  const logTypical = Math.log(Math.max(1, work.typicalCents) / 5000)
  const x: Weights = {
    log_typical: logTypical,
    log_typical_sq: logTypical * logTypical,
    pickup_today: today,
    pickup_later: offset >= 2 ? 1 : 0,
    hour: (hour - 13) / 5,
    today_late_hour: (today * clamp(hour - 12, 0, 6)) / 6,
    hours_to_last_pickup: Math.log(clamp((work.lastPickupAt - work.at) / HOUR, 1, 96) / 24),
    friday: day === 4 ? 1 : 0,
    monday: day === 0 ? 1 : 0,
    private_pickup: work.privatePickup ? 1 : 0,
    private_delivery: work.privateDelivery ? 1 : 0,
    premium: work.premium ? 1 : 0,
    electric: work.electric ? 1 : 0,
    trade_in: work.tradeIn ? 1 : 0,
    long_drive: clamp(work.driveMinutes / 60 - 3, 0, 6) / 6,
    home_pickup: Math.log(1 + work.homePickup) / 5,
    home_delivery: Math.log(1 + work.homeDelivery) / 5,
    drivers: Math.log(Math.max(1, work.drivers) / 777),
    load_booked: work.booked / 300,
    load_open: work.open / 40,
  }
  const sum = (weights: Weights): number =>
    Object.entries(x).reduce((total, [key, value]) => total + (weights[key] ?? 0) * value, weights.base ?? 0)
  return { mu: sum(model.fee), sd: model.sd, never: 1 / (1 + Math.exp(-sum(model.never))) }
}

/** The standard normal distribution function (Abramowitz and Stegun 26.2.17, error under 1e-7). */
function phi(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const tail =
    Math.exp((-z * z) / 2) *
    0.3989422804 *
    t *
    (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
  return z >= 0 ? 1 - tail : tail
}

/** The fee to open at, x typical: the fee that books `chance` of such gigs, `z` scatters above the middle. */
export const openingOf = (n: Need, z: number): number => clamp(Math.exp(n.mu + z * n.sd), 0.5, 1.5)

/** What a gig that opens at `open` x typical ends up paying, x typical: the opening when a driver takes it, else
 * what its own driver needs (the mean of the larger of the two). */
export function paidOf(n: Need, open: number): number {
  const at = Math.log(open)
  return open * phi((at - n.mu) / n.sd) + Math.exp(n.mu + (n.sd * n.sd) / 2) * phi((n.mu + n.sd * n.sd - at) / n.sd)
}
