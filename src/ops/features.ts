/** The features of a gig that the fee model learns a multiplier for (SPREAD_AGENT_BRIEF.md, "Design", step 2):
 * the work that the saved weeks show drivers ask more for (findings 9 and 10). */
import type { DeliveryOption, Order, PriceRequest, WorldMap } from '../../vendor/spread-typescript/types.ts'
import { dayOf, isWeekend } from './calendar.ts'
import { road } from './map.ts'

export type Features = {
  privatePickup: boolean // a car is collected at a private address
  privateDelivery: boolean // a car is delivered to a private address
  tradeIn: boolean // two cars: the new car out and the old car back
  premium: boolean // a premium car: experienced drivers only
  weekendDelivery: boolean // a weekend lies between the car's ready day and its deadline, as for a car ready on Friday
  laneKm: number // road km of the first car's trip, 0 when the map has no road
  laneMinutes: number // road minutes of the first car's trip, 0 when the map has no road
}

/** No feature: what work that cannot be read has. */
export const NO_FEATURES: Features = Object.freeze({
  privatePickup: false,
  privateDelivery: false,
  tradeIn: false,
  premium: false,
  weekendDelivery: false,
  laneKm: 0,
  laneMinutes: 0,
})

/** The features of an order, or of a request quoted for `option` (its first option by default). */
export function features(work: Order | PriceRequest, map: WorldMap, option?: DeliveryOption): Features {
  try {
    const legs = work.legs
    const first = legs[0]
    const deadline = option?.deadline ?? ('deadline' in work ? work.deadline : work.options[0]?.deadline)
    const trip = first && road(map, first.pickup.placeId, first.delivery.placeId)
    return {
      privatePickup: legs.some((leg) => leg.pickup.privateAddress),
      privateDelivery: legs.some((leg) => leg.delivery.privateAddress),
      tradeIn: legs.length > 1,
      premium: legs.some((leg) => leg.car.premium),
      weekendDelivery:
        first !== undefined && deadline !== undefined && spansWeekend(first.pickup.window.from, deadline),
      laneKm: trip?.km ?? 0,
      laneMinutes: trip?.minutes ?? 0,
    }
  } catch {
    return NO_FEATURES
  }
}

function spansWeekend(from: number, to: number): boolean {
  const last = Math.min(dayOf(to), dayOf(from) + 6) // any seven days hold a weekend
  for (let day = dayOf(from); day <= last; day++) if (isWeekend(day)) return true
  return false
}
