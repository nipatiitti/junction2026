/** `unseenRule`: gigs no driver sees. A driver's app notifies them of a gig whose first pickup is within 30 km of
 * their home, and drivers follow gigs near where they are, so a pickup with few roster drivers living near gets
 * few views and books late whatever its fee (analysis/unseen.py). Leave such options out of the quote. */
import type { DeliveryOption, DriverProfile, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import type { WorldMap } from '../../../vendor/spread-typescript/types.ts'
import { driversNear } from '../../models/quote/index.ts'

export type Unseen = { near: Record<string, number>; map: WorldMap; removed: { quotes: number; options: number } }
type Rule = { unseenMin: number; unseenLegKm: number }

export function newUnseen(roster: DriverProfile[], map: WorldMap, km: number): Unseen {
  return { near: driversNear(roster, map, km), map, removed: { quotes: 0, options: 0 } }
}

/** Whether the request's first leg is short (under `unseenLegKm` in a straight line) or its pickup has at least
 * `unseenMin` roster drivers living within the rule's radius. */
export function seen(unseen: Unseen, request: PriceRequest, rule: Rule): boolean {
  const leg = request.legs[0]
  if (!leg) return true
  const at = (id: string) => unseen.map.places.find((p) => p.id === id)
  const a = at(leg.pickup.placeId)
  const b = at(leg.delivery.placeId)
  if (a && b && km(a, b) < rule.unseenLegKm) return true
  return (unseen.near[leg.pickup.placeId] ?? 0) >= rule.unseenMin
}

function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * rad) / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

/** The options left after the rule, counting what it removed. */
export function keepSeen(unseen: Unseen, request: PriceRequest, options: DeliveryOption[], rule: Rule) {
  if (options.length === 0 || seen(unseen, request, rule)) return options
  unseen.removed.quotes += 1
  unseen.removed.options += options.length
  return []
}
