/** Direct offers to the drivers who looked at a gig and did not take it. A driver who sees a fee in the app may
 * hold out for a rise: two bookers in three had seen the gig before at a lower fee. An offer is for 10 minutes at one
 * fee, so there is nothing to wait for, and a driver takes it when the fee pays for the gig (RULES.md, "Direct
 * offers"). So each viewer who lives near the gig's first pickup or last delivery gets the fee the app shows, × `at`,
 * as an offer: at most three open offers a gig and three offers a driver a day, as the rules allow. */
import type { Action, WorldMap } from '../../../vendor/spread-typescript/spread.ts'
import { DAY, minutes } from '../../ops/index.ts'
import type { Books } from '../../strategy.ts'

/** A viewer counts when they live within this many road minutes of the first pickup or the last delivery. */
const NEAR = 90
const PER_DRIVER = 3
const PER_GIG = 3
const OPEN_FOR = 10

export class Offers {
  private readonly homes = new Map<string, string>()
  /** Gig id -> the drivers who viewed it and wait for an offer. */
  private readonly viewers = new Map<string, string[]>()
  /** "<gig id> <driver id>" of every offer sent; driver id -> the days of its offers; gig id -> when its offers end. */
  private readonly offered = new Set<string>()
  private readonly days = new Map<string, number[]>()
  private readonly open = new Map<string, number[]>()
  readonly tally = { sent: 0, accepted: 0 }
  private readonly map: WorldMap

  constructor(map: WorldMap, roster: readonly { id: string; homePlaceId: string }[]) {
    this.map = map
    for (const driver of roster) this.homes.set(driver.id, driver.homePlaceId)
  }

  viewed(gigId: string, driverId: string): void {
    if (this.offered.has(`${gigId} ${driverId}`)) return
    const waiting = this.viewers.get(gigId) ?? []
    if (!waiting.includes(driverId)) this.viewers.set(gigId, [...waiting, driverId])
  }

  answered(accepted: boolean): void {
    if (accepted) this.tally.accepted++
  }

  /** The offers to send now: for each open gig, its waiting viewers who live near it, at `fee(gigId)` cents. */
  actions(books: Books, fee: (gigId: string) => number): Action[] {
    const now = books.now
    const day = Math.floor(now / DAY)
    const actions: Action[] = []
    if (now % DAY < 7 * 60 || now % DAY >= 22 * 60) return actions // no driver reads an offer at night
    for (const [gigId, waiting] of this.viewers) {
      this.viewers.delete(gigId)
      const post = books.posts.get(gigId)
      const first = post?.stops[0]
      const last = post?.stops.at(-1)
      const from = first && books.orders.get(first.orderId)?.legs[first.leg]?.pickup.placeId
      const to = last && books.orders.get(last.orderId)?.legs[last.leg]?.delivery.placeId
      if (!post || !from || !to || books.booked.has(gigId) || !books.gigsOf(first.orderId).includes(gigId)) continue
      const cents = Math.round(fee(gigId))
      const live = (this.open.get(gigId) ?? []).filter((until) => until > now)
      for (const driverId of waiting) {
        if (live.length >= PER_GIG || !(cents > 0)) break
        const home = this.homes.get(driverId)
        const today = (this.days.get(driverId) ?? []).filter((d) => d === day)
        if (!home || today.length >= PER_DRIVER) continue
        if (minutes(this.map, home, from) > NEAR && minutes(this.map, to, home) > NEAR) continue
        this.offered.add(`${gigId} ${driverId}`)
        this.days.set(driverId, [...today, day])
        live.push(now + OPEN_FOR)
        this.tally.sent++
        actions.push({ type: 'offer', gigId, driverId, feeCents: cents })
      }
      this.open.set(gigId, live)
    }
    return actions
  }
}
