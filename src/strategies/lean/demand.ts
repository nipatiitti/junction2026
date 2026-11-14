/** The dealers' side, learned while the week runs: for one option of one request, the highest multiple of the list
 * price that wins. Its log is a sum of effects (the world, the day, the dealer, the pickup place, the delivery place,
 * the option), each a mean and a variance, updated from every quote that wins or loses. The priors are the measured
 * level 8 facts: half of the quotes win at `middle` × list, worlds differ by 8% and a day by 14% around its week
 * (349 recorded seeds, sim/market.json), same-day takes 12% more (the quote probes). */
import type { DeliveryOption, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { DAY } from '../../ops/index.ts'
import { normal } from './sample.ts'

/** The most that one outcome moves an estimate, in log price. Not measured. */
const MAX_STEP = 0.12
/** Half of the quotes win at this multiple of the list price below level 8 (RULES.md, "Practice and the final");
 * at level 8 it is the param `middle`. */
const MIDDLE = (level: number, middle: number): number => (level >= 8 ? middle : level === 7 ? 1.25 : 1)
/** The prices that `bestPrice` tries, in hundredths of the list price. A cost over the top declines the option. */
const PRICE_FROM = 90
const PRICE_TO = 300
/** No effect is ever surer than this variance. */
const LEAST_DOUBT = 1e-5

/** Each kind of effect: its prior mean and variance in log price, and the variance it gains back each morning,
 * because the competitor moves its prices by place and by dealer during the week. The world, the day and same-day
 * are measured (above). The dealer and place variances (9% each), the options' (4%) and the drifts are not. */
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

export type QuoteOutcome = { keys: string[]; offset: number; multiple: number; won: boolean }

type Contribution = { mean: number; variance: number; count: number }

export class Demand {
  private readonly effects = new Map<string, Effect>()
  private readonly base: number
  private day = -1
  /** The noise that stays in one request's threshold, as a logistic scale in log price. */
  private readonly noise: number

  constructor(level: number, noise: number, middle: number) {
    this.noise = noise
    this.base = Math.log(MIDDLE(level, middle))
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
    return { mu, variance, scale: this.noise * Math.sqrt(1 + (Math.PI * variance) / (8 * this.noise * this.noise)) }
  }

  /** Thompson sampling: the belief for one draw of the effects `keys` from what we know of them, each mean moved
   * by `sample` × its standard deviation × a normal number drawn from `seed` and the effect's key. The effects that
   * the options of a request share (the world, the day, the dealer, the places) have the same key, so with the
   * request id as the seed they are drawn once for the request, and the option's own effect once for each option.
   * The scale keeps only the doubt that the draw does not carry: none of it at `sample` 1 (the request's own noise
   * is left), all of it at 0, where this is `belief`. `learn` never sees a draw. */
  sampled(keys: string[], offset: number, sample: number, seed: string): Belief {
    let mu = this.base + offset
    let variance = 0
    for (const key of keys) {
      const effect = this.effect(key)
      mu += effect.mean + sample * Math.sqrt(effect.variance) * normal(`${seed} ${key}`)
      variance += effect.variance
    }
    variance *= Math.max(0, 1 - sample * sample)
    return { mu, variance, scale: this.noise * Math.sqrt(1 + (Math.PI * variance) / (8 * this.noise * this.noise)) }
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
      effect.variance = Math.max(LEAST_DOUBT, effect.variance - effect.variance * effect.variance * curve * gain)
    }
  }

  /** Learns a lost request's quoted options without counting their shared evidence more than once. All observations
   * use the state before the request. The option effect learns separately; each shared effect gets the mean of the
   * options' contributions, so the answer does not depend on their order. */
  learnShared(outcomes: readonly QuoteOutcome[]): void {
    const shared = new Map<string, Contribution>()
    const options: { key: string; mean: number; variance: number }[] = []
    for (const { keys, offset, multiple, won } of outcomes) {
      const optionKey = keys.at(-1)
      if (!(multiple > 0) || !Number.isFinite(multiple) || optionKey === undefined) continue
      const belief = this.belief(keys, offset)
      const p = Demand.chance(belief, multiple)
      const gradient = ((won ? 1 : 0) - p) / belief.scale
      const curve = (p * (1 - p)) / (belief.scale * belief.scale)
      const gain = 1 / (1 + belief.variance * curve)
      const step = Math.abs(belief.variance * gradient * gain)
      const damp = step > MAX_STEP ? MAX_STEP / step : 1
      for (const key of keys) {
        const effect = this.effect(key)
        const mean = effect.variance * gradient * gain * damp
        const variance = -effect.variance * effect.variance * curve * gain
        if (key === optionKey) options.push({ key, mean, variance })
        else {
          const contribution = shared.get(key) ?? { mean: 0, variance: 0, count: 0 }
          contribution.mean += mean
          contribution.variance += variance
          contribution.count++
          shared.set(key, contribution)
        }
      }
    }
    for (const [key, contribution] of shared) {
      const effect = this.effect(key)
      effect.mean += contribution.mean / contribution.count
      effect.variance = Math.max(LEAST_DOUBT, effect.variance + contribution.variance / contribution.count)
    }
    for (const { key, mean, variance } of options) {
      const effect = this.effect(key)
      effect.mean += mean
      effect.variance = Math.max(LEAST_DOUBT, effect.variance + variance)
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
  for (let hundredths = PRICE_FROM; hundredths <= PRICE_TO; hundredths++) {
    const multiple = hundredths / 100
    const value = Demand.chance(belief, multiple) * (multiple * listCents - costCents)
    if (value > best) {
      best = value
      price = multiple * listCents
    }
  }
  return price
}
