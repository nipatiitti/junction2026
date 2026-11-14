/** The organisers' starter as a strategy: it quotes the first option at its list price and posts each order at
 * rising fees, steep after the deadline warning. It decides exactly as src/dispatch.ts did before the harness. */
import type { PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type Books, type GigNeed, type GigPlan, type Prices, Strategy, type StrategyKind } from '../../strategy.ts'
import { starterGig } from './gig.ts'

export type StarterParams = {
  /** The quote over the list price: 1 quotes at list. */
  markup: number
}

class Starter extends Strategy<StarterParams> {
  quote(request: PriceRequest): Prices {
    const first = request.options[0]!
    return { [first.kind]: Math.round(first.listPriceCents * this.params.markup) }
  }

  gig(need: GigNeed, books: Books): GigPlan {
    return starterGig(need, books, this.setup.level)
  }
}

export const starter: StrategyKind<StarterParams> = {
  defaults: { markup: 1 },
  build: (setup, params) => new Starter(setup, params),
}
