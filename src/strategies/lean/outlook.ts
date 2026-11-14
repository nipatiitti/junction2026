/** The order model (order.json), fitted on the real orders of the saved weeks (analysis/ml on the branch of #305):
 * what a won order costs to serve over its typical fee (fees, failed visits, waiting), and the chance that it
 * arrives late, from what the desk sees at the quote. The level of the cost stays the week's own; the model says
 * which requests are dear and which are risky. */
import { readFileSync } from 'node:fs'
import { DAY, HOUR } from '../../ops/index.ts'

type Weights = Record<string, number>
const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))

export type OrderModel = { meanCost: number; cost: Weights; late: Weights }

/** A request as the model sees it, at the minute `at`. */
export type Work = {
  typicalCents: number
  at: number
  readyAt: number
  lastPickupAt: number
  deadline: number
  driveMinutes: number
  privatePickup: boolean
  privateDelivery: boolean
  premium: boolean
  electric: boolean
  tradeIn: boolean
  hasNote: boolean
  /** Drivers of this week's list who live at the pickup place and at the delivery place, and all of them. */
  homePickup: number
  homeDelivery: number
  drivers: number
  /** Our orders won so far in the week and today, and our gigs open without a driver now. */
  won: number
  wonToday: number
  open: number
}

export const loadOrders = (): OrderModel =>
  JSON.parse(readFileSync(new URL('./order.json', import.meta.url), 'utf-8')) as OrderModel

/** What the model expects of this work, won now: its cost over the mean order's (1 = as dear as the mean order:
 * `meanCost` is the mean of the fit, so the level of a price is `costLevel` alone),
 * and its chance to be late. */
export function outlook(model: OrderModel, work: Work): { cost: number; late: number } {
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
