/** Supply: the drivers who live within 30 km of a place, in a straight line (the notification radius), from the
 * driver list `GET /drivers` read at the start of the week. */
import type { DriverProfile, Place, WorldMap } from '../../../vendor/spread-typescript/types.ts'

const NEAR_KM = 30
/** A place has few drivers near when it has under this share of the drivers near the world's median place. */
const FEW = 0.5

const counts = new WeakMap<DriverProfile[], Map<string, number>>()

function km(a: Place, b: Place): number {
  const rad = Math.PI / 180
  const h =
    Math.sin(((b.lat - a.lat) * rad) / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(h))
}

/** Drivers near each place of the map, counted once for each driver list. */
function nearCounts(drivers: DriverProfile[], map: WorldMap): Map<string, number> {
  let near = counts.get(drivers)
  if (near) return near
  const homes = new Map<string, number>()
  for (const driver of drivers) homes.set(driver.homePlaceId, (homes.get(driver.homePlaceId) ?? 0) + 1)
  const places = new Map(map.places.map((place) => [place.id, place]))
  near = new Map()
  for (const place of map.places) {
    let n = 0
    for (const [home, count] of homes) {
      const at = places.get(home)
      if (at && km(place, at) <= NEAR_KM) n += count
    }
    near.set(place.id, n)
  }
  counts.set(drivers, near)
  return near
}

/** Drivers who live within 30 km of `region`, a place id. */
export function supply(region: string, drivers: DriverProfile[], map: WorldMap): number {
  return nearCounts(drivers, map).get(region) ?? 0
}

/** True when `place` has under half the drivers near the world's median place: the fee extra `fewDriversNear`. */
export function fewDriversNear(place: string, drivers: DriverProfile[], map: WorldMap): boolean {
  const near = nearCounts(drivers, map)
  const sorted = [...near.values()].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)] ?? 0
  return (near.get(place) ?? 0) < FEW * median
}
