/** The harness's desk: the books of the week, the order mechanics that every strategy needs, and the outbox. The
 * strategy decides each quote and each gig; the desk asks it through the guard and sends the answers. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  DeskSnapshot,
  Order,
  PostAction,
  PriceRequest,
  VisitFailedEvent,
  World,
} from '../../vendor/spread-typescript/spread.ts'
import { starterGig } from '../strategies/starter/gig.ts'
import type { Books, GigNeed, Strategy } from '../strategy.ts'
import { type Guard, whole } from './guard.ts'

/** A declined request is quoted at this many times its list price: a quote that loses costs nothing. */
const DECLINE = 10

export class Desk implements Books {
  readonly world: World
  readonly strategy: Strategy
  readonly guard: Guard
  readonly endsAt: number
  now: number
  nextTick: number // when the strategy's tick is due next
  readonly outbox: Action[] = [] // the actions decided since the desk last sent
  readonly requests = new Map<string, PriceRequest>()
  readonly orders = new Map<string, Order>() // the orders won and not cancelled
  readonly legGigs = new Map<string, Map<number, string>>() // order id -> leg -> the gig that carries the leg
  readonly booked = new Set<string>() // the gigs that a driver holds now
  readonly posts = new Map<string, PostAction>() // gig id -> the post that made it
  readonly urgent = new Set<string>() // the orders whose deadline warning has come
  readonly refused = new Map<string, number>() // "post: <reason>" -> how many actions the world refused

  constructor(world: World, strategy: Strategy, guard: Guard, snapshot: DeskSnapshot) {
    this.world = world
    this.strategy = strategy
    this.guard = guard
    this.now = snapshot.now
    this.endsAt = snapshot.endsAt
    this.nextTick = this.tickAfter(snapshot.now)
  }

  /** Rebuilds the books from the world and the strategy from the event log, so a desk that stopped keeps its orders.
   * Then answers what it missed: open requests, orders without a gig, failed visits without a new gig, and the
   * deadline warnings, so the orders that had one keep their urgent fees. */
  async rejoin(snapshot: DeskSnapshot, history: DeskEvent[]): Promise<void> {
    const posted = Map.groupBy(snapshot.gigs, (gig) => gig.stops[0]!.orderId) // order id -> its gigs, oldest first
    for (const gig of snapshot.gigs) if (['booked', 'working', 'done'].includes(gig.status)) this.booked.add(gig.id)
    for (const gig of snapshot.gigs)
      if (['open', 'booked', 'working'].includes(gig.status))
        this.carry({ type: 'post', stops: gig.stops, audience: gig.audience, schedule: gig.schedule }, gig.id)
    for (const event of history) if (event.kind === 'price_request') this.requests.set(event.request.id, event.request)
    for (const event of history) if (event.kind === 'deadline_close') this.urgent.add(event.orderId)
    for (const order of snapshot.orders)
      if (this.requests.has(order.id) && order.status !== 'cancelled') this.orders.set(order.id, order)
    for (const event of history) this.observe(event)
    for (const order of this.orders.values())
      if (order.status === 'waiting' && this.gigsOf(order.id).length === 0)
        await this.post('won', order, undelivered(order))
    for (const event of history) {
      const order = 'orderId' in event ? this.orders.get(event.orderId) : undefined
      if (!order) continue
      if (event.kind === 'visit_failed' && order.deliveredAt[event.leg] === null) {
        const later = (posted.get(order.id) ?? []).filter((gig) => gig.postedAt >= event.at && gig.id !== event.gigId)
        if (!later.some((gig) => gig.stops.some((stop) => stop.leg === event.leg)))
          await this.retry(order.id, event.leg, event.reason)
      }
    }
    for (const request of snapshot.openRequests) this.quote(request)
  }

  async handle(event: DeskEvent): Promise<void> {
    this.observe(event)
    if (event.kind === 'price_request') this.quote(event.request)
    else if (event.kind === 'order_won') await this.win(event.order)
    else if (event.kind === 'order_changed') await this.change(event.order)
    // The world has stopped a cancelled order's car and told each of its gigs what happens.
    else if (event.kind === 'order_cancelled')
      for (const books of [this.orders, this.legGigs]) books.delete(event.orderId)
    else if (event.kind === 'visit_failed') await this.retry(event.orderId, event.leg, event.reason)
    else if (event.kind === 'gig_expired') this.repost(event.gigId)
    // It comes again when a driver drops the car after the first warning.
    else if (event.kind === 'deadline_close') await this.raise(event.orderId)
    else if (event.kind === 'gig_booked') this.booked.add(event.gigId)
    else if (event.kind === 'offer_answered' && event.answer === 'accepted') this.booked.add(event.gigId)
    // After a no-show the gig is open again, as after a drop. A late driver still comes.
    else if (event.kind === 'gig_dropped' || event.kind === 'no_show') this.booked.delete(event.gigId)
    else if (event.kind === 'delivered') this.delivered(event.orderId, event.leg, event.at)
  }

  /** Puts the strategy's periodic actions in the outbox, once `every` minutes have passed since the last time. */
  tick(): void {
    if (this.now < this.nextTick) return
    this.nextTick = this.tickAfter(this.now)
    this.outbox.push(...whole(this.guard.run('tick', () => this.strategy.tick(this)) ?? []))
  }

  /** When the tick is due after `minute`: never for a strategy without one. */
  tickAfter(minute: number): number {
    const every = this.strategy.every
    return every === null ? Infinity : minute + Math.max(1, Math.round(every))
  }

  observe(event: DeskEvent): void {
    this.guard.run('observe', () => this.strategy.observe(event, this))
  }

  /** The strategy's prices, or a decline: far above list, or no quote up to level 3, where every quote wins. */
  quote(request: PriceRequest): void {
    this.requests.set(request.id, request)
    const prices = whole(this.guard.run('quote', () => this.strategy.quote(request, this)))
    if (prices && Object.keys(prices).length > 0) this.outbox.push({ type: 'quote', requestId: request.id, prices })
    else if (this.strategy.setup.level > 3) {
      const first = request.options[0]!
      this.outbox.push({
        type: 'quote',
        requestId: request.id,
        prices: { [first.kind]: first.listPriceCents * DECLINE },
      })
    }
  }

  /** The strategy's gig, or the starter's when the strategy fails. */
  plan(need: GigNeed): PostAction {
    const gig =
      this.guard.run('gig', () => this.strategy.gig(need, this)) ?? starterGig(need, this, this.strategy.setup.level)
    return whole({ type: 'post', ...gig })
  }

  delivered(orderId: string, leg: number, at: number): void {
    this.legGigs.get(orderId)?.delete(leg)
    const order = this.orders.get(orderId)
    if (order) order.deliveredAt[leg] = at
  }

  async win(order: Order): Promise<void> {
    if (!this.requests.has(order.id) || this.orders.has(order.id)) return // rejoin can know it already
    this.orders.set(order.id, order)
    await this.post('won', order, undelivered(order))
  }

  async change(order: Order): Promise<void> {
    if (!this.orders.has(order.id)) return
    this.orders.set(order.id, order)
    if (await this.withdraw(order.id)) await this.post('changed', order, undelivered(order))
  }

  /** Posts a gig again when one of its windows ended before a driver booked it. */
  repost(gigId: string): void {
    const previous = this.posts.get(gigId)
    // A gig already taken off and posted again, after a change of plan, needs nothing.
    if (!previous?.stops.some(({ orderId, leg }) => this.legGigs.get(orderId)?.get(leg) === gigId)) return
    for (const { orderId, leg } of previous.stops) this.legGigs.get(orderId)?.delete(leg)
    const order = this.orders.get(previous.stops[0]!.orderId)
    if (!order) return
    this.outbox.push(this.plan({ why: 'repost', order, legs: legsOf(previous, order.id), previous }))
  }

  /** From the order's deadline warning on, its gigs that no driver holds take the urgent fees. */
  async raise(orderId: string): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.urgent.add(orderId)
    await this.sendPostOf(orderId)
    for (const gigId of this.gigsOf(orderId)) {
      if (this.booked.has(gigId)) continue
      const previous = this.posts.get(gigId)!
      const { schedule } = this.plan({ why: 'urgent', order, legs: legsOf(previous, orderId), previous })
      this.outbox.push({ type: 'reprice', gigId, schedule })
    }
  }

  async retry(orderId: string, leg: number, reason: VisitFailedEvent['reason']): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.legGigs.get(orderId)?.delete(leg) // the world has taken the car out of the failed gig
    await this.post('retry', order, [leg], reason)
  }

  /** Posts one gig for the legs. A trade-in over the 12-hour limit for a gig with two cars goes as one gig per car. */
  async post(why: GigNeed['why'], order: Order, legs: number[], failed?: GigNeed['failed']): Promise<void> {
    this.outbox.push(this.plan({ why, order, legs, failed }))
    if (legs.length === 1) return
    await this.send()
    if (this.gigsOf(order.id).length === 0) for (const leg of legs) await this.post('split', order, [leg], failed)
  }

  /** The gigs that carry the order's undelivered legs: one, or one for each leg of a split trade-in. */
  gigsOf(orderId: string): string[] {
    return [...new Set(this.legGigs.get(orderId)?.values())]
  }

  /** Remembers a gig that the world accepted: the post that made it, and the legs it carries. */
  carry(action: PostAction, gigId: string): void {
    for (const { orderId, leg } of action.stops)
      this.legGigs.set(orderId, (this.legGigs.get(orderId) ?? new Map()).set(leg, gigId))
    this.posts.set(gigId, action)
  }

  /** Takes an order's gigs out of the drivers' app. False, and nothing withdrawn, when a driver holds one of them. */
  async withdraw(orderId: string): Promise<boolean> {
    await this.sendPostOf(orderId)
    const gigs = this.gigsOf(orderId)
    if (gigs.some((gigId) => this.booked.has(gigId))) return false
    this.legGigs.delete(orderId)
    for (const gigId of gigs) this.outbox.push({ type: 'withdraw', gigId })
    return true
  }

  /** A post of the order still in the outbox goes to the world now, so the desk knows its gig. */
  async sendPostOf(orderId: string): Promise<void> {
    if (this.outbox.some((action) => action.type === 'post' && action.stops.some((stop) => stop.orderId === orderId)))
      await this.send()
  }

  /** Sends the outbox now. In practice, the outbox goes with the next advance instead. The client sends batches of
   * at most 50 actions and waits for the tokens that the RateLimit headers name. */
  async send(): Promise<void> {
    const actions = this.outbox.splice(0)
    if (actions.length > 0) this.readResults(actions, await this.world.act(actions))
  }

  /** Books the gigs that the world made and the ones the strategy withdrew; counts the refused actions. */
  readResults(actions: Action[], results: ActionResult[]): void {
    actions.forEach((action, i) => {
      const result = results[i]
      if (!result) return
      if (!result.ok) {
        const reason = `${action.type}: ${result.reason}`
        this.refused.set(reason, (this.refused.get(reason) ?? 0) + 1)
      } else if (action.type === 'post') this.carry(action, result.id)
      else if (action.type === 'withdraw') this.forget(action.gigId)
    })
  }

  /** Drops a withdrawn gig from the legs it carried. */
  forget(gigId: string): void {
    for (const legs of this.legGigs.values()) for (const [leg, id] of legs) if (id === gigId) legs.delete(leg)
  }
}

const undelivered = (order: Order): number[] =>
  order.legs.map((_, leg) => leg).filter((leg) => order.deliveredAt[leg] === null)

/** The legs of the order that a post carries. */
const legsOf = (action: PostAction, orderId: string): number[] =>
  action.stops.filter((stop) => stop.orderId === orderId && stop.kind === 'pickup').map((stop) => stop.leg)
