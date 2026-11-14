/** Rule 3 of RULES.md: "An electric car below 30% charge on a route over 200 km needs a charging stop." The route is
 * the car's own drive, pickup to delivery, by the road km of the map. Behind `Context.chargeOver200`; off, every
 * electric car under 30% gets the stop, as before. */
import type { Car } from '../../vendor/spread-typescript/types.ts'
import { type Context, road } from './map.ts'

/** A route longer than this many road km needs the charging stop. */
export const CHARGE_KM = 200

/** How many cars the route rule spared a charging stop: posted gigs and checked quotes. */
export const charging = { gigsSpared: 0, quotesSpared: 0 }

const low = (car: Car): boolean => car.electric && car.chargePercent !== null && car.chargePercent < 30

/** Whether the car's drive from `from` to `to` needs a charging stop. A route the map has no km for keeps the stop. */
export function needsCharging(car: Car, from: string, to: string, context: Context): boolean {
  if (!low(car)) return false
  if (!context.chargeOver200) return true
  const km = road(context.map, from, to)?.km
  return km === undefined || !Number.isFinite(km) || km > CHARGE_KM
}
