/** Road minutes and kilometres from the world map, indexed once per map. */
import type { Leg, Road, WorldMap } from '../../vendor/spread-typescript/types.ts'

const index = new WeakMap<WorldMap, Map<string, Road>>()

/** The road from one place to another, or undefined when the map has none. */
export function road(map: WorldMap, from: string, to: string): Road | undefined {
  let roads = index.get(map)
  if (!roads) {
    roads = new Map((map.roads ?? []).map((r) => [`${r.from}\n${r.to}`, r]))
    index.set(map, roads)
  }
  return roads.get(`${from}\n${to}`)
}

/** Road minutes between two places: 0 to the same place, Infinity when the map has no road, so a check that
 * needs the drive fails safe. */
export const minutes = (map: WorldMap, from: string, to: string): number =>
  from === to ? 0 : (road(map, from, to)?.minutes ?? Infinity)

/** Road minutes to move the cars one after the other, as one driver would: each car's drive, and the drive from
 * one car's delivery to the next car's pickup. The 12-hour rule for a gig with several cars counts the same. */
export function driveMinutes(map: WorldMap, legs: readonly Leg[]): number {
  let total = 0
  let here: string | undefined
  for (const { pickup, delivery } of legs) {
    if (here !== undefined) total += minutes(map, here, pickup.placeId)
    total += minutes(map, pickup.placeId, delivery.placeId)
    here = delivery.placeId
  }
  return total
}
