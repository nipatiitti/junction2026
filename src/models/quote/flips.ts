/** The scatter of a request's flip around its level, as a distribution of the log of flip / level. */
import type { QuoteParams } from './params.ts'

export type Shape = {
  /** Log quantiles at `probs`, increasing. */
  logs: number[]
  probs: number[]
  /** The logistic scale with the same spread: half the interquartile range over ln 3. */
  scale: number
}

const shapes = new WeakMap<QuoteParams, Shape>()

/** The shape of `params.flipResidual`, built once per params object. */
export function shapeOf(params: QuoteParams): Shape {
  let shape = shapes.get(params)
  if (!shape) {
    const logs = params.flipResidual.map(Math.log)
    const iqr = interpolate(params.probs, logs, 0.75) - interpolate(params.probs, logs, 0.25)
    shape = { logs, probs: params.probs, scale: Math.max(iqr / (2 * Math.log(3)), 0.01) }
    shapes.set(params, shape)
  }
  return shape
}

/** The share of flips whose log over the level is at least `x`: a quote at that log ratio over the level wins
 * this often. Linear between the quantiles, and on to 0 and 1 along the end segments beyond them. */
export function survival(shape: Shape, x: number): number {
  return 1 - Math.min(1, Math.max(0, interpolate(shape.logs, shape.probs, x)))
}

/** The log of flip / level at cumulative share `p`. */
export function quantile(shape: Shape, p: number): number {
  return interpolate(shape.probs, shape.logs, p)
}

/** Piecewise-linear `ys` at `x` over increasing `xs`, extended along the first and last segments. */
function interpolate(xs: number[], ys: number[], x: number): number {
  let lo = 0
  let hi = xs.length - 1
  if (x <= xs[0]) hi = 1
  else if (x >= xs[hi]) lo = hi - 1
  else {
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (xs[mid] <= x) lo = mid
      else hi = mid
    }
  }
  const span = xs[hi] - xs[lo]
  return span > 0 ? ys[lo] + ((x - xs[lo]) / span) * (ys[hi] - ys[lo]) : ys[lo]
}
