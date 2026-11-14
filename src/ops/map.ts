/** What the ops know of the world besides the order itself, and the road minutes of its map. */
import type { Leg, Road, WorldMap } from '../../vendor/spread-typescript/types.ts'
import type { Snowfall } from './windows.ts'

/** The world around an order, as plain data. */
export type Context = {
  map: WorldMap // `client.map()`, loaded once
  forecasts?: readonly Snowfall[] // the `forecast` events so far
  level?: number // the practice level, 1 to 8; the final is 8
  /** How tight admission is, from 1 (the on-time share is at its target) down to 0.25 (at the delivery minimum):
   * the slack an option needs grows as it falls. */
  tightening?: number
  /** Rule 3 by the route: a charging stop only on a drive over 200 road km (charging.ts). */
  chargeOver200?: boolean
}

const index = new WeakMap<WorldMap, Map<string, Road>>()

/** The road from one place to another, or undefined when the map has none. */
export function road(map: WorldMap | undefined, from: string, to: string): Road | undefined {
  if (typeof map !== 'object' || map === null) return undefined
  let roads = index.get(map)
  if (!roads) {
    roads = new Map((map.roads ?? []).map((r) => [`${r.from}\n${r.to}`, r]))
    index.set(map, roads)
  }
  return roads.get(`${from}\n${to}`)
}

/** Road minutes between two places: 0 to the same place, Infinity when the map has no road, so a check that
 * needs the drive fails safe. */
export const minutes = (map: WorldMap | undefined, from: string, to: string): number =>
  from === to ? 0 : (road(map, from, to)?.minutes ?? Infinity)

/** Road minutes to move the cars one after the other, as one driver would: each car's drive, and the drive from
 * one car's delivery to the next car's pickup. The 12-hour rule for a gig with several cars counts the same. */
export function driveMinutes(map: WorldMap | undefined, legs: readonly Leg[]): number {
  let total = 0
  let here: string | undefined
  for (const { pickup, delivery } of legs) {
    if (here !== undefined) total += minutes(map, here, pickup.placeId)
    total += minutes(map, pickup.placeId, delivery.placeId)
    here = delivery.placeId
  }
  return total
}
