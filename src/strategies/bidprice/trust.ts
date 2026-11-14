/** Trust protection (`trustGuard`): what a late order costs besides its refund. A late order halves the dealer's
 * count (RULES.md, dealer trust), and each point of the count lifts the prices that dealer accepts by about 1% on
 * every later request, until our later orders on time have counted it back. The top dealer sends a quarter to a
 * third of a week's requests, so a halving there costs more than the refund; at a dealer who sends little it costs
 * almost nothing. */
import { dealerWeight, type QuoteParams, type QuoteState, requestsLeft, trustOf } from '../../models/quote/index.ts'

/** The points of trust a halving now takes from the dealer, summed over the orders we expect to win from it for the
 * rest of the week: each later win on time counts one point back, and the count would have stopped at the cap. */
export function trustPointsLost(state: QuoteState, dealer: string, now: number, params: QuoteParams): number {
  if (!params.flags.trust) return 0
  const count = trustOf(state, dealer, params)
  const halved = Math.floor(count / 2)
  if (count <= halved) return 0
  const winShare = Math.min(1, Math.max(0.1, (state.wins + 1) / (state.answers + 3)))
  const wins = dealerWeight(state, dealer, params) * requestsLeft(state, now, params) * winShare
  let points = 0
  for (let i = 0; i < wins; i++) {
    const gap = Math.min(params.trustCap, count + i) - Math.min(params.trustCap, halved + i)
    if (gap <= 0) break
    points += gap * Math.min(1, wins - i)
  }
  return points
}

/** The trust a halving loses, as a share of one order's price: the points lost times what a point adds to a price. */
export function trustLossShare(state: QuoteState, dealer: string, now: number, params: QuoteParams): number {
  const perOrder = Math.max(0, state.belief.trust?.[0] ?? params.trustPerOrder)
  return perOrder * trustPointsLost(state, dealer, now, params)
}
