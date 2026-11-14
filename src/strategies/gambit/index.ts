/** gambit: every dealer is a poker opponent with a private, drifting threshold level. A Bayesian filter over a grid
 * of levels per dealer learns it from wins and losses; each request is priced at the expected-profit optimum under
 * that belief, plus a deliberate bluff (a step or two higher) to probe the dealer, more often for big dealers. */
import { DAY } from '../../ops/index.ts'
import { type BaseParams, type OptionKind, type Outcome, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  /** Level grid (within_3_days-equivalent multiple of list at trust 0), log-spaced. */
  gridLow: 0.75,
  gridHigh: 2.1,
  gridStep: 0.025,
  /** Prior over the level: log-normal around `priorMid` with log-sd `priorSd`. */
  priorMid: 1.2,
  priorSd: 0.18,
  /** Request-to-request scatter of the threshold (log-sd). */
  noise: 0.16,
  /** Likelihood tempering: 1 is exact Bayes. */
  learn: 0.8,
  /** Each morning, mix this share of each level's weight into its neighbours. */
  drift: 0.15,
  /** A dealer we won at least `undercutWins` from yesterday, mostly, is undercut: shift the belief down this many steps. */
  undercutWins: 3,
  undercutSteps: 2,
  /** Option ladder over within_3_days. */
  nextDay: 1.13,
  sameDay: 1.367,
  /** Each trust point raises the threshold this much. */
  trustStep: 0.01,
  /** Value of a win beyond its margin, as a share of list: negative is the shadow cost of a driver slot. */
  winBonus: -0.12,
  /** Bluff: probability `bluff` + `bluffShare` × dealer share (capped at `bluffMax`), one or two `bluffStep` up. */
  bluff: 0.08,
  bluffShare: 0.5,
  bluffMax: 0.25,
  bluffStep: 0.05,
  /** Price search range and step (multiple of list). */
  priceLow: 0.9,
  priceHigh: 2.6,
  priceStep: 0.01,
}
type P = typeof OWN & BaseParams

const phi = (x: number): number => {
  // Normal CDF (Abramowitz-Stegun 7.1.26).
  const t = 1 / (1 + 0.3275911 * Math.abs(x / Math.SQRT2))
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) *
      t *
      Math.exp(-(x * x) / 2)
  return x >= 0 ? (1 + y) / 2 : (1 - y) / 2
}

class Gambit extends PricedStrategy<P> {
  private readonly levels: number[] = []
  private readonly beliefs = new Map<string, number[]>()
  private readonly today = new Map<string, { won: number; lost: number }>()
  private day = -1

  private grid(): number[] {
    if (this.levels.length === 0)
      for (let l = Math.log(this.params.gridLow); l <= Math.log(this.params.gridHigh); l += this.params.gridStep)
        this.levels.push(Math.exp(l))
    return this.levels
  }

  private norm(w: number[]): number[] {
    const s = w.reduce((a, b) => a + b, 0) || 1
    return w.map((x) => x / s)
  }

  private belief(dealer: string): number[] {
    let w = this.beliefs.get(dealer)
    if (w) return w
    const all = [...this.beliefs.values()]
    const { priorMid, priorSd } = this.params
    w =
      all.length > 0
        ? this.norm(this.grid().map((_, i) => all.reduce((a, b) => a + (b[i] ?? 0), 0)))
        : this.norm(this.grid().map((l) => Math.exp(-((Math.log(l / priorMid) / priorSd) ** 2) / 2)))
    this.beliefs.set(dealer, w)
    return w
  }

  /** Probability a dealer at level `l` accepts an equivalent ratio `r`. */
  private accept(r: number, l: number): number {
    return 1 - phi(Math.log(r / l) / this.params.noise)
  }

  private factor(kind: OptionKind, trust: number): number {
    const f = kind === 'same_day' ? this.params.sameDay : kind === 'next_day' ? this.params.nextDay : 1
    return f * (1 + this.params.trustStep * trust)
  }

  private morning(now: number): void {
    const day = Math.floor(now / DAY)
    if (this.day < 0) this.day = day
    for (; this.day < day; this.day++) {
      const d = this.params.drift
      for (const [dealer, w] of this.beliefs) {
        let next = w.map((x, i) => (1 - d) * x + (d / 2) * ((w[i - 1] ?? x) + (w[i + 1] ?? x)))
        const t = this.today.get(dealer)
        if (t && t.won >= this.params.undercutWins && t.won > t.lost) {
          const k = this.params.undercutSteps
          next = next.map((_, i) => next[Math.min(next.length - 1, i + k)] ?? 0)
        }
        this.beliefs.set(dealer, this.norm(next))
      }
      this.today.clear()
    }
  }

  price(ctx: PriceCtx): number | null {
    this.morning(ctx.now)
    const w = this.belief(ctx.dealerId)
    const levels = this.grid()
    const f = this.factor(ctx.option.kind, ctx.trust)
    const list = ctx.listCents
    let best = this.params.priceLow
    let bestValue = -Infinity
    for (let r = this.params.priceLow; r <= this.params.priceHigh; r += this.params.priceStep) {
      let p = 0
      for (let i = 0; i < levels.length; i++) p += (w[i] ?? 0) * this.accept(r / f, levels[i] ?? 1)
      const value = (r * list - ctx.costCents + this.params.winBonus * list) * p
      if (value > bestValue) {
        bestValue = value
        best = r
      }
    }
    const rate = Math.min(this.params.bluffMax, this.params.bluff + this.params.bluffShare * ctx.dealerShare)
    if (ctx.random() < rate) best *= 1 + this.params.bluffStep * (ctx.random() < 0.5 ? 1 : 2)
    return best
  }

  override onOutcome(outcome: Outcome, won: boolean): void {
    const { request, prices } = outcome
    const dealer = request.dealerId
    const trust = this.t.trust.get(dealer) ?? 0
    const ratio = (kind: OptionKind): number | null => {
      const option = request.options.find((o) => o.kind === kind)
      const cents = prices[kind]
      return option && cents ? cents / option.listPriceCents / this.factor(kind, trust) : null
    }
    let r: number | null = null
    if (won && outcome.won) r = ratio(outcome.won)
    else
      for (const kind of Object.keys(prices) as OptionKind[]) {
        const x = ratio(kind)
        if (x !== null && (r === null || x < r)) r = x
      }
    if (r === null) return
    const eq = r
    const w = this.belief(dealer)
    const levels = this.grid()
    const next = w.map((x, i) => {
      const a = this.accept(eq, levels[i] ?? 1)
      return x * Math.max(1e-6, won ? a : 1 - a) ** this.params.learn
    })
    this.beliefs.set(dealer, this.norm(next))
    const t = this.today.get(dealer) ?? { won: 0, lost: 0 }
    if (won) t.won++
    else t.lost++
    this.today.set(dealer, t)
  }
}

export const gambit = priced(OWN, Gambit)
