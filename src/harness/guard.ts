/** Runs strategy calls so that no strategy can stop the week: an error, a late answer or an answer that the world
 * would refuse gives the safe answer. */
import type { Action, FeeStep, PriceRequest, StopRef } from '../../vendor/spread-typescript/spread.ts'

/** The time budget of each call, in milliseconds. A final gives 4.5 real seconds for a quote. */
export const BUDGET_MS = { build: 5000, observe: 1500, sent: 1500, quote: 1500, gig: 1500, tick: 3000, summary: 1500 }
export type Call = keyof typeof BUDGET_MS

export class Guard {
  /** "quote error", "gig late" and so on -> how many times. */
  readonly faults = new Map<string, number>()
  /** The first message of each kind of fault. */
  readonly messages = new Map<string, string>()

  /** The strategy's answer, or undefined when the call throws or takes longer than its budget: the caller then takes
   * the safe action. A call cannot be stopped midway, so a late answer is dropped once it comes. */
  run<T>(call: Call, decide: () => T): T | undefined {
    const started = performance.now()
    try {
      const answer = decide()
      if (performance.now() - started <= BUDGET_MS[call]) return answer
      this.fault(`${call} late`)
    } catch (error) {
      this.fault(`${call} error`, error)
    }
    return undefined
  }

  /** The actions, rounded to whole numbers, that the world can take; each other one counts as an invalid answer of
   * `call`, and the caller takes the safe action. A quote must price only the options that `request` offers. */
  admit<T extends Action>(call: Call, actions: T[], request?: PriceRequest): T[] {
    return actions.flatMap((action) => {
      try {
        const rounded = whole(action)
        if (sound(rounded, request)) return [rounded]
      } catch {} // a value that whole() cannot walk, such as one that holds itself
      this.fault(`${call} invalid`, JSON.stringify(action)?.slice(0, 300))
      return []
    })
  }

  /** Counts a fault, and prints the first of each kind. */
  fault(kind: string, error?: unknown): void {
    const count = (this.faults.get(kind) ?? 0) + 1
    this.faults.set(kind, count)
    if (count > 1) return
    const why = error === undefined ? '' : `: ${error instanceof Error ? error.message : String(error)}`
    this.messages.set(kind, why.slice(2))
    console.error(`strategy ${kind}${why}. The harness takes the safe action.`)
  }
}

/** The value with every number rounded. The API takes whole minutes and cents only, and the client refuses a whole
 * batch for one fraction. */
export function whole<T>(value: T): T {
  if (typeof value === 'number') return Math.round(value) as T
  if (Array.isArray(value)) return value.map(whole) as T
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, whole(item)])) as T
  return value
}

/** Whether the world can take an action: every number whole and finite, prices and fees at least 1 cent, a schedule
 * of 1 to 48 steps in time order whose fee never falls, and the ids, stops and audience present. One bad number
 * would make the server refuse the whole batch. */
export function sound(action: Action, request?: PriceRequest): boolean {
  if (typeof action !== 'object' || action === null) return false
  switch (action.type) {
    case 'quote':
      return isId(action.requestId) && isPrices(action.prices, request)
    case 'post':
      return isStops(action.stops) && isAudience(action.audience) && isSchedule(action.schedule)
    case 'reprice':
      return isId(action.gigId) && isSchedule(action.schedule)
    case 'offer':
      return isId(action.gigId) && isId(action.driverId) && isCents(action.feeCents)
    case 'withdraw':
    case 'release':
      return isId(action.gigId)
    default:
      return false
  }
}

const isId = (value: unknown): boolean => typeof value === 'string' && value.length > 0
const isMinute = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const isCents = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 1
const isFlag = (value: unknown): boolean => value === undefined || typeof value === 'boolean'
const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null

function isPrices(prices: unknown, request?: PriceRequest): boolean {
  if (!isObject(prices)) return false
  const offered = (kind: string) => !request || request.options.some((option) => option.kind === kind)
  const entries = Object.entries(prices)
  return entries.length > 0 && entries.every(([kind, cents]) => offered(kind) && isCents(cents))
}

function isStops(stops: unknown): boolean {
  const isStop = (stop: StopRef) =>
    isObject(stop) &&
    isId(stop.orderId) &&
    isMinute(stop.leg) &&
    (stop.kind === 'pickup' || stop.kind === 'delivery') &&
    (stop.window === undefined || (isObject(stop.window) && isMinute(stop.window.from) && isMinute(stop.window.to))) &&
    isFlag(stop.withPlates) &&
    isFlag(stop.withCharging)
  return Array.isArray(stops) && stops.length > 0 && stops.every(isStop)
}

const isAudience = (audience: unknown): boolean =>
  isObject(audience) && typeof audience.experienced === 'boolean' && typeof audience.manualLicence === 'boolean'

function isSchedule(schedule: unknown): boolean {
  if (!Array.isArray(schedule) || schedule.length < 1 || schedule.length > 48) return false
  return schedule.every(
    (step: FeeStep, i) =>
      isObject(step) &&
      isMinute(step.at) &&
      isCents(step.feeCents) &&
      (i === 0 || (step.at > schedule[i - 1].at && step.feeCents >= schedule[i - 1].feeCents)),
  )
}
