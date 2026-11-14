/** The price of a quote: for each option we can serve, the price on a grid that maximises the expected profit
 * `(p − c) × W(p)`, plus the value of the trust a win adds, with several options priced as one decision. */
import type { PriceRequest } from '../../../vendor/spread-typescript/types.ts'
import { level, winShare } from './belief.ts'
import { quantile, shapeOf } from './flips.ts'
import { OPTIONS, type Option, type QuoteParams } from './params.ts'
import { dealerWeight, inWar, type QuoteState, requestsLeft, requestTerms, trustOf } from './state.ts'

export type QuoteDecision = {
  /** Cents for each option to quote: ready for a `quote` action. A decline quotes far above the list price. */
  prices: Partial<Record<Option, number>>
  /** The expected profit in cents, the trust a win adds included. */
  valueCents: number
  /** The chance that the dealer takes one of the prices. */
  winProb: number
  decline: boolean
}

/** The chance that the dealer accepts `price` (cents) for `option` of the request, from the flip distribution
 * shifted by what we believe of the world, the day, the lane, the option and this dealer's trust. */
export function winProb(price: number, option: Option, request: PriceRequest, state: QuoteState, params: QuoteParams) {
  const list = request.options.find((o) => o.kind === option)?.listPriceCents
  if (!list || price <= 0) return 0
  const { mean, variance } = level(state.belief, requestTerms(state, request, option, params))
  return winShare(shapeOf(params), Math.log(price / list), mean, variance)
}

/** The quote for a request. `costByOption` holds, in cents, the expected cost of each option we can serve (fee
 * and lateness); an option left out is not offered. Each option gets the price that maximises its expected
 * profit, and a faster option can be offered at a premium over a slower one where the dealer's taste for speed
 * (the choice curve) pays for it; a faster option is never offered cheaper than a slower one, since the dealer
 * would take it anyway. Declines when the best value is under `params.minValueCents`, or in a price war with
 * `war: 'decline'`. */
export function bestQuote(
  request: PriceRequest,
  costByOption: Partial<Record<Option, number>>,
  state: QuoteState,
  params: QuoteParams,
  now: number = request.arrivedAt,
): QuoteDecision {
  const offers = OPTIONS.flatMap((kind) => {
    const option = request.options.find((o) => o.kind === kind)
    const cost = costByOption[kind]
    return option && cost !== undefined && Number.isFinite(cost) ? [{ kind, list: option.listPriceCents, cost }] : []
  })
  if (offers.length === 0 || inWar(state, now, params)) return decline(request, params)
  const shape = shapeOf(params)
  const lo = Math.min(...offers.map((o) => o.list)) * params.gridFrom
  const hi = Math.max(...offers.map((o) => o.list)) * params.gridTo
  const prices = Array.from({ length: Math.ceil(Math.log(hi / lo) / params.gridStep) + 1 }, (_, j) =>
    Math.round(lo * Math.exp(j * params.gridStep)),
  )
  const options = offers.map((offer) => {
    const { mean, variance } = level(state.belief, requestTerms(state, request, offer.kind, params))
    const win = prices.map((p) => winShare(shape, Math.log(p / offer.list), mean, variance))
    return { ...offer, mean, win }
  })

  if (params.flags.pricing === 'median') {
    const median = quantile(shape, 0.5)
    const quoted = options.map((o) => ({ ...o, price: Math.round(o.list * Math.exp(o.mean + median)) }))
    const lead = quoted[0]
    const w = winProb(lead.price, lead.kind, request, state, params)
    return decide(
      request,
      params,
      Object.fromEntries(quoted.map((o) => [o.kind, o.price])),
      w * (lead.price - lead.cost),
      w,
    )
  }

  // Each option alone, first without the trust a win adds, to know what a request of this dealer earns.
  const solo = (bonus: number) => {
    let best = { value: -Infinity, win: 0, revenue: 0, quote: {} as Partial<Record<Option, number>> }
    for (const o of options) {
      for (let j = 0; j < prices.length; j++) {
        const value = prices[j] >= o.cost ? o.win[j] * (prices[j] - o.cost + bonus) : -Infinity
        if (value > best.value)
          best = { value, win: o.win[j], revenue: o.win[j] * prices[j], quote: { [o.kind]: prices[j] } }
      }
    }
    return best
  }
  const bonus = trustBonus(request, state, params, now, Math.max(0, solo(0).revenue))
  let best = solo(bonus)

  // A slower option as the lead, and a faster one at a premium k grid steps above it: the dealer takes one of them
  // when either price is under its flip, and the fastest with the share of the choice curve.
  const steps = Math.floor(Math.log(1 + params.maxPremium) / params.gridStep)
  for (let f = 0; f < options.length; f++) {
    for (let l = f + 1; l < options.length; l++) {
      const fast = options[f]
      const slow = options[l]
      for (let k = 1; k <= steps; k++) {
        const share = choice(params, Math.exp(k * params.gridStep) - 1)
        for (let j = 0; j + k < prices.length; j++) {
          const pSlow = prices[j]
          const pFast = prices[j + k]
          if (pSlow < slow.cost || pFast < fast.cost) continue
          const win = Math.max(slow.win[j], fast.win[j + k])
          const value = win * (share * (pFast - fast.cost) + (1 - share) * (pSlow - slow.cost) + bonus)
          if (value > best.value) best = { value, win, revenue: 0, quote: { [fast.kind]: pFast, [slow.kind]: pSlow } }
        }
      }
    }
  }
  return decide(request, params, best.quote, best.value, best.win)
}

/** The value of the trust that a win adds, in cents: each order on time lifts the price this dealer accepts by
 * `trustPerOrder` on its later requests, which is worth that share of their expected revenue (the envelope
 * theorem), until the dealer's count would have reached the cap anyway. With `trustMinShare`, `trustUntil` and
 * `trustLagHours` the bonus is kept to the dealers who send most of the requests, to the start of their count, and to
 * the requests that come after the order is delivered. */
export function trustBonus(
  request: PriceRequest,
  state: QuoteState,
  params: QuoteParams,
  now: number,
  revenue: number,
): number {
  const trust = trustOf(state, request.dealerId, params)
  if (!params.flags.trust || params.trustValue <= 0 || trust >= Math.min(params.trustCap, params.trustUntil)) return 0
  const weight = dealerWeight(state, request.dealerId, params)
  if (weight < params.trustMinShare) return 0
  const perOrder = Math.max(0, state.belief.trust?.[0] ?? params.trustPerOrder)
  const later = weight * requestsLeft(state, now, params, now + params.trustLagHours * 60)
  const winShare = Math.min(1, Math.max(0.1, (state.wins + 1) / (state.answers + 3)))
  return params.trustValue * perOrder * revenue * Math.min(later, (params.trustCap - trust) / winShare)
}

/** The share of wins where the dealer takes the fastest option at this premium over the cheapest. */
function choice(params: QuoteParams, premium: number): number {
  const xs = params.choicePremium
  const ys = params.choiceFastest
  if (premium <= xs[0]) return ys[0]
  for (let i = 1; i < xs.length; i++) {
    if (premium <= xs[i]) return ys[i - 1] + ((premium - xs[i - 1]) / (xs[i] - xs[i - 1])) * (ys[i] - ys[i - 1])
  }
  return ys[ys.length - 1]
}

function decide(
  request: PriceRequest,
  params: QuoteParams,
  prices: Partial<Record<Option, number>>,
  value: number,
  win: number,
): QuoteDecision {
  if (!(value >= params.minValueCents)) return decline(request, params)
  return { prices, valueCents: value, winProb: win, decline: false }
}

function decline(request: PriceRequest, params: QuoteParams): QuoteDecision {
  const first = request.options[0]
  const prices = first ? { [first.kind]: Math.round(first.listPriceCents * params.declineFactor) } : {}
  return { prices, valueCents: 0, winProb: 0, decline: true }
}
