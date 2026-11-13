/** Drivers who live near each place: the count the lane offsets pool by. */
import type { DriverProfile, WorldMap } from '../../../vendor/spread-typescript/types.ts'

const NEAR_KM = 30 // a driver's app notifies them of gigs within 30 km of home (RULES.md)

/** For each place of the map, the drivers whose home is within `km` of it in a straight line. */
export function driversNear(roster: DriverProfile[], map: WorldMap, km: number = NEAR_KM): Record<string, number> {
  const homes: Record<string, number> = {}
  for (const driver of roster) homes[driver.homePlaceId] = (homes[driver.homePlaceId] ?? 0) + 1
  const near: Record<string, number> = {}
  for (const place of map.places) {
    near[place.id] = map.places.reduce((n, home) => n + (distance(place, home) <= km ? (homes[home.id] ?? 0) : 0), 0)
  }
  return near
}

/** Great-circle distance in km. */
function distance(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * rad) / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}
