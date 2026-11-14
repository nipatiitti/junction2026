/** The dealers' side, learned while the week runs: for one option of one request, the highest multiple of the list
 * price that wins. Its log is a sum of effects (the world, the day, the dealer, the pickup place, the delivery place,
 * the option), each a mean and a variance, updated from every quote that wins or loses. The priors are the measured
 * level 8 facts: half of the quotes win at 1.40 × list, worlds differ by 7%, days by 15%, same-day takes 13% more,
 * and 12% of noise stays in every request. */
import type { DeliveryOption, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { DAY } from '../../ops/index.ts'

/** The noise that stays in one request's threshold, as a logistic scale in log price. */
const NOISE = 0.08
/** The most that one outcome moves an estimate, in log price. */
const MAX_STEP = 0.12
/** Half of the quotes win at this multiple of the list price, by level (RULES.md, "Practice and the final"). */
const MIDDLE = (level: number): number => (level >= 8 ? 1.4 : level === 7 ? 1.25 : 1)

/** Each kind of effect: its prior mean and variance in log price, and the variance it gains back each morning,
 * because the competitor moves its prices by place and by dealer during the week. */
const PRIOR: Record<string, { mean: number; variance: number; drift: number }> = {
  world: { mean: 0, variance: 0.006, drift: 0.0005 },
  day: { mean: 0, variance: 0.0225, drift: 0 },
  dealer: { mean: 0, variance: 0.008, drift: 0.001 },
  from: { mean: 0, variance: 0.008, drift: 0.001 },
  to: { mean: 0, variance: 0.008, drift: 0.001 },
  same_day: { mean: 0.12, variance: 0.002, drift: 0 },
  next_day: { mean: 0, variance: 0.002, drift: 0 },
  within_3_days: { mean: 0, variance: 0.002, drift: 0 },
}

type Effect = { mean: number; variance: number }

/** What we believe of one option's threshold: its log multiple of the list price, and the logistic scale of our
 * doubt about it (the request's own noise, widened by what the effects have not learned yet). */
export type Belief = { mu: number; scale: number; variance: number }

export class Demand {
  private readonly effects = new Map<string, Effect>()
  private readonly base: number
  private day = -1

  constructor(level: number) {
    this.base = Math.log(MIDDLE(level))
  }

  /** The effects that an option of a request sums. */
  keys(request: PriceRequest, kind: DeliveryOption['kind']): string[] {
    const leg = request.legs[0]
    return [
      'world',
      `day:${Math.floor(request.arrivedAt / DAY)}`,
      `dealer:${request.dealerId}`,
      `from:${leg?.pickup.placeId}`,
      `to:${leg?.delivery.placeId}`,
      kind,
    ]
  }

  /** The belief for the effects `keys`, moved by `offset` (the dealer's trust). */
  belief(keys: string[], offset = 0): Belief {
    let mu = this.base + offset
    let variance = 0
    for (const key of keys) {
      const effect = this.effect(key)
      mu += effect.mean
      variance += effect.variance
    }
    return { mu, variance, scale: NOISE * Math.sqrt(1 + (Math.PI * variance) / (8 * NOISE * NOISE)) }
  }

  /** The chance that a price of `multiple` × list wins. */
  static chance(belief: Belief, multiple: number): number {
    return 1 / (1 + Math.exp((Math.log(multiple) - belief.mu) / belief.scale))
  }

  /** Learns from one quote: `multiple` × list won or lost. Each effect moves by its share of the doubt. */
  learn(keys: string[], offset: number, multiple: number, won: boolean): void {
    if (!(multiple > 0) || !Number.isFinite(multiple)) return
    const belief = this.belief(keys, offset)
    const p = Demand.chance(belief, multiple)
    const gradient = ((won ? 1 : 0) - p) / belief.scale
    const curve = (p * (1 - p)) / (belief.scale * belief.scale)
    const gain = 1 / (1 + belief.variance * curve)
    const step = Math.abs(belief.variance * gradient * gain)
    const damp = step > MAX_STEP ? MAX_STEP / step : 1
    for (const key of keys) {
      const effect = this.effect(key)
      effect.mean += effect.variance * gradient * gain * damp
      effect.variance = Math.max(1e-5, effect.variance - effect.variance * effect.variance * curve * gain)
    }
  }

  /** A new day: the effects that the competitor moves get some doubt back. */
  dawn(day: number): void {
    if (day <= this.day) return
    this.day = day
    for (const [key, effect] of this.effects) {
      const prior = PRIOR[key.split(':')[0]!]!
      effect.variance = Math.min(prior.variance, effect.variance + prior.drift)
    }
  }

  /** The multiple of the list price at which half of the quotes win, for the world and today. */
  level(day: number): number {
    return Math.exp(this.base + this.effect('world').mean + this.effect(`day:${day}`).mean)
  }

  private effect(key: string): Effect {
    let effect = this.effects.get(key)
    if (!effect) {
      const prior = PRIOR[key.split(':')[0]!]!
      effect = { mean: prior.mean, variance: prior.variance }
      this.effects.set(key, effect)
    }
    return effect
  }
}

/** The price in cents that earns the most: the chance to win times what the win leaves over `costCents` (the
 * drivers, and what the capacity is worth). Null when no price leaves anything. */
export function bestPrice(belief: Belief, listCents: number, costCents: number): number | null {
  let best = 0
  let price: number | null = null
  for (let multiple = 0.9; multiple <= 3.001; multiple += 0.01) {
    const value = Demand.chance(belief, multiple) * (multiple * listCents - costCents)
    if (value > best) {
      best = value
      price = multiple * listCents
    }
  }
  return price
}
