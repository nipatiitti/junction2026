/** The dealer prior: the part of a dealer's limit that is the same in every world, fitted once on the recorded quotes
 * (analysis/dealer/README.md). For one option of one request it gives the log of the limit over the list price, from
 * what the desk sees when the request arrives: the option and how many the dealer offers, the two places and their
 * lane, the list price, and how this dealer knows us (orders on time, late orders, requests won and lost). The level
 * of the week's world and of the day is not in it: `Demand` learns that from the week's own wins and losses. */
import { readFileSync } from 'node:fs'
import type { DeliveryOption, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'

type Table = Record<string, number>
export type Prior = {
  /** The noise that stays in one request's limit, as a logistic scale in log price. */
  scale: number
  base: number
  /** How far a world's level, and a day's level in its world, lie from the mean: variances in log price. */
  worldVariance: number
  dayVariance: number
  /** What this week's dealers and places may still differ by, and the doubt they gain back each morning. */
  placeVariance: number
  placeDrift: number
  option: Table
  offered: Table
  optionOffered: Table
  from: Table
  to: Table
  lane: Table
  listEdges: number[]
  list: number[]
  logList: number
  logRefOverList: number
  trust: number
  late: number
  winBalance: number
  winShare: number
}

/** How one dealer knows us when its request arrives. */
export type DealerState = {
  /** The trust count of the rules: orders on time, 25 at most, halved by a late one. */
  onTime: number
  /** Its orders that arrived late so far. */
  late: number
  /** Its earlier requests that we won and lost. */
  won: number
  lost: number
}

export const loadPrior = (): Prior =>
  JSON.parse(readFileSync(new URL('./prior.json', import.meta.url), 'utf-8')) as Prior

/** The log of the limit over the list price that the prior expects, before the week's level. */
export function priorMu(prior: Prior, request: PriceRequest, option: DeliveryOption, dealer: DealerState): number {
  const leg = request.legs[0]
  const from = leg?.pickup.placeId ?? ''
  const to = leg?.delivery.placeId ?? ''
  const offered = String(Math.min(3, Math.max(1, request.options.length)))
  const list = option.listPriceCents
  const band = prior.listEdges.filter((edge) => edge < list).length
  const decided = dealer.won + dealer.lost + 10
  return (
    prior.base +
    (prior.option[option.kind] ?? 0) +
    (prior.offered[offered] ?? 0) +
    (prior.optionOffered[`${option.kind}/${offered}`] ?? 0) +
    (prior.from[from] ?? 0) +
    (prior.to[to] ?? 0) +
    (prior.lane[`${from}>${to}`] ?? 0) +
    (prior.list[band] ?? 0) +
    prior.logList * Math.log(list / 5000) +
    prior.logRefOverList * Math.log(request.referenceFeeCents / list) +
    prior.trust * Math.log(1 + Math.min(25, dealer.onTime) / 100) +
    (prior.late * Math.min(8, dealer.late)) / 8 +
    (prior.winBalance * (dealer.won - dealer.lost)) / decided +
    (prior.winShare * dealer.won) / decided
  )
}
