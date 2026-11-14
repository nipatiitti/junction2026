/** flat: a fixed markup per option over the list price, a little more for a trusting dealer. The example strategy on
 * the shared base (src/strategies/base/): admission, the capacity brake, gigs and fees all come from there. */
import { type BaseParams, type OptionKind, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = { sameDay: 1.42, nextDay: 1.36, within3: 1.3, trustStep: 0.008 }

class Flat extends PricedStrategy<typeof OWN & BaseParams> {
  price(ctx: PriceCtx): number {
    const markup: Record<OptionKind, number> = {
      same_day: this.params.sameDay,
      next_day: this.params.nextDay,
      within_3_days: this.params.within3,
    }
    return markup[ctx.option.kind] * (1 + this.params.trustStep * ctx.trust)
  }
}

export const flat = priced(OWN, Flat)
