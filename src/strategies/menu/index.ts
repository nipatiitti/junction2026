/** menu: price a request's options as one menu. A dealer has one hidden threshold (a world level × region × trust ×
 * a lognormal draw), faster options sell at fixed ratios above slower ones, and among the options under threshold the
 * dealer takes the fastest with a probability that falls with its premium over the cheapest. The menu that maximises
 * expected profit over the draw is computed once per request and cached; the world level learns from wins and
 * losses. */
import type { DeliveryOption } from '../../../vendor/spread-typescript/spread.ts'
import { type BaseParams, type Outcome, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  /** Median threshold / list at trust 0 and its lognormal spread. */
  median: 1.29,
  sigma: 0.19,
  /** Region multipliers on the median: capital (Helsinki, Espoo, Vantaa, Hyvinkää) and elsewhere. */
  capital: 0.9,
  other: 1.06,
  /** Threshold × (1 + trustStep × min(trust, trustCap)). */
  trustStep: 0.025,
  trustCap: 16,
  /** Threshold ratios: next_day over within_3_days, same_day over next_day. */
  nextRatio: 1.13,
  sameRatio: 1.21,
  /** The menu grid, as multiples of each option's list. */
  gridLo: 1.0,
  gridHi: 2.4,
  gridStep: 0.05,
  /** Value of a win beyond its margin (future trust), × list; extra cost of same_day (lateness risk), × list. */
  winValue: 0.12,
  sameDayRisk: 0.04,
  /** Learning rate of the world level (log scale), and its bounds. */
  eta: 0.03,
  levelLo: 0.75,
  levelHi: 1.4,
  /** Points of the threshold draw. */
  draws: 15,
}
type P = typeof OWN & BaseParams
type Menu = { prices: Map<DeliveryOption['kind'], number>; pWin: number }

const SPEED = { same_day: 0, next_day: 1, within_3_days: 2 }
const CAPITAL = ['helsinki', 'espoo', 'vantaa', 'hyvink']
const CHOICE: [number, number][] = [
  [0, 0.995],
  [0.1, 0.74],
  [0.2, 0.49],
  [0.5, 0.12],
  [1, 0.01],
]
/** Probability the dealer takes the faster option at this premium over the cheaper. */
function fastShare(premium: number): number {
  if (premium <= 0) return CHOICE[0][1]
  for (let i = 1; i < CHOICE.length; i++) {
    const [x0, y0] = CHOICE[i - 1]
    const [x1, y1] = CHOICE[i]
    if (premium <= x1) return y0 + ((y1 - y0) * (premium - x0)) / (x1 - x0)
  }
  return CHOICE.at(-1)?.[1] ?? 0
}

class MenuStrategy extends PricedStrategy<P> {
  private readonly menus = new Map<string, Menu>()
  private logLevel = 0
  private names: Map<string, string> | null = null

  price(ctx: PriceCtx): number | null {
    let menu = this.menus.get(ctx.request.id)
    if (!menu) {
      menu = this.design(ctx)
      this.menus.set(ctx.request.id, menu)
    }
    const p = menu.prices.get(ctx.option.kind)
    return p === undefined ? null : p
  }

  override onOutcome(outcome: Outcome, won: boolean): void {
    const menu = this.menus.get(outcome.request.id)
    if (!menu) return
    const p = this.params
    this.logLevel += p.eta * ((won ? 1 : 0) - menu.pWin)
    this.logLevel = Math.min(Math.log(p.levelHi), Math.max(Math.log(p.levelLo), this.logLevel))
  }

  override summary(): string {
    return `${super.summary()}; menu level ${Math.exp(this.logLevel).toFixed(3)}`
  }

  private isCapital(placeId: string): boolean {
    if (!this.names) this.names = new Map(this.setup.map.places.map((pl) => [pl.id, pl.name.toLowerCase()]))
    const name = this.names.get(placeId) ?? ''
    return CAPITAL.some((c) => name.includes(c))
  }

  /** The expected-profit-maximising menu over the options from the first admitted one on. */
  private design(ctx: PriceCtx): Menu {
    const p = this.params
    const { request } = ctx
    const first = request.options.findIndex((o) => o.kind === ctx.option.kind)
    const opts = request.options.slice(Math.max(0, first)).sort((a, b) => SPEED[a.kind] - SPEED[b.kind])
    const slow = opts.at(-1) ?? ctx.option
    const chainOf = (o: DeliveryOption) =>
      (o.kind === 'same_day' ? p.sameRatio * p.nextRatio : o.kind === 'next_day' ? p.nextRatio : 1) /
      (slow.kind === 'same_day' ? p.sameRatio * p.nextRatio : slow.kind === 'next_day' ? p.nextRatio : 1)
    const region = this.isCapital(request.legs[0]?.delivery.placeId ?? '') ? p.capital : p.other
    const trust = 1 + p.trustStep * Math.min(ctx.trust, p.trustCap)
    const center = p.median * region * trust * Math.exp(this.logLevel) * slow.listPriceCents
    const thresholds = Array.from({ length: p.draws }, (_, i) => {
      const u = (i + 0.5) / p.draws
      const z = 4.91 * (u ** 0.14 - (1 - u) ** 0.14)
      return center * Math.exp(p.sigma * z)
    })
    // Candidate prices (cents) per option, with null (index 0 = left out).
    const cands = opts.map((o) => {
      const cost = this.costOf(request, o, ctx.now) + (o.kind === 'same_day' ? p.sameDayRisk * o.listPriceCents : 0)
      const floor = (this.costOf(request, o, ctx.now) * p.minMargin) / o.listPriceCents
      const list: { m: number; cents: number; gain: number }[] = []
      for (let m = p.gridLo; m <= p.gridHi + 1e-9; m += p.gridStep) {
        if (m < floor) continue
        const cents = m * o.listPriceCents
        list.push({ m, cents, gain: cents - cost + p.winValue * o.listPriceCents })
      }
      return { o, chain: chainOf(o), list }
    })
    let best: Menu = { prices: new Map(), pWin: 0 }
    let bestValue = 0
    const pick = new Array<number>(cands.length).fill(-1)
    const evaluate = () => {
      let value = 0
      let win = 0
      for (const t of thresholds) {
        // Accepted options, fastest first; the dealer walks down the list.
        let rest = 1
        for (let i = 0; i < cands.length && rest > 1e-6; i++) {
          if (pick[i] < 0) continue
          const c = cands[i].list[pick[i]]
          if (c.cents >= t * cands[i].chain) continue
          let cheapest = Infinity
          for (let j = i + 1; j < cands.length; j++) {
            if (pick[j] < 0) continue
            const d = cands[j].list[pick[j]]
            if (d.cents < t * cands[j].chain) cheapest = Math.min(cheapest, d.cents)
          }
          const share = cheapest === Infinity ? 1 : fastShare(c.cents / cheapest - 1)
          value += rest * share * c.gain
          win += rest * share
          rest *= 1 - share
        }
      }
      return { value: value / thresholds.length, win: win / thresholds.length }
    }
    const walk = (i: number) => {
      if (i === cands.length) {
        const { value, win } = evaluate()
        if (value > bestValue) {
          bestValue = value
          const prices = new Map<DeliveryOption['kind'], number>()
          pick.forEach((k, j) => {
            if (k >= 0) prices.set(cands[j].o.kind, cands[j].list[k].m)
          })
          best = { prices, pWin: win }
        }
        return
      }
      for (let k = -1; k < cands[i].list.length; k++) {
        pick[i] = k
        walk(i + 1)
      }
    }
    walk(0)
    return best
  }
}

export const menu = priced(OWN, MenuStrategy)
