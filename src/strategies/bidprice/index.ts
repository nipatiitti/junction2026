/** bidprice: the design of src/BRIEF.md on the harness. One number joins the two sides of the desk, the expected cost
 * `c` of moving a car, from the fee function that also gives the gig's schedule (bid-price control):
 * - a quote prices each option we can serve at the price that maximises (p − c) × W(p), or declines;
 * - a gig takes its stops and audience from the order handling, and its schedule from the same fee function;
 * - every event teaches the win model, the booking hazard, the fee extras, lambda and mu.
 * README.md next to this file has the data flow and the params. */
import type { Action, DeskEvent, FeeStep, Order, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type FeeEvent, type FeeParams, type FeeState, learn, newFeeState, planFees } from '../../models/fees/index.ts'
import {
  bestQuote,
  createQuoteState,
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

class BidPrice extends Strategy<BidPriceParams> {
  readonly quoteParams: QuoteParams
  readonly feeParams: FeeParams
  readonly quotes: QuoteState
  readonly fees: FeeState
  readonly log = new WeekLog()
  /** The answer to each request, decided when it arrives, so a strategy rebuilt from the event log holds the same
   * quotes and learns the same losses. Null declines. */
  readonly answers = new Map<string, Prices | null>()
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
    if (event.kind === 'price_request') this.answers.set(event.request.id, this.decide(event.request, event.at))
  }

  /** Our own gigs, as the world accepted them, for the fee learner. */
  accepted(action: Action, id: string, at: number): void {
    const event = this.feeEventOf(action, id, at)
    if (event) learn(this.fees, event, this.feeParams)
  }

  quote(request: PriceRequest): Prices | null {
    return this.answers.get(request.id) ?? null
  }

  /** Design 1: each option we can serve at the price that maximises (p − c) × W(p); a decline when none pays. */
  decide(request: PriceRequest, now: number): Prices | null {
    const decision = bestQuote(request, this.costs(request, now), this.quotes, this.quoteParams, now)
    if (decision.decline) return null
    recordQuote(this.quotes, request, decision.prices, this.quoteParams)
    this.tally.quoted++
    return decision.prices
  }

  /** Designs 2 to 4: the cost `c` of each option we can serve on time, the expected fee and lateness times lambda.
   * Up to level 3 every quote wins the first option, so only that one counts. */
  costs(request: PriceRequest, now: number): Partial<Record<Option, number>> {
    const context = this.context()
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    return Object.fromEntries(
      options
        .filter((option) => canServe(request, option, now, context).ok)
        .map((option) => [option.kind, this.plan(requestFeeGig(request, option, this.setup), now).costCents]),
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
    const request = this.log.requests.get(order.id)
    if (!request) throw new Error(`no request for order ${order.id}`) // the harness posts the starter's gig
    const legs = legsOf(stops, order.id)
    const seen = this.log.seen(order.id, legs)
    const gig = orderFeeGig(order, request, legs, experienced, books.now, seen, this.setup)
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

  /** The fee learner's event for an action of ours, with the same `FeeGig` that planned it. */
  private feeEventOf(action: Action, gigId: string, at: number): FeeEvent | null {
    if (action.type === 'reprice') return { kind: 'gig_repriced', at, gigId, schedule: action.schedule }
    if (action.type === 'withdraw') return { kind: 'gig_withdrawn', at, gigId }
    if (action.type !== 'post') return null
    const gig = this.log.post(gigId, action)
    const order = gig && this.log.orders.get(gig.orderId)
    const request = gig && this.log.requests.get(gig.orderId)
    if (!gig || !order || !request) return null
    const feeGig = orderFeeGig(order, request, gig.legs, action.audience.experienced, at, gig.seen, this.setup)
    return { kind: 'gig_posted', at, gigId, orderIds: [gig.orderId], gig: feeGig, schedule: action.schedule }
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
