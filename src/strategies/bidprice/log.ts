/** What the week's events told the strategy, kept from the events alone so that a restart rebuilds it from the event
 * log: each request and its note's facts, the orders won, how to post each car again, our gigs, and the snow. */
import type { DeskEvent, Order, PostAction, PriceRequest, StopRef } from '../../../vendor/spread-typescript/spread.ts'
import {
  FIRST_TRY,
  NO_FACTS,
  type NoteFacts,
  type Retry,
  readNote,
  retryAfter,
  type Setback,
  type Snowfall,
} from '../../ops/index.ts'

/** A gig of ours: the order and the cars it carries. */
export type OurGig = { orderId: string; legs: number[] }

export class WeekLog {
  readonly requests = new Map<string, PriceRequest>()
  readonly facts = new Map<string, NoteFacts>()
  /** The orders won and not cancelled, as their latest event and deliveries left them. */
  readonly orders = new Map<string, Order>()
  /** `order/leg` -> what the car's setbacks taught: one `Retry` for each leg. */
  readonly retries = new Map<string, Retry>()
  /** Gig id -> what it carries, for every gig of ours the world accepted. */
  readonly gigs = new Map<string, OurGig>()
  /** `order/leg` of every car posted at least once: drivers have seen it. */
  readonly posted = new Set<string>()
  readonly forecasts: Snowfall[] = []

  observe(event: DeskEvent): void {
    switch (event.kind) {
      case 'price_request':
        this.requests.set(event.request.id, event.request)
        this.facts.set(event.request.id, readNote(event.request.note, event.request.arrivedAt))
        break
      case 'order_won':
      case 'order_changed':
        this.orders.set(event.order.id, { ...event.order, deliveredAt: [...event.order.deliveredAt] })
        break
      case 'order_cancelled':
        this.orders.delete(event.orderId)
        break
      case 'delivered': {
        const order = this.orders.get(event.orderId)
        if (order) order.deliveredAt[event.leg] = event.at
        break
      }
      case 'visit_failed':
        this.setBack(event.orderId, event.leg, event.reason, event.at)
        break
      case 'gig_expired': {
        const gig = this.gigs.get(event.gigId)
        for (const leg of gig?.legs ?? []) this.setBack(gig?.orderId ?? '', leg, 'expired', event.at)
        break
      }
      case 'forecast':
        this.forecasts.push(event)
        break
    }
  }

  /** Remembers a post that the world accepted, and returns the gig with whether drivers had seen its cars before. */
  post(gigId: string, action: PostAction): (OurGig & { seen: boolean }) | null {
    const orderId = action.stops[0]?.orderId
    if (orderId === undefined) return null
    const legs = legsOf(action.stops, orderId)
    const seen = this.seen(orderId, legs)
    for (const leg of legs) this.posted.add(key(orderId, leg))
    this.gigs.set(gigId, { orderId, legs })
    return { orderId, legs, seen }
  }

  /** Whether any of the cars has been posted before. */
  seen(orderId: string, legs: readonly number[]): boolean {
    return legs.some((leg) => this.posted.has(key(orderId, leg)))
  }

  /** What the setbacks of the cars taught, together: a gig with several cars waits for the latest and takes every
   * condition. */
  retryOf(orderId: string, legs: readonly number[]): Retry {
    return legs.reduce((sum: Retry, leg) => {
      const retry = this.retries.get(key(orderId, leg)) ?? FIRST_TRY
      return {
        pickupFrom: Math.max(sum.pickupFrom, retry.pickupFrom),
        manualLicence: sum.manualLicence || retry.manualLicence,
        plates: sum.plates || retry.plates,
        late: sum.late || retry.late,
      }
    }, FIRST_TRY)
  }

  factsOf(orderId: string): NoteFacts {
    return this.facts.get(orderId) ?? NO_FACTS
  }

  private setBack(orderId: string, leg: number, setback: Setback, at: number): void {
    const order = this.orders.get(orderId)
    if (!order) return
    const before = this.retries.get(key(orderId, leg))
    this.retries.set(key(orderId, leg), retryAfter(setback, order, this.requests.get(orderId), leg, at, before))
  }
}

/** The cars of the order that a gig's stops carry. */
export const legsOf = (stops: readonly StopRef[], orderId: string): number[] =>
  stops.filter((stop) => stop.orderId === orderId && stop.kind === 'pickup').map((stop) => stop.leg)

const key = (orderId: string, leg: number): string => `${orderId}/${leg}`
