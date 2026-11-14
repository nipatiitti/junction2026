/** A driver who is late (HANDBOOK.md, `driver_late`): "release them without a fee until they leave, and find a driver
 * who can come earlier". Behind `driverLate`. We release only when the late driver would deliver after the order's
 * deadline, the driver has not left, and another driver can plausibly still make it: `lateLeadHours` for the urgent
 * schedule to book and reach the pickup before `lastPickupAt`, and that pickup at least `lateGainHours` before the
 * late driver's. The cars go again at the urgent fees. Its state comes from `observe` and `sent` alone. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  DriverLateEvent,
  Order,
  WorldMap,
} from '../../../vendor/spread-typescript/spread.ts'
import { driveMinutes, HOUR } from '../../ops/index.ts'
import type { OurGig } from './log.ts'

export type LateParams = { lateLeadHours: number; lateGainHours: number }

export class LateDrivers {
  readonly started = new Set<string>() // gigs whose driver has left
  readonly released = new Set<string>() // orders whose late driver we released: their cars take the urgent fees
  readonly tally = { seen: 0, onTime: 0, noTime: 0, left: 0, released: 0, refused: 0, delivered: 0, deliveredLate: 0 }

  observe(event: DeskEvent, orders: ReadonlyMap<string, Order>): void {
    if (event.kind === 'gig_started') this.started.add(event.gigId)
    else if (event.kind === 'delivered' && this.released.has(event.orderId)) {
      this.tally.delivered++
      const order = orders.get(event.orderId)
      if (order && event.at > order.deadline) this.tally.deliveredLate++
    }
  }

  /** Whether to release the late driver of a gig of ours now. */
  decide(
    event: DriverLateEvent,
    gig: OurGig | undefined,
    order: Order | undefined,
    map: WorldMap,
    now: number,
    p: LateParams,
  ): boolean {
    this.tally.seen++
    if (!gig || !order) return false
    if (this.started.has(event.gigId)) {
      this.tally.left++
      return false
    }
    const legs = gig.legs.map((leg) => order.legs[leg]).filter((leg) => leg !== undefined)
    if (event.pickupAt + driveMinutes(map, legs) <= order.deadline) {
      this.tally.onTime++
      return false
    }
    const earliest = now + p.lateLeadHours * HOUR
    if (earliest > order.lastPickupAt || earliest + p.lateGainHours * HOUR > event.pickupAt) {
      this.tally.noTime++
      return false
    }
    return true
  }

  /** A release the world took: the order's cars go again at the urgent fees. */
  sent(action: Action, result: ActionResult, gigs: ReadonlyMap<string, OurGig>): void {
    if (action.type !== 'release') return
    const gig = gigs.get(action.gigId)
    if (!result.ok) this.tally.refused++
    else if (gig) {
      this.tally.released++
      this.released.add(gig.orderId)
    }
  }

  summary(): string {
    const t = this.tally
    return `late drivers ${t.seen}: released ${t.released} (refused ${t.refused}), kept on time ${t.onTime}, kept no time ${t.noTime}, left ${t.left}; released cars delivered ${t.delivered}, late ${t.deliveredLate}`
  }
}
