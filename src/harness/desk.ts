/** The harness's desk: the books of the week, the order mechanics that every strategy needs, and the outbox. The
 * strategy decides each quote and each gig; the desk asks it through the guard and sends the answers. */
import {
  type Action,
  type ActionResult,
  type DeskEvent,
  type DeskSnapshot,
  type Order,
  type OrderCancelledEvent,
  type PostAction,
  type PriceRequest,
  SpreadError,
  Unreachable,
  type VisitFailedEvent,
  type World,
} from '../../vendor/spread-typescript/spread.ts'
import { starterGig } from '../strategies/starter/gig.ts'
import type { Books, GigNeed, GigPlan, Strategy } from '../strategy.ts'
import { HOUR } from '../time.ts'
import type { Guard } from './guard.ts'
import { Journal, type JournalLine } from './journal.ts'

/** A declined request is quoted at this many times its list price: a quote that loses costs nothing. */
const DECLINE = 10
/** Live, the most actions besides quotes in one request: a final refills 20 action tokens a second, and a quote
 * should never wait for tokens that a burst of reprices took. */
const OTHERS_PER_SEND = 10

export class Desk implements Books {
  readonly world: World
  readonly strategy: Strategy
  readonly guard: Guard
  readonly journal: Journal
  readonly endsAt: number
  now: number
  seen = -1 // the last event handled
  nextTick: number // when the strategy's tick is due next
  /** How the desk sends: in practice the whole outbox in order, as the advance would carry it; live, the quotes
   * first. The live loop sets it. */
  live = false
  readonly outbox: Action[] = [] // the actions decided and not sent yet
  inFlight: Action[] = [] // the actions of the request that waits for its answer
  flight: Promise<void> | undefined // that request; one at a time
  failure: unknown // why the last request failed: the loop throws it and the week is rebuilt
  readonly requests = new Map<string, PriceRequest>()
  readonly orders = new Map<string, Order>() // the orders won and not cancelled
  readonly legGigs = new Map<string, Map<number, string>>() // order id -> leg -> the gig that carries the leg
  readonly booked = new Set<string>() // the gigs that a driver holds now
  readonly posts = new Map<string, PostAction>() // gig id -> the post that made it
  readonly urgent = new Set<string>() // the orders whose deadline warning has come
  readonly refused = new Map<string, number>() // "post: <reason>" -> how many actions the world refused
  readonly swept = new Map<string, number>() // "<order id> <leg>" -> when the sweep last posted the leg
  readonly held = new Map<string, number>() // order id -> when the strategy wants its first post (`holdUntil`)

  constructor(world: World, strategy: Strategy, guard: Guard, snapshot: DeskSnapshot, journal = new Journal(world.id)) {
    this.world = world
    this.strategy = strategy
    this.guard = guard
    this.journal = journal
    this.now = snapshot.now
    this.endsAt = snapshot.endsAt
    this.nextTick = this.tickAfter(snapshot.now)
  }

  /** Rebuilds the books from the world, and the strategy from the event log and the journal, so a desk that stopped
   * keeps its orders. Then answers what it missed: failed visits without a new gig, open requests, and the legs left
   * without a gig. */
  async rejoin(snapshot: DeskSnapshot, history: DeskEvent[]): Promise<void> {
    for (const gig of snapshot.gigs) {
      const post: PostAction = { type: 'post', stops: gig.stops, audience: gig.audience, schedule: gig.schedule }
      this.posts.set(gig.id, post)
      if (['booked', 'working', 'done'].includes(gig.status)) this.booked.add(gig.id)
      if (['open', 'booked', 'working'].includes(gig.status)) this.carry(post, gig.id)
    }
    for (const event of history) if (event.kind === 'price_request') this.requests.set(event.request.id, event.request)
    for (const event of history) if (event.kind === 'deadline_close') this.urgent.add(event.orderId)
    for (const order of snapshot.orders)
      if (this.requests.has(order.id) && order.status !== 'cancelled') this.orders.set(order.id, order)
    this.replay(history, this.journal.read())
    this.now = snapshot.now
    this.seen = history.at(-1)?.seq ?? -1
    // The failed visits first, so their legs go with the retry's plates or licence, and the sweep leaves them.
    for (const event of history) {
      const order = event.kind === 'visit_failed' ? this.orders.get(event.orderId) : undefined
      if (event.kind !== 'visit_failed' || order?.deliveredAt[event.leg] !== null) continue
      const later = snapshot.gigs.some(
        (gig) => gig.postedAt >= event.at && gig.id !== event.gigId && carries(gig, event.orderId, event.leg),
      )
      if (!later) await this.retry(event.orderId, event.leg, event.reason)
    }
    for (const request of snapshot.openRequests) this.quote(request)
    await this.sweep()
  }

  /** Feeds the strategy the week so far in the order it lived it: each event through `observe` and each journal
   * line through `sent`, with the clock at its minute. */
  replay(history: DeskEvent[], journal: JournalLine[]): void {
    let next = 0
    const sentBefore = (seq: number) => {
      for (; next < journal.length && journal[next]!.seq < seq; next++) {
        const { at, action, result } = journal[next]!
        this.now = at
        this.guard.run('sent', () => this.strategy.sent(action, result, this))
      }
    }
    for (const event of history) {
      sentBefore(event.seq)
      this.now = event.at
      this.observe(event)
    }
    sentBefore(Infinity)
  }

  async handle(event: DeskEvent): Promise<void> {
    // After a server restart an advance can repeat events, and a rebuild has replayed the ones before it.
    if (event.seq <= this.seen) return
    this.seen = event.seq
    this.now = Math.max(this.now, event.at)
    this.observe(event)
    if (event.kind === 'price_request') this.quote(event.request)
    else if (event.kind === 'order_won') await this.win(event.order)
    else if (event.kind === 'order_changed') await this.change(event.order)
    else if (event.kind === 'order_cancelled') this.cancel(event)
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

  /** Puts the strategy's periodic actions in the outbox once `every` minutes have passed since the last time, and
   * sweeps. */
  async tick(): Promise<void> {
    if (this.now < this.nextTick) return
    this.nextTick = this.tickAfter(this.now)
    const actions = this.guard.run('tick', () => this.strategy.tick(this))
    this.outbox.push(...this.guard.admit('tick', Array.isArray(actions) ? actions : []))
    await this.sweep()
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
    const prices = this.guard.run('quote', () => this.strategy.quote(request, this))
    const answer =
      prices && Object.keys(prices).length > 0 ? [{ type: 'quote' as const, requestId: request.id, prices }] : []
    const [action] = this.guard.admit('quote', answer, request)
    if (action) this.outbox.push(action)
    else if (this.strategy.setup.level > 3) {
      const first = request.options[0]!
      this.outbox.push({
        type: 'quote',
        requestId: request.id,
        prices: { [first.kind]: first.listPriceCents * DECLINE },
      })
    }
  }

  /** The strategy's gigs for the need, and the starter's for every leg that they leave out: an empty, invalid or
   * failed answer gets the starter's gig for all the legs. */
  plan(need: GigNeed): PostAction[] {
    const answer = this.guard.run('gig', () => [this.strategy.gig(need, this)].flat())
    if (answer?.length === 0) this.guard.fault('gig empty')
    const plans = this.guard.admit('gig', (answer ?? []).map(postOf))
    const left = need.legs.filter((leg) => !plans.some((plan) => carries(plan, need.order.id, leg)))
    if (left.length === 0) return plans
    const safe = this.guard.run('gig', () => starterGig({ ...need, legs: left }, this, this.strategy.setup.level))
    return [...plans, ...this.guard.admit('gig', safe ? [postOf(safe)] : [])]
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

  /** The world has stopped a cancelled order's car and told each of its gigs what happens. A withdrawn gig that also
   * carried another order's cars leaves them to the sweep. */
  cancel(event: OrderCancelledEvent): void {
    for (const books of [this.orders, this.legGigs, this.held]) books.delete(event.orderId)
    for (const gig of event.gigs) if (gig.outcome === 'withdrawn') this.forget(gig.gigId)
  }

  /** Posts a gig again when one of its windows ended before a driver booked it. The cars of other orders in it are
   * left to the sweep. */
  repost(gigId: string): void {
    const previous = this.posts.get(gigId)
    // A gig already taken off and posted again, after a change of plan, needs nothing.
    if (!previous?.stops.some(({ orderId, leg }) => this.legGigs.get(orderId)?.get(leg) === gigId)) return
    for (const { orderId, leg } of previous.stops) this.legGigs.get(orderId)?.delete(leg)
    const order = this.orders.get(previous.stops[0]!.orderId)
    if (!order) return
    this.outbox.push(...this.plan({ why: 'repost', order, legs: legsOf(previous, order.id), previous }))
  }

  /** From the order's deadline warning on, its gigs that no driver holds take the urgent fees. */
  async raise(orderId: string): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.urgent.add(orderId)
    await this.sendPostOf(orderId)
    for (const gigId of this.gigsOf(orderId)) {
      const previous = this.posts.get(gigId)
      if (this.booked.has(gigId) || !previous) continue
      const [plan] = this.plan({ why: 'urgent', order, legs: legsOf(previous, orderId), previous })
      if (plan) this.outbox.push({ type: 'reprice', gigId, schedule: plan.schedule })
    }
  }

  async retry(orderId: string, leg: number, reason: VisitFailedEvent['reason']): Promise<void> {
    const order = this.orders.get(orderId)
    if (!order) return
    this.legGigs.get(orderId)?.delete(leg) // the world has taken the car out of the failed gig
    await this.post('retry', order, [leg], reason)
  }

  /** Posts the strategy's gigs for the legs. A leg that none of them got, as a trade-in over the 12-hour limit for a
   * gig with two cars, goes again as a gig of its own. */
  async post(why: GigNeed['why'], order: Order, legs: number[], failed?: GigNeed['failed']): Promise<void> {
    if ((why === 'won' || why === 'lost') && this.hold(order)) return
    const plans = this.plan({ why, order, legs, failed })
    this.outbox.push(...plans)
    if (legs.length === 1) return
    await this.answered(plans)
    for (const leg of legs.filter((leg) => !this.legGigs.get(order.id)?.has(leg) && !this.waiting(order.id, leg)))
      await this.post('split', order, [leg], failed)
  }

  /** Posts every undelivered leg of a live order that no gig carries and no post waits for: a refused post, a change
   * or a cancellation of another order in a combined gig, or a gig of several orders that expired can leave one. A
   * leg goes again at most once an hour, so a post that the world keeps refusing does not eat the action tokens. */
  async sweep(): Promise<void> {
    for (const order of [...this.orders.values()]) {
      if ((this.held.get(order.id) ?? -Infinity) > this.now) continue // its first post waits for its minute
      const due = (leg: number) => !(this.now < (this.swept.get(`${order.id} ${leg}`) ?? -Infinity) + HOUR)
      const legs = undelivered(order).filter(
        (leg) => !this.legGigs.get(order.id)?.has(leg) && !this.waiting(order.id, leg) && due(leg),
      )
      for (const leg of legs) this.swept.set(`${order.id} ${leg}`, this.now)
      if (legs.length > 0) await this.post(this.held.delete(order.id) ? 'won' : 'lost', order, legs)
    }
  }

  /** Whether the strategy holds the order's first post to a later minute: the sweep posts it then. */
  hold(order: Order): boolean {
    const at = this.guard.run('gig', () => this.strategy.holdUntil(order, this.now)) ?? this.now
    if (at > this.now) this.held.set(order.id, at)
    return at > this.now
  }

  /** The gigs that carry the order's undelivered legs: one, or one for each leg of a split trade-in. */
  gigsOf(orderId: string): string[] {
    return [...new Set(this.legGigs.get(orderId)?.values())]
  }

  /** Whether a post of the leg waits in the outbox or for the world's answer. */
  waiting(orderId: string, leg: number): boolean {
    return [...this.outbox, ...this.inFlight].some((action) => action.type === 'post' && carries(action, orderId, leg))
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

  /** A post of the order still waiting goes to the world now, so the desk knows its gig. */
  async sendPostOf(orderId: string): Promise<void> {
    const posts = [...this.outbox, ...this.inFlight].filter(
      (action) => action.type === 'post' && action.stops.some((stop) => stop.orderId === orderId),
    )
    if (posts.length > 0) await this.answered(posts)
  }

  /** Sends the outbox and waits until the world has answered all of it. In practice the outbox goes with the next
   * advance instead. */
  async send(): Promise<void> {
    await this.answered(this.outbox)
  }

  /** Sends the outbox, one request at a time, until the world has answered these actions. */
  async answered(actions: readonly Action[]): Promise<void> {
    const waiting = [...actions]
    this.pump()
    while (waiting.some((action) => this.outbox.includes(action) || this.inFlight.includes(action))) {
      await this.flight
      this.pump()
    }
  }

  /** Starts the next request unless one is in flight; the next one goes when it returns, so the outbox collects
   * meanwhile and a burst of requests goes out in one. Throws the error of a request that failed. */
  pump(): void {
    if (this.failure !== undefined) throw this.failure
    if (this.flight || this.outbox.length === 0) return
    const batch = this.take()
    this.inFlight = batch
    this.flight = this.act(batch)
      .then((results) => this.readResults(batch, results))
      .catch((error: unknown) => {
        this.failure ??= error
      })
      .finally(() => {
        this.inFlight = []
        this.flight = undefined
        if (this.failure === undefined) this.pump()
      })
  }

  /** Waits until no request is in flight, whatever its end. */
  async settle(): Promise<void> {
    while (this.flight) await this.flight
  }

  /** Takes the next request's actions out of the outbox. In practice, all of them in order. Live, the quotes first,
   * then posts and withdrawals, then the rest, with at most OTHERS_PER_SEND actions besides the quotes. */
  take(): Action[] {
    const rank = (action: Action) =>
      !this.live ? 0 : action.type === 'quote' ? 0 : action.type === 'post' || action.type === 'withdraw' ? 1 : 2
    const ranked = this.outbox
      .map((action, i) => ({ action, i }))
      .sort((a, b) => rank(a.action) - rank(b.action) || a.i - b.i)
    let others = 0
    const batch = ranked
      .filter(({ action }) => !this.live || rank(action) === 0 || ++others <= OTHERS_PER_SEND)
      .map(({ action }) => action)
    const taken = new Set(batch)
    const rest = this.outbox.filter((action) => !taken.has(action))
    this.outbox.splice(0, this.outbox.length, ...rest)
    return batch
  }

  /** The world's answers to the actions. A batch that the server refuses as a whole goes again in halves, so that
   * only the bad action is refused. An unreachable server is not the batch's fault, and throws. */
  async act(actions: Action[]): Promise<ActionResult[]> {
    try {
      return await this.world.act(actions)
    } catch (error) {
      if (!(error instanceof SpreadError) || error instanceof Unreachable || ![0, 400].includes(error.status))
        throw error
      if (actions.length === 1) return [{ ok: false, reason: error.message }]
      const half = Math.ceil(actions.length / 2)
      return [...(await this.act(actions.slice(0, half))), ...(await this.act(actions.slice(half)))]
    }
  }

  /** Books the gigs that the world made and the ones the strategy withdrew, counts the refused actions, writes each
   * to the journal and tells the strategy. A refused post of one car that had windows of its own goes again without
   * them: the world cuts a window to the site's hours, and the clock can be minutes old. */
  readResults(actions: Action[], results: ActionResult[]): void {
    actions.forEach((action, i) => {
      const result: ActionResult = results[i] ?? { ok: false, reason: 'no answer' }
      if (!result.ok) {
        const reason = `${action.type}: ${result.reason.replace(/\b[A-Za-z]?\d[\w:]*/g, '#')}` // without ids and times, so like reasons count together
        this.refused.set(reason, (this.refused.get(reason) ?? 0) + 1)
        if (action.type === 'post' && cars(action) === 1 && action.stops.some((stop) => stop.window))
          this.outbox.push({ ...action, stops: action.stops.map(({ window: _, ...stop }) => stop) })
      } else if (action.type === 'post') this.carry(action, result.id)
      else if (action.type === 'withdraw') this.forget(action.gigId)
      this.journal.write({ seq: this.seen, at: this.now, action, result })
      this.guard.run('sent', () => this.strategy.sent(action, result, this))
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

/** Whether a gig or a post picks up the order's leg. */
const carries = (gig: Pick<PostAction, 'stops'>, orderId: string, leg: number): boolean =>
  gig.stops.some((stop) => stop.orderId === orderId && stop.leg === leg && stop.kind === 'pickup')

/** The post of a plan, with its fields only. */
const postOf = (plan: GigPlan): PostAction => ({
  type: 'post',
  stops: plan?.stops,
  audience: plan?.audience,
  schedule: plan?.schedule,
})

/** The cars that a post carries. */
const cars = (action: PostAction): number => action.stops.filter((stop) => stop.kind === 'pickup').length
