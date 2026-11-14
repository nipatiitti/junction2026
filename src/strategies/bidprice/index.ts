/** bidprice: the design of src/BRIEF.md on the harness. One number joins the two sides of the desk, the expected cost
 * `c` of moving a car: what an order of its kind really costs, fees after every raise and drop plus late refunds,
 * learned during the week (bid-price control):
 * - a quote prices each option we can serve at the price that maximises (p − c) × W(p), or declines, so a tight or
 *   dear option is priced up or declined by the profit rule, not by a threshold;
 * - a gig takes its stops and audience from the order handling, and its schedule from the fee function;
 * - every event, and every action the desk sent, teaches the win model, the cost of each kind, the booking hazard,
 *   the fee extras and mu. All state is a function of `observe` and `sent`, so a rebuild from the event log and the
 *   journal of sent actions holds the same quotes, pending answers and costs.
 * README.md next to this file has the data flow and the params. */
import type {
  Action,
  ActionResult,
  DeliveryOption,
  DeskEvent,
  FeeStep,
  Order,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  costOf,
  type FeeEvent,
  type FeeGig,
  type FeeParams,
  type FeeState,
  fewDriversNear,
  learn,
  muOf,
  newFeeState,
  planFees,
} from '../../models/fees/index.ts'
import { feeAt } from '../../models/fees/plan.ts'
import {
  bestQuote,
  createQuoteState,
  dealerWeight,
  driversNear,
  inWar,
  type Option,
  observe as observeQuotes,
  type QuoteParams,
  type QuoteState,
  recordQuote,
} from '../../models/quote/index.ts'
import { appendFileSync } from 'node:fs'
import { type Context, canServe, driveMinutes, type GigShape, gigShape, HOUR } from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import {
  booked,
  type CostLearning,
  type CostPrior,
  type CostState,
  cancelled,
  closed,
  feeRatio,
  kindOf,
  lateRatio,
  moved,
  newCostState,
  picked,
  posted,
  priorOf,
  readCostPrior,
  remember,
  repriced,
  settled,
  unbooked,
} from './cost.ts'
import { climb, higher, orderFeeGig, ramp, tightening, urgentRamp } from './fees.ts'
import { lateRiskOf, newLateRisk } from './late.ts'
import { legsOf, WeekLog } from './log.ts'
import { type BidPriceParams, DEFAULTS, feeParamsOf, quoteParamsOf } from './params.ts'
import { Widen } from './widen.ts'

/** A quote at this many times the list price or more is a decline. */
const DECLINED = 5

export class BidPrice extends Strategy<BidPriceParams> {
  override readonly every = 30
  readonly quoteParams: QuoteParams
  readonly feeParams: FeeParams
  readonly quotes: QuoteState
  readonly fees: FeeState
  readonly costPrior: CostPrior = readCostPrior()
  readonly cost: CostState
  readonly learning: CostLearning
  readonly log = new WeekLog()
  readonly lateRisk: ReturnType<typeof newLateRisk>
  /** The latest minute an event or action has told, for the summary. */
  private now = 0
  readonly tally = { requests: 0, quoted: 0, won: 0, booked: 0, paidOverTypical: 0 }
  /** Why each request got no quote, and how many options each admission rule left out of the quotes. */
  readonly declines: Record<string, number> = {}
  readonly widen = new Widen(this)

  constructor(setup: Setup, params: BidPriceParams) {
    super(setup, params)
    this.quoteParams = quoteParamsOf(params)
    this.feeParams = feeParamsOf(params, setup.level)
    this.quotes = createQuoteState(driversNear(setup.roster, setup.map))
    this.fees = newFeeState(this.feeParams)
    this.cost = newCostState(this.costPrior)
    this.learning = { learn: params.costLearn, pseudoGigs: params.costPseudo }
    this.lateRisk = newLateRisk(setup.roster, setup.map)
  }

  observe(event: DeskEvent): void {
    this.now = Math.max(this.now, event.at)
    this.log.observe(event)
    observeQuotes(this.quotes, event, this.quoteParams)
    learn(this.fees, event, this.feeParams)
    this.learnCost(event)
    this.count(event)
  }

  /** What the desk sent for us, as sent, and the world's answer: the quotes the quote learner waits on, and our gigs
   * for the fee learner. */
  sent(action: Action, result: ActionResult, books: Books): void {
    if (!result.ok) return
    if (action.type === 'quote') this.quoted(action.requestId, action.prices)
    const event = this.feeEventOf(action, result.id, books.now)
    if (event) learn(this.fees, event, this.feeParams)
  }

  /** Design 1: each option we offer at the price that maximises (p − c) × W(p); a decline when none pays. */
  quote(request: PriceRequest, books: Books): Prices | null {
    const decision = this.decide(request, books.now)
    this.audit(request, books.now, decision)
    if (this.params.quoteAll || this.params.allOptions) return this.widen.prices(request, books.now, decision)
    return decision.decline ? null : decision.prices
  }

  /** The decline log: the reason a request got no quote (or `quoted`), and each option an admission rule left out.
   * With `BIDPRICE_DECLINE_LOG` set, one JSON line per request in that file. */
  audit(request: PriceRequest, now: number, decision: ReturnType<BidPrice['decide']>): void {
    const context = this.context()
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const verdicts = options.map((option) => ({ option, ...canServe(request, option, now, context) }))
    const served = verdicts.filter((v) => v.ok)
    const risky = served.filter(
      (v) => this.params.lateRisk && this.riskOf(request, v.option, now) >= this.params.lateRiskMax,
    )
    const offered: string[] = this.offered(request, now).map((o) => o.kind)
    const dropped = (kind: string) => {
      if (!verdicts.find((v) => v.option.kind === kind)?.ok) return 'serve'
      if (risky.some((v) => v.option.kind === kind)) return 'lateRisk'
      return offered.includes(kind) ? null : 'comfort'
    }
    const optionDrops = Object.fromEntries(
      options.flatMap((o) => {
        const why = dropped(o.kind)
        return why ? [[o.kind, why]] : []
      }),
    )
    for (const why of Object.values(optionDrops)) this.bump(`opt-${why}`)
    let reason = 'quoted'
    if (decision.decline) {
      if (served.length === 0) {
        const why = verdicts.map((v) => v.reason)
        reason = why.some((r) => r.includes('h needed'))
          ? 'serve-slack'
          : why.some((r) => r.includes('note'))
            ? 'serve-note'
            : why.some((r) => r.includes('read'))
              ? 'serve-unread'
              : 'serve-deadline'
      } else if (offered.length === 0) reason = 'lateRisk'
      else if (inWar(this.quotes, now, this.quoteParams)) reason = 'war'
      else {
        const loose = bestQuote(
          request,
          this.costs(request, now),
          this.quotes,
          { ...this.quoteParams, minValueCents: -1e18 },
          now,
        )
        reason = loose.decline ? 'underCost' : 'minValue'
      }
    }
    this.bump(reason)
    const file = process.env.BIDPRICE_DECLINE_LOG
    if (file) {
      const costs = this.costs(request, now)
      const line = {
        id: request.id,
        at: now,
        reason,
        optionDrops,
        offered,
        costs,
        value: decision.valueCents,
        win: decision.winProb,
        prices: decision.decline ? null : decision.prices,
      }
      appendFileSync(file, `${JSON.stringify(line)}\n`)
    }
  }

  private bump(reason: string): void {
    this.declines[reason] = (this.declines[reason] ?? 0) + 1
  }

  decide(request: PriceRequest, now: number) {
    return bestQuote(request, this.costs(request, now), this.quotes, this.quoteParams, now)
  }

  /** Designs 2 to 4: the cost `c` of each option we offer, what an order of its kind costs this week. */
  costs(request: PriceRequest, now: number): Partial<Record<Option, number>> {
    return Object.fromEntries(
      this.offered(request, now).map((option) => [option.kind, this.costOf(request, option, now)]),
    )
  }

  /** The fees an order of this kind pays over its typical fee, and its late refunds over its price (the list price
   * at the world's level, before we price it), each times what this week pays over the prior; the late part also
   * times `mu` and the dealer's late weight. */
  costOf(request: PriceRequest, option: DeliveryOption, now: number): number {
    const { fee, late } = this.costParts(request, option, now)
    const risk = this.params.lateRisk ? this.riskOf(request, option, now) * this.params.lateRiskCents : 0
    return (fee + late) * this.params.costScale + risk
  }

  /** The late share the late-risk table predicts for this option if we win it now. */
  riskOf(request: PriceRequest, option: DeliveryOption, now: number): number {
    return lateRiskOf(this.lateRisk, request, option, now, this.setup.map)
  }

  /** The two parts of `costOf`, in cents. */
  costParts(request: PriceRequest, option: DeliveryOption, now: number): { fee: number; late: number } {
    const lastPickupAt = option.deadline - driveMinutes(this.setup.map, request.legs)
    const kind = kindOf(request.legs, option.kind, now, lastPickupAt, this.fewNear(request.legs), this.costPrior)
    const prior = priorOf(kind, this.costPrior)
    const price = option.listPriceCents * this.quoteParams.startLevel
    const lateness = lateRatio(this.cost, this.learning, now) * muOf(this.fees, this.feeParams)
    return {
      fee: request.referenceFeeCents * prior.fee * feeRatio(this.cost, kind.band, this.learning, now),
      late: price * prior.late * lateness * this.lateWeight(request.dealerId),
    }
  }

  /** Admission: the options we can serve with `comfortHours` to spare (more as the late share rises); with none, only
   * the slowest one we can serve. Up to level 3 every quote wins the first option, so only that one counts. */
  offered(request: PriceRequest, now: number): DeliveryOption[] {
    const context = this.context()
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const served = options
      .map((option) => ({ option, ...canServe(request, option, now, context) }))
      .filter((verdict) => verdict.ok)
      .filter((verdict) => !this.params.lateRisk || this.riskOf(request, verdict.option, now) < this.params.lateRiskMax)
    if (this.params.comfortHours <= 0) return served.map((verdict) => verdict.option)
    const comfortable = served.filter((v) => v.slack >= (this.params.comfortHours * HOUR) / (context.tightening ?? 1))
    return (comfortable.length > 0 ? comfortable : served.slice(-1)).map((verdict) => verdict.option)
  }

  /** The stops and audience from the order handling, each with its schedule from the fee function. An urgent
   * reprice keeps the gig as it is. */
  gig(need: GigNeed, books: Books): GigPlan[] {
    const { order, legs, previous } = need
    const shapes: GigShape[] =
      need.why === 'urgent' && previous
        ? [previous]
        : gigShape(order, legs, this.log.factsOf(order.id), this.log.retryOf(order.id, legs), books.now, this.context())
    if (shapes.length === 0) throw new Error('cannot read the order') // the harness posts the starter's gig
    return shapes.map(({ stops, audience }) => ({
      stops,
      audience,
      schedule: this.schedule(order, stops, audience.experienced, books),
    }))
  }

  /** The schedule for the cars of `stops`; from the order's deadline warning on, at least the urgent ramp. */
  schedule(order: Order, stops: GigPlan['stops'], experienced: boolean, books: Books): FeeStep[] {
    const gig = this.orderGig(order, legsOf(stops, order.id), experienced, books.now)
    if (!gig) throw new Error(`no request for order ${order.id}`) // the harness posts the starter's gig
    const { schedule } = this.plan(gig, books.now)
    if (!books.urgent.has(order.id)) return schedule
    return higher(schedule, urgentRamp(books.now, gig.typicalCents, this.params), this.setup.level)
  }

  /** Reprices our open gigs that no driver holds and the schedule no longer serves: one dropped since its schedule
   * was set, at once; one whose schedule ended `staleHours` ago, climbing. Not after the deadline warning, which has
   * its own schedule. At most `repriceMax`, the nearest last pickup first, so quotes never wait behind them. */
  tick(books: Books): Action[] {
    const now = books.now
    const due = [...this.log.gigs].flatMap(([gigId, gig]) => {
      const order = books.orders.get(gig.orderId)
      if (!order || books.urgent.has(order.id) || books.booked.has(gigId)) return []
      if (!books.gigsOf(order.id).includes(gigId)) return []
      const ended = (gig.schedule.at(-1)?.at ?? now) + this.params.staleHours * HOUR <= now
      return gig.dropped || ended ? [{ gigId, gig, order }] : []
    })
    due.sort((a, b) => a.order.lastPickupAt - b.order.lastPickupAt)
    return due.slice(0, this.params.repriceMax).flatMap(({ gigId, gig, order }) => {
      const feeGig = this.orderGig(order, gig.legs, books.posts.get(gigId)?.audience.experienced ?? false, now)
      if (!feeGig) return []
      const fee = feeAt(gig.schedule, now)
      const { level } = this.setup
      // The brief's way: the fee function again, for a gig drivers have seen, with the time left, never under the
      // fee in the app. Without the solver, the ramp from now above the dropped fee, or a climb.
      const schedule = this.params.feeSolver
        ? higher(this.plan(feeGig, now).schedule, [{ at: now, feeCents: fee }], level)
        : gig.dropped
          ? higher(
              this.plan(feeGig, now).schedule,
              [{ at: now, feeCents: fee + this.params.dropStep * feeGig.typicalCents }],
              level,
            )
          : climb(fee, now, feeGig, this.params, level)
      return schedule.length > 0 && (schedule.at(-1)?.feeCents ?? 0) > fee
        ? [{ type: 'reprice' as const, gigId, schedule }]
        : []
    })
  }

  summary(): string {
    const { requests, quoted, won, booked, paidOverTypical } = this.tally
    const level = Math.exp(this.quotes.belief.world?.[0] ?? Math.log(this.quoteParams.startLevel))
    const fees = feeRatio(this.cost, null, this.learning, this.now).toFixed(2)
    const late = lateRatio(this.cost, this.learning, this.now).toFixed(2)
    const share = (part: number, whole: number) => (whole > 0 ? `${((100 * part) / whole).toFixed(0)}%` : 'n/a')
    return [
      `bidprice: level ${level.toFixed(3)}, cost over prior: fees ${fees}, late ${late}, mu ${this.fees.mu.toFixed(2)}`,
      `quoted ${quoted} of ${requests} requests (${share(quoted, requests)}), won ${won} (${share(won, quoted)} of quoted)`,
      booked > 0
        ? `fees paid ${(paidOverTypical / booked).toFixed(2)} × typical over ${booked} bookings`
        : 'no fee paid',
      `declines ${Object.entries(this.declines)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => `${k} ${v}`)
        .join(' ')}`,
      ...(this.params.quoteAll || this.params.allOptions ? [this.widen.summary()] : []),
    ].join(', ')
  }

  /** The schedule for a gig from now, and its expected cost `c`: the ramp, or the fee model's solver behind its flag. */
  private plan(gig: FeeGig, now: number): { schedule: FeeStep[]; costCents: number } {
    if (this.params.feeSolver) return planFees(gig, now, this.fees, this.feeParams)
    const schedule = ramp(gig, now, this.params, this.setup.level)
    return { schedule, costCents: costOf(schedule, gig, now, this.fees, this.feeParams).costCents }
  }

  /** Whether the cars' delivery place has few drivers near. */
  private fewNear(legs: PriceRequest['legs']): boolean {
    return fewDriversNear(legs[0]?.delivery.placeId ?? '', this.setup.roster, this.setup.map)
  }

  /** The cost learner: the prior cost of each order won, each booking that holds, and each order settled. */
  private learnCost(event: DeskEvent): void {
    if (event.kind === 'order_won') {
      const { order } = event
      const request = this.log.requests.get(order.id)
      if (!request) return
      const kind = kindOf(
        order.legs,
        order.option,
        event.at,
        order.lastPickupAt,
        this.fewNear(order.legs),
        this.costPrior,
      )
      remember(
        this.cost,
        order.id,
        kind,
        request.referenceFeeCents,
        order.priceCents,
        order.legs.length,
        order.lastPickupAt,
        this.costPrior,
      )
    } else if (event.kind === 'order_changed') moved(this.cost, event.order.id, event.order.lastPickupAt)
    else if (event.kind === 'deadline_close') moved(this.cost, event.orderId, event.lastPickupAt)
    else if (event.kind === 'order_cancelled') cancelled(this.cost, event.orderId)
    else if (event.kind === 'picked_up') picked(this.cost, event.orderId)
    else if (event.kind === 'gig_expired' || event.kind === 'delivered') closed(this.cost, event.gigId)
    else if (event.kind === 'gig_booked') {
      const gig = this.log.gigs.get(event.gigId)
      if (gig) booked(this.cost, event.gigId, gig.orderId, gig.legs.length, event.feeCents)
    } else if (event.kind === 'gig_dropped' || event.kind === 'no_show') unbooked(this.cost, event.gigId)
    else if (event.kind === 'ledger' && event.line.orderId)
      settled(this.cost, event.line.orderId, event.line.kind, event.line.cents)
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
    if (action.type === 'reprice') {
      this.log.reprice(action.gigId, action.schedule)
      repriced(this.cost, action.gigId, action.schedule)
      return { kind: 'gig_repriced', at, gigId: action.gigId, schedule: action.schedule }
    }
    if (action.type === 'withdraw') {
      closed(this.cost, action.gigId)
      return { kind: 'gig_withdrawn', at, gigId: action.gigId }
    }
    if (action.type !== 'post') return null
    const order = this.log.orders.get(action.stops[0]?.orderId ?? '')
    if (!order) return null
    const legs = legsOf(action.stops, order.id)
    const gig = this.orderGig(order, legs, action.audience.experienced, at)
    this.log.post(gigId, order.id, legs, action.schedule)
    posted(this.cost, gigId, order.id, legs.length, action.schedule)
    if (!gig) return null
    return { kind: 'gig_posted', at, gigId, orderIds: [order.id], gig, schedule: action.schedule }
  }

  private count(event: DeskEvent): void {
    if (event.kind === 'price_request') this.tally.requests++
    else if (event.kind === 'order_won') {
      this.tally.won++
      this.widen.won(event.order.id, event.order.option, event.at)
    } else if (event.kind === 'gig_booked') {
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
