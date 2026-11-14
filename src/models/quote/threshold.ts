/** The threshold model (src/params/threshold.json, from analysis/threshold_model.py): the part of a request's
 * threshold that is predictable across worlds from what is known at quote time, as a log offset from the world-day
 * level. Pickup and delivery town, a premium car, a private address and list / typical fee carry it; the dealer id
 * does not transfer between worlds and is left out. */
import { readFileSync } from 'node:fs'
import type { PriceRequest } from '../../../vendor/spread-typescript/types.ts'

type Table = { intercept: number; listFee: number; cats: Record<string, Record<string, number>> }

let table: Table | null = null
const load = (): Table =>
  (table ??= JSON.parse(readFileSync(new URL('../../params/threshold.json', import.meta.url), 'utf8')) as Table)

/** The log offset of the threshold of `option` of the request; 0 for what the table does not know. */
export function thresholdOffset(request: PriceRequest, option: string): number {
  const t = load()
  const legs = request.legs
  const leg = legs[0]
  const list = request.options.find((o) => o.kind === option)?.listPriceCents
  if (!leg || !list) return 0
  const cat = (name: string, value: string) => t.cats[name]?.[value] ?? 0
  const premium = legs.some((l) => l.car.premium)
  const priv = legs.some((l) => l.pickup.privateAddress || l.delivery.privateAddress)
  const fee = request.referenceFeeCents
  return (
    t.intercept +
    cat('pickup', leg.pickup.placeId) +
    cat('delivery', leg.delivery.placeId) +
    cat('premium', premium ? 'True' : 'False') +
    cat('private', priv ? 'True' : 'False') +
    (fee > 0 ? t.listFee * Math.log(list / fee) : 0)
  )
}
