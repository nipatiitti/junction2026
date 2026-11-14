/** isotone: learn the win curve online and price at its profit peak. Per context (trust bucket × capital-region
 * delivery) it keeps win/loss counts on a grid of normalised price multiples. A threshold model makes the curve
 * monotone: a win at z is a win at every lower grid z, a loss at z a loss at every higher one. Each option is priced
 * by Thompson sampling: one shared normal draw over the Beta posteriors, made non-increasing, then argmax of (z − cost) × win. */
import type { PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type BaseParams, type OptionKind, type Outcome, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  gridLo: 1.0,
  gridHi: 2.2,
  gridStep: 0.05,
  /** Prior counts per cell, from the trust-0 threshold quantiles below. */
  priorWeight: 25,
  /** Prior threshold scale: capital-region deliveries and the rest; trust raises it by `trustLift` a point. */
  capitalScale: 0.88,
  otherScale: 1.05,
  trustLift: 0.03,
  /** Trust buckets: under `trustMid`, under `trustHigh`, above. */
  trustMid: 3,
  trustHigh: 10,
  /** Option ladder: same_day = sameDayLadder × next_day, next_day = nextDayLadder × within_3_days. */
  sameDayLadder: 1.21,
  nextDayLadder: 1.13,
  /** Counts of a context fade by this on each of its outcomes, so the week's level and price-war days show. */
  decay: 0.997,
  /** Thompson spread: 1 = the posterior's own, 0 = greedy. */
  explore: 1,
  /** Final price × this, a nudge after the argmax. */
  shade: 1,
}
type P = typeof OWN & BaseParams

const CAPITAL = /helsinki|espoo|vantaa|hyvink/i
/** Trust-0 thresholds (price / list): quantile → value. */
const Q: [number, number][] = [
  [0, 0.7],
  [0.1, 0.98],
  [0.25, 1.15],
  [0.5, 1.29],
  [0.75, 1.46],
  [0.9, 1.62],
  [1, 2.1],
]
const cdf = (x: number) => {
  if (x <= Q[0][1]) return 0
  for (let i = 1; i < Q.length; i++) {
    const [q0, x0] = Q[i - 1]
    const [q1, x1] = Q[i]
    if (x <= x1) return q0 + ((q1 - q0) * (x - x0)) / (x1 - x0)
  }
  return 1
}

type Cells = { win: number[]; loss: number[] }

class Isotone extends PricedStrategy<P> {
  private readonly grid: number[] = []
  private readonly cells = new Map<string, Cells>()
  private readonly capital = new Set<string>()

  constructor(...args: ConstructorParameters<typeof PricedStrategy<P>>) {
    super(...args)
    const p = this.params
    for (let z = p.gridLo; z <= p.gridHi + 1e-9; z += p.gridStep) this.grid.push(z)
    for (const place of this.setup.map.places) if (CAPITAL.test(place.name)) this.capital.add(place.id)
  }

  private ladder(kind: OptionKind): number {
    const p = this.params
    return kind === 'same_day' ? p.sameDayLadder * p.nextDayLadder : kind === 'next_day' ? p.nextDayLadder : 1
  }

  /** The request's within_3_days-equivalent list price, so z = price / (anchor × ladder). */
  private anchor(r: PriceRequest): number {
    const xs = r.options.map((o) => o.listPriceCents / this.ladder(o.kind))
    return xs.reduce((a, b) => a + b, 0) / xs.length
  }

  private key(r: PriceRequest): { key: string; cap: boolean; trust: number } {
    const trust = this.t.trust.get(r.dealerId) ?? 0
    const cap = r.legs.some((l) => this.capital.has(l.delivery.placeId))
    const b = trust < this.params.trustMid ? 0 : trust < this.params.trustHigh ? 1 : 2
    return { key: `${b}/${cap ? 'c' : 'o'}`, cap, trust: [1, 6, 15][b] }
  }

  private cellsOf(r: PriceRequest): Cells {
    const { key, cap, trust } = this.key(r)
    let c = this.cells.get(key)
    if (!c) {
      const p = this.params
      const scale = (cap ? p.capitalScale : p.otherScale) * (1 + p.trustLift * trust)
      const w = this.grid.map((z) => p.priorWeight * Math.min(0.99, Math.max(0.01, 1 - cdf(z / scale))))
      c = { win: w, loss: w.map((x) => p.priorWeight - x) }
      this.cells.set(key, c)
    }
    return c
  }

  price(ctx: PriceCtx): number | null {
    const c = this.cellsOf(ctx.request)
    const unit = this.anchor(ctx.request) * this.ladder(ctx.option.kind)
    const cost = ctx.costCents / unit
    let best = -1
    let bestZ = 0
    let cap = 1
    // One shared normal draw: a coherent sample of the whole curve (Beta by its normal approximation).
    const n = Math.sqrt(-2 * Math.log(ctx.random() || 1e-12)) * Math.cos(2 * Math.PI * ctx.random())
    for (let i = 0; i < this.grid.length; i++) {
      const a = c.win[i] + 1
      const m = a + c.loss[i] + 1
      const draw = a / m + this.params.explore * n * Math.sqrt((a * (m - a)) / (m * m * (m + 1)))
      cap = Math.min(cap, Math.max(0, draw))
      const value = (this.grid[i] - cost) * cap
      if (value > best) {
        best = value
        bestZ = this.grid[i]
      }
    }
    if (best <= 0) return null
    return (bestZ * unit * this.params.shade) / ctx.listCents
  }

  override onOutcome(o: Outcome, won: boolean): void {
    const c = this.cellsOf(o.request)
    const unit = this.anchor(o.request)
    for (let i = 0; i < this.grid.length; i++) {
      c.win[i] *= this.params.decay
      c.loss[i] *= this.params.decay
    }
    const zOf = (kind: OptionKind) => (o.prices[kind] ?? 0) / (unit * this.ladder(kind))
    if (won && o.won) {
      const z = zOf(o.won)
      for (let i = 0; i < this.grid.length; i++) if (this.grid[i] <= z + 1e-9) c.win[i]++
    } else {
      const kinds = Object.keys(o.prices) as OptionKind[]
      if (kinds.length === 0) return
      const z = Math.min(...kinds.map(zOf))
      for (let i = 0; i < this.grid.length; i++) if (this.grid[i] >= z - 1e-9) c.loss[i]++
    }
  }
}

export const isotone = priced(OWN, Isotone)
