/** bidprice: the design of src/BRIEF.md on the harness. One number joins the two sides of the desk, the expected cost
 * `c` of moving a car, from the fee function that also gives the gig's schedule (bid-price control):
 * - a quote prices each option we can serve at the price that maximises (p − c) × W(p), or declines;
 * - a gig takes its stops and audience from the order handling, and its schedule from the same fee function;
 * - every event, and every action the desk sent, teaches the win model, the booking hazard, the fee extras, lambda
 *   and mu. All state is a function of `observe` and `sent`, so a rebuild from the event log and the journal of sent
 *   actions holds the same quotes, pending answers and fee state.
 * README.md next to this file has the data flow and the params. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  FeeStep,
  Order,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import { type FeeEvent, type FeeParams, type FeeState, learn, newFeeState, planFees } from '../../models/fees/index.ts'
import {
  bestQuote,
  createQuoteState,
  dealerWeight,
  driversNear,
  type Option,
  observe as observeQuotes,
  type QuoteParams,
  type QuoteState,
  recordQuote,
} from '../../models/quote/index.ts'
import { type Context, canServe, type GigShape, gigShape } from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import { higher, orderFeeGig, requestFeeGig, tightening, urgentRamp } from './fees.ts'
import { legsOf, WeekLog } from './log.ts'
import { type BidPriceParams, DEFAULTS, feeParamsOf, quoteParamsOf } from './params.ts'

/** A quote at this many times the list price or more is a decline. */
const DECLINED = 5

class BidPrice extends Strategy<BidPriceParams> {
  readonly quoteParams: QuoteParams
  readonly feeParams: FeeParams
  readonly quotes: QuoteState
  readonly fees: FeeState
  readonly log = new WeekLog()
  readonly tally = { requests: 0, quoted: 0, won: 0, booked: 0, paidOverTypical: 0 }

  constructor(setup: Setup, params: BidPriceParams) {
    super(setup, params)
    this.quoteParams = quoteParamsOf(params)
    this.feeParams = feeParamsOf(params, setup.level)
    this.quotes = createQuoteState(driversNear(setup.roster, setup.map))
    this.fees = newFeeState(this.feeParams)
  }

  observe(event: DeskEvent): void {
    this.log.observe(event)
    observeQuotes(this.quotes, event, this.quoteParams)
    learn(this.fees, event, this.feeParams)
    this.count(event)
  }

  /** What the desk sent for us, as sent, and the world's answer: the quotes the quote learner waits on, and our gigs
   * for the fee learner. */
  sent(action: Action, result: ActionResult, books: Books): void {
    if (!result.ok) return
    if (action.type === 'quote') return this.quoted(action.requestId, action.prices)
    const event = this.feeEventOf(action, result.id, books.now)
    if (event) learn(this.fees, event, this.feeParams)
  }

  /** Design 1: each option we can serve at the price that maximises (p − c) × W(p); a decline when none pays. */
  quote(request: PriceRequest, books: Books): Prices | null {
    const decision = bestQuote(request, this.costs(request, books.now), this.quotes, this.quoteParams, books.now)
    return decision.decline ? null : decision.prices
  }

  /** Designs 2 to 4: the cost `c` of each option we can serve on time, the expected fee and lateness times lambda.
   * Up to level 3 every quote wins the first option, so only that one counts. */
  costs(request: PriceRequest, now: number): Partial<Record<Option, number>> {
    const context = this.context()
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const late = this.lateWeight(request.dealerId)
    return Object.fromEntries(
      options
        .filter((option) => canServe(request, option, now, context).ok)
        .map((option) => [option.kind, this.plan(requestFeeGig(request, option, late, this.setup), now).costCents]),
    )
  }

  /** The stops and audience from the order handling, each with its schedule from the fee function. An urgent
   * reprice keeps the gig as it is. */
  gig(need: GigNeed, books: Books): GigPlan[] {
    const { order, legs, previous } = need
    const shapes: GigShape[] =
      need.why === 'urgent' && previous
        ? [previous]
        : gigShape(order, legs, this.log.factsOf(order.id), this.log.retryOf(order.id, legs), books.now, this.context())
    return shapes.map(({ stops, audience }) => ({
      stops,
      audience,
      schedule: this.schedule(order, stops, audience.experienced, books),
    }))
  }

  /** The fee function's schedule for the cars of `stops`; from the order's deadline warning on, at least the ramp. */
  schedule(order: Order, stops: GigPlan['stops'], experienced: boolean, books: Books): FeeStep[] {
    const gig = this.orderGig(order, legsOf(stops, order.id), experienced, books.now)
    if (!gig) throw new Error(`no request for order ${order.id}`) // the harness posts the starter's gig
    const { schedule } = this.plan(gig, books.now)
    if (!books.urgent.has(order.id)) return schedule
    return higher(schedule, urgentRamp(books.now, gig.typicalCents, this.params), this.setup.level)
  }

  summary(): string {
    const { requests, quoted, won, booked, paidOverTypical } = this.tally
    const level = Math.exp(this.quotes.belief.world?.[0] ?? Math.log(this.quoteParams.startLevel))
    const regions = Object.entries(this.fees.lambda).filter(([key]) => !key.includes('/'))
    const lambda = regions.reduce((sum, [, value]) => sum + value, 0) / Math.max(1, regions.length)
    const share = (part: number, whole: number) => `${((100 * part) / Math.max(1, whole)).toFixed(0)}%`
    return [
      `bidprice: level ${level.toFixed(3)}, lambda ${lambda.toFixed(2)}, mu ${this.fees.mu.toFixed(2)}`,
      `quoted ${share(quoted, requests)} of ${requests} requests, won ${share(won, quoted)} of those`,
      `fees paid ${(paidOverTypical / Math.max(1, booked)).toFixed(2)} × typical`,
    ].join(', ')
  }

  private plan(gig: Parameters<typeof planFees>[0], now: number) {
    return planFees(gig, now, this.fees, this.feeParams)
  }

  private context(): Context {
    const { map, level } = this.setup
    return { map, level, forecasts: this.log.forecasts, tightening: tightening(this.fees, this.feeParams) }
  }

  /** A late order halves the dealer's trust, so lateness weighs more for a dealer who sends more of the requests:
   * 1 + `lateTrust` × its share, over the same for an average dealer. */
  private lateWeight(dealer: string): number {
    const k = this.params.lateTrust
    return (1 + k * dealerWeight(this.quotes, dealer, this.quoteParams)) / (1 + k / this.quoteParams.dealers)
  }

  /** The fee models' view of some cars of an order posted at `at`, from the log alone, so a post and its replay
   * give the same gig. Null without the order's request. */
  private orderGig(order: Order, legs: number[], experienced: boolean, at: number) {
    const request = this.log.requests.get(order.id)
    if (!request) return null
    const seen = this.log.seen(order.id, legs)
    return orderFeeGig(order, request, legs, experienced, at, seen, this.lateWeight(order.dealerId), this.setup)
  }

  /** A quote sent: the quote learner waits for its answer. A decline teaches nothing, and is not counted. */
  private quoted(requestId: string, prices: Prices): void {
    const request = this.log.requests.get(requestId)
    if (!request) return
    recordQuote(this.quotes, request, prices, this.quoteParams)
    const real = request.options.some((o) => (prices[o.kind] ?? Infinity) < DECLINED * o.listPriceCents)
    if (real) this.tally.quoted++
  }

  /** The fee learner's event for a gig action of ours, with the `FeeGig` that planned it. */
  private feeEventOf(action: Action, gigId: string, at: number): FeeEvent | null {
    if (action.type === 'reprice') return { kind: 'gig_repriced', at, gigId: action.gigId, schedule: action.schedule }
    if (action.type === 'withdraw') return { kind: 'gig_withdrawn', at, gigId: action.gigId }
    if (action.type !== 'post') return null
    const order = this.log.orders.get(action.stops[0]?.orderId ?? '')
    if (!order) return null
    const legs = legsOf(action.stops, order.id)
    const gig = this.orderGig(order, legs, action.audience.experienced, at)
    this.log.post(gigId, order.id, legs)
    if (!gig) return null
    return { kind: 'gig_posted', at, gigId, orderIds: [order.id], gig, schedule: action.schedule }
  }

  private count(event: DeskEvent): void {
    if (event.kind === 'price_request') this.tally.requests++
    else if (event.kind === 'order_won') this.tally.won++
    else if (event.kind === 'gig_booked') {
      const gig = this.log.gigs.get(event.gigId)
      const typical = gig && this.log.requests.get(gig.orderId)?.referenceFeeCents
      const order = gig && this.log.orders.get(gig.orderId)
      if (!gig || !typical || !order) return
      this.tally.booked++
      this.tally.paidOverTypical += event.feeCents / ((typical * gig.legs.length) / order.legs.length)
    }
  }
}

export const bidprice: StrategyKind<BidPriceParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new BidPrice(setup, params),
}
