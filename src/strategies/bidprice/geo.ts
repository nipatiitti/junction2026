/** `geoCost`: the cost `c` of a request from where drivers live and from our own orders (HANDBOOK.md "a gig that ends
 * near a driver's home, or near their next pickup, is cheap for that driver"). A factor on `c`:
 * - per doubling of the roster drivers within 30 km of the delivery (pickup) over the world's median place,
 *   `geoDel` (`geoPick`) of `c`, the log ratio capped at ±2 doublings;
 * - `geoChain` of `c` once when one of our open orders delivers within `chainKm` of the pickup in the `chainHours`
 *   before its pickup window (a return leg among them), or picks up at the same yard within `chainHours`;
 * kept inside [`geoMin`, `geoMax`]. Not fitted: sensible starting sizes. Plain data, from the setup and the orders. */
import type { DriverProfile, Order, Place, PriceRequest, WorldMap } from '../../../vendor/spread-typescript/types.ts'
import { HOUR } from '../../time.ts'

export type GeoParams = {
  geoDel: number
  geoPick: number
  geoChain: number
  chainKm: number
  chainHours: number
  geoMin: number
  geoMax: number
}

export type Geo = {
  places: Map<string, Place>
  near: Map<string, number>
  median: number
  tally: { quotes: number; under: number; over: number; chains: number }
  counted: Set<string>
}

const NEAR_KM = 30

function km(a: Place | undefined, b: Place | undefined): number {
  if (!a || !b) return Number.POSITIVE_INFINITY
  const rad = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * rad) / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

export function newGeo(roster: DriverProfile[], map: WorldMap): Geo {
  const places = new Map(map.places.map((place) => [place.id, place]))
  const homes = roster.map((driver) => places.get(driver.homePlaceId))
  const near = new Map(map.places.map((place) => [place.id, homes.filter((home) => km(place, home) <= NEAR_KM).length]))
  const sorted = [...near.values()].sort((a, b) => a - b)
  const median = Math.max(1, sorted[Math.floor(sorted.length / 2)] ?? 1)
  return { places, near, median, tally: { quotes: 0, under: 0, over: 0, chains: 0 }, counted: new Set() }
}

/** Doublings of the drivers near `placeId` over the median place, capped at ±2. */
function doublings(geo: Geo, placeId: string): number {
  const n = geo.near.get(placeId) ?? 0
  return Math.max(-2, Math.min(2, Math.log2((n + 0.5) / geo.median)))
}

/** Whether one of our open orders chains with this request: it delivers near the pickup shortly before, it is the
 * other way round (a return leg), or it is a car from the same yard on the same day. */
export function chains(geo: Geo, request: PriceRequest, orders: Iterable<Order>, p: GeoParams): boolean {
  const leg = request.legs[0]
  if (!leg) return false
  const pickup = geo.places.get(leg.pickup.placeId)
  const from = leg.pickup.window.from
  for (const order of orders) {
    for (const [i, theirs] of order.legs.entries()) {
      if (order.deliveredAt[i] != null) continue
      const theirDelivery = geo.places.get(theirs.delivery.placeId)
      const before =
        km(theirDelivery, pickup) <= p.chainKm &&
        theirs.delivery.window.from <= leg.pickup.window.to &&
        theirs.delivery.window.to >= from - p.chainHours * HOUR
      // A return leg is a chain that also ends near their pickup: the timing test of `before` covers it.
      const sameYard =
        theirs.pickup.placeId === leg.pickup.placeId &&
        Math.abs(theirs.pickup.window.from - from) <= p.chainHours * HOUR
      if (before || sameYard) return true
    }
  }
  return false
}

/** The factor on `c`, counted in the tally once for each quote (`count`). */
export function geoFactor(
  geo: Geo,
  request: PriceRequest,
  orders: Iterable<Order>,
  p: GeoParams,
  count: boolean,
): number {
  const leg = request.legs[0]
  if (!leg) return 1
  const chained = chains(geo, request, orders, p)
  const raw =
    1 +
    p.geoDel * doublings(geo, leg.delivery.placeId) +
    p.geoPick * doublings(geo, leg.pickup.placeId) +
    (chained ? p.geoChain : 0)
  const factor = Math.max(p.geoMin, Math.min(p.geoMax, raw))
  if (count && !geo.counted.has(request.id)) {
    geo.counted.add(request.id)
    geo.tally.quotes++
    if (factor < 0.95) geo.tally.under++
    if (factor > 1.05) geo.tally.over++
    if (chained) geo.tally.chains++
  }
  return factor
}

export function geoSummary(geo: Geo): string {
  const { quotes, under, over, chains } = geo.tally
  return `geo: ${quotes} requests, factor <0.95 ${under}, >1.05 ${over}, chain discounts ${chains}`
}
