/** squeeze: one price curve over the dealer's trust and size. Big dealers get cheap, safe quotes while their trust is
 * low, so they reach high trust fast; then the price climbs a logistic in trust far above 1% per order. Small dealers
 * never build trust in a week, so they pay a high fixed price from the first request. Late in the week investing has
 * no future, so the big dealers' floor rises to the myopic optimum. */
import type { Setup } from '../../strategy.ts'
import { type BaseParams, type OptionKind, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  /** A dealer with at least this share of requests is big; before `warmup` requests every dealer counts as big. */
  bigShare: 0.05,
  warmup: 30,
  /** Big dealers: `lo` at trust 0, rising to `hi` along a logistic centred on `mid` with width `width`. */
  lo: 1.12,
  hi: 1.62,
  mid: 8,
  width: 3,
  /** From this weekday (0 Monday) on, the big dealers' floor is `loLate`: no more investing. */
  lateDay: 3,
  loLate: 1.24,
  /** Small dealers: a fixed multiple, plus `smallTrustStep` per trust point. */
  small: 1.42,
  smallTrustStep: 0.01,
  /** Option factors over the within_3_days curve. */
  nextDay: 1.04,
  sameDay: 1.09,
  /** Deliveries into the capital region pay this factor (they accept less). */
  capital: 0.9,
}

type P = typeof OWN & BaseParams

const CAPITAL = ['helsinki', 'espoo', 'vantaa', 'hyvinkaa']
const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

class Squeeze extends PricedStrategy<P> {
  private readonly capitalPlaces: Set<string>

  constructor(setup: Setup, params: P) {
    super(setup, params)
    this.capitalPlaces = new Set(
      setup.map.places.filter((p) => CAPITAL.some((c) => fold(p.name).includes(c))).map((p) => p.id),
    )
  }

  /** The logistic in trust, rescaled so trust 0 gives `lo` and trust 25 gives `hi`. */
  private curve(trust: number, lo: number): number {
    const p = this.params
    const s = (t: number) => 1 / (1 + Math.exp(-(t - p.mid) / p.width))
    const f = (s(trust) - s(0)) / (s(25) - s(0))
    return lo + (p.hi - lo) * Math.max(0, Math.min(1, f))
  }

  price(ctx: PriceCtx): number {
    const p = this.params
    const big = ctx.t.total < p.warmup || ctx.dealerShare >= p.bigShare
    let base: number
    if (big) {
      const lo = ctx.weekday >= p.lateDay ? Math.max(p.lo, p.loLate) : p.lo
      base = this.curve(ctx.trust, lo)
    } else base = p.small * (1 + p.smallTrustStep * ctx.trust)
    const option: Record<OptionKind, number> = { same_day: p.sameDay, next_day: p.nextDay, within_3_days: 1 }
    const legs = ctx.request.legs
    const capital = legs.length > 0 && legs.every((l) => this.capitalPlaces.has(l.delivery.placeId))
    return base * option[ctx.option.kind] * (capital ? p.capital : 1)
  }
}

export const squeeze = priced(OWN, Squeeze)
