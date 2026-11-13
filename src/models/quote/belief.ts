/** What we believe the log level of the flips to be: a sum of parts (the world, the day, the lane, the option,
 * the dealer's trust), each a Gaussian belief with a mean and a variance. Each answered quote is a censored
 * observation: a win says the flip was at or above our price, a loss that it was below. */
import { type Shape, survival } from './flips.ts'

/** Each part's [mean, variance] of the log level. A part not yet seen starts at its prior. */
export type Belief = Record<string, [number, number]>

/** One part of a request's level: its key, its weight (1, or the dealer's trust count), and its prior. */
export type Term = { key: string; weight: number; prior: [number, number] }

/** The level of a request whose parts are `terms`: the mean and variance of its log. */
export function level(belief: Belief, terms: Term[]): { mean: number; variance: number } {
  let mean = 0
  let variance = 0
  for (const { key, weight, prior } of terms) {
    const [m, v] = belief[key] ?? prior
    mean += weight * m
    variance += weight * weight * v
  }
  return { mean, variance }
}

/** The chance that a quote at `x` (the log of price / list) wins, averaged over what we do not know of the
 * level: a three-point Gauss-Hermite rule, so a level we are unsure of spreads the flips wider. */
export function winShare(shape: Shape, x: number, mean: number, variance: number): number {
  const d = Math.sqrt(3 * variance)
  return (survival(shape, x - mean - d) + 4 * survival(shape, x - mean) + survival(shape, x - mean + d)) / 6
}

/** Learns from one answer, as an extended Kalman filter with a logistic observation: each part moves by its own
 * variance times the surprise (won minus the chance it had), so a win moves every part up and a loss down, and
 * the parts we are least sure of move most. No step exceeds a part's variance over the logistic scale, a mean
 * stays within four prior deviations of its prior, and a variance never falls under a fifth of its prior's. */
export function learn(belief: Belief, terms: Term[], x: number, won: boolean, shape: Shape): void {
  const { mean, variance } = level(belief, terms)
  const w = survival(shape, x - mean)
  const v = Math.max(w * (1 - w), 0.01)
  const s = shape.scale
  const gain = 1 + (v * variance) / (s * s)
  for (const { key, weight, prior } of terms) {
    if (weight === 0) continue
    const [m, p] = belief[key] ?? prior
    const [m0, p0] = prior
    const reach = 4 * Math.sqrt(p0)
    const next = m + (p * weight * ((won ? 1 : 0) - w)) / (s * gain)
    const shrunk = p - (p * weight) ** 2 * (v / (s * s * gain))
    belief[key] = [Math.min(m0 + reach, Math.max(m0 - reach, next)), Math.max(shrunk, p0 / 25)]
  }
}

/** Adds variance to a part, so it keeps learning as fast as the world can move it. */
export function drift(belief: Belief, term: Term, variance: number): void {
  const [m, p] = belief[term.key] ?? term.prior
  belief[term.key] = [m, Math.min(p + variance, term.prior[1])]
}
