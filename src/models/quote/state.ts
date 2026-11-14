/** What the quote side remembers of a week: the belief about the level, each dealer's trust and share of the
 * requests, and the quotes that wait for an answer. Plain data, so `JSON.stringify` saves it; `observe` with every
 * event of the week, in order, rebuilds it. */
import type { DeskEvent, LedgerLine, PriceRequest } from '../../../vendor/spread-typescript/types.ts'
import { type Belief, drift, learn, level, type Term } from './belief.ts'
import { shapeOf, survival } from './flips.ts'
import { OPTIONS, type Option, type QuoteParams } from './params.ts'

const DAY = 24 * 60
const OPEN = 8 * 60 // requests come, the price war runs, from 08:00 to 18:00
const CLOSE = 18 * 60
const DECLINED = 5 // a quote at five times the list price or more is a decline: its loss says nothing

/** A quote sent, until its answer. `quotes` holds each option's [price, list price] in cents. */
export type Pending = {
  dealer: string
  day: number
  respondBy: number
  /** Drivers near the delivery place on the log2 scale, or null when unknown. */
  lane: number | null
  trust: number
  quotes: Partial<Record<Option, [number, number]>>
}

export type QuoteState = {
  belief: Belief
  /** The day of the `day` part of the belief, and the answers it has learned from. */
  day: number
  dayAnswers: number
  /** Drivers who live within 30 km of each place (`driversNear`). */
  near: Record<string, number>
  /** Requests so far, by dealer and in all. */
  requests: Record<string, number>
  requestTotal: number
  /** Each dealer's count of orders on time (RULES.md, dealer trust), and what it is counted from. */
  trust: Record<string, number>
  dealerOf: Record<string, string>
  unsettled: Record<string, number>
  settled: Record<string, true>
  pending: Record<string, Pending>
  wins: number
  answers: number
}

export function createQuoteState(near: Record<string, number> = {}): QuoteState {
  return {
    belief: {},
    day: 0,
    dayAnswers: 0,
    near,
    requests: {},
    requestTotal: 0,
    trust: {},
    dealerOf: {},
    unsettled: {},
    settled: {},
    pending: {},
    wins: 0,
    answers: 0,
  }
}

/** Feeds one event. `price_request`, `order_won`, `order_lost` and `ledger` teach; every event moves the clock,
 * which starts a new day, settles trust and counts a quote whose deadline has passed without a win as lost. */
export function observe(state: QuoteState, event: DeskEvent, params: QuoteParams): void {
  tick(state, event.at, params)
  switch (event.kind) {
    case 'price_request':
      state.requests[event.request.dealerId] = (state.requests[event.request.dealerId] ?? 0) + 1
      state.requestTotal += 1
      break
    case 'order_won':
      state.dealerOf[event.order.id] = event.order.dealerId
      answer(state, event.order.id, params, [event.order.option, event.order.priceCents])
      break
    case 'order_lost':
      answer(state, event.requestId, params)
      break
    case 'ledger':
      account(state, event.line, params)
      break
  }
}

/** Remembers the prices sent for a request, so its answer can teach. Call it with what went into the quote. */
export function recordQuote(
  state: QuoteState,
  request: PriceRequest,
  prices: Partial<Record<Option, number>>,
  params: QuoteParams,
): void {
  const quotes: Pending['quotes'] = {}
  for (const option of request.options) {
    const price = prices[option.kind]
    if (price !== undefined) quotes[option.kind] = [price, option.listPriceCents]
  }
  state.pending[request.id] = {
    dealer: request.dealerId,
    day: Math.floor(request.arrivedAt / DAY),
    respondBy: request.respondBy,
    lane: laneOf(state, request),
    trust: trustOf(state, request.dealerId, params),
    quotes,
  }
}

/** The dealer's share of the week's requests so far, starting equal for every dealer. */
export function dealerWeight(state: QuoteState, dealer: string, params: QuoteParams): number {
  return ((state.requests[dealer] ?? 0) + 1) / (state.requestTotal + params.dealers)
}

/** The dealer's count of orders on time, as the dealer counts it. */
export function trustOf(state: QuoteState, dealer: string, params: QuoteParams): number {
  return Math.min(params.trustCap, state.trust[dealer] ?? 0)
}

/** Requests still to come this week from the minute `from` on: the rate so far, leaning on the prior early in the
 * week. */
export function requestsLeft(state: QuoteState, now: number, params: QuoteParams, from: number = now): number {
  const done = weekShare(now)
  const prior = 0.1 // the prior counts as a tenth of a week
  return ((state.requestTotal + prior * params.requestsPerWeek) / (done + prior)) * (1 - weekShare(Math.max(now, from)))
}

/** The share of the week's request hours (Monday to Friday, 08:00 to 18:00) that has passed. */
export function weekShare(now: number): number {
  let open = 0
  for (let day = 0; day < 5; day++) open += Math.min(CLOSE, Math.max(OPEN, now - day * DAY)) - OPEN
  return open / (5 * (CLOSE - OPEN))
}

/** The parts of the level of `option` for a request: the world, its day, the lane, the option and the trust. */
export function termsFor(
  option: Option,
  lane: number | null,
  trust: number,
  sameDay: boolean,
  params: QuoteParams,
): Term[] {
  const terms: Term[] = [{ key: 'world', weight: 1, prior: [Math.log(params.startLevel), params.worldSd ** 2] }]
  if (sameDay) terms.push(dayTerm(params))
  if (params.flags.lane && lane !== null) {
    const prior = params.laneSlope * (lane - params.laneCenter)
    terms.push({ key: `lane:${lane}`, weight: 1, prior: [prior, params.laneSd ** 2] })
  }
  if (params.flags.ladder) {
    terms.push({ key: `option:${option}`, weight: 1, prior: [Math.log(params.ladder[option]), params.ladderSd ** 2] })
  }
  if (params.flags.trust)
    terms.push({ key: 'trust', weight: trust, prior: [params.trustPerOrder, params.trustSd ** 2] })
  return terms
}

/** The terms of a request's option now. */
export function requestTerms(state: QuoteState, request: PriceRequest, option: Option, params: QuoteParams): Term[] {
  return termsFor(option, laneOf(state, request), trustOf(state, request.dealerId, params), true, params)
}

/** Drivers near the delivery place of the request's first leg, on the log2 scale the lanes pool by. */
export function laneOf(state: QuoteState, request: PriceRequest): number | null {
  const near = state.near[request.legs[0]?.delivery.placeId ?? '']
  return near === undefined ? null : Math.round(Math.log2(1 + near))
}

/** Today's level against the world's, while the price war could run: a fall of `warDrop` or more, seen in at least
 * ten answers today, is the war, and with `war: 'decline'` we decline until 18:00. */
export function inWar(state: QuoteState, now: number, params: QuoteParams): boolean {
  const minute = now % DAY
  if (params.flags.war !== 'decline' || minute < OPEN || minute >= CLOSE || state.dayAnswers < 10) return false
  const [mean] = state.belief.day ?? dayTerm(params).prior
  return mean <= -params.warDrop
}

function dayTerm(params: QuoteParams): Term {
  return { key: 'day', weight: 1, prior: [0, params.daySd ** 2] }
}

function tick(state: QuoteState, now: number, params: QuoteParams): void {
  const day = Math.floor(now / DAY)
  if (day !== state.day) {
    state.day = day
    state.dayAnswers = 0
    delete state.belief.day
  }
  settle(state, now, params)
  for (const [id, quote] of Object.entries(state.pending)) {
    if (quote.respondBy < now) answer(state, id, params)
  }
}

/** Learns from the answer to a quote at the option that was likeliest to win: a loss says the dealer turned down
 * even that one, and a win with several options quoted says no more than that one would have won (the option taken
 * may be a pricier rung, taken for its speed). A win with one option is learned at the price taken. */
function answer(state: QuoteState, id: string, params: QuoteParams, won?: [Option, number]): void {
  const quote = state.pending[id]
  if (!quote) return
  delete state.pending[id]
  const shape = shapeOf(params)
  const sameDay = quote.day === state.day
  const termsOf = (option: Option) => termsFor(option, quote.lane, quote.trust, sameDay, params)
  let seen: { option: Option; x: number; chance: number } | undefined // x: the log of price / list
  let offered = 0
  for (const option of OPTIONS) {
    const [price, list] = quote.quotes[option] ?? [0, 0]
    if (price <= 0 || price >= DECLINED * list) continue
    offered += 1
    const x = Math.log(price / list)
    const chance = survival(shape, x - level(state.belief, termsOf(option)).mean)
    if (!seen || chance > seen.chance) seen = { option, x, chance }
  }
  if (won && offered <= 1) {
    const list = quote.quotes[won[0]]?.[1]
    seen = list ? { option: won[0], x: Math.log(won[1] / list), chance: 0 } : undefined
  }
  if (!seen) return
  learn(state.belief, termsOf(seen.option), seen.x, won !== undefined, shape)
  if (sameDay) {
    drift(state.belief, dayTerm(params), params.dayDrift)
    state.dayAnswers += 1
  }
  state.answers += 1
  if (won) state.wins += 1
}

/** Counts trust from the account: a revenue line with no late refund by the next minute is an order on time
 * (+1, up to the cap); a late refund or an undelivered penalty halves the dealer's count. */
function account(state: QuoteState, line: LedgerLine, params: QuoteParams): void {
  const order = line.orderId
  if (!order) return
  if (line.kind === 'revenue') {
    if (!state.settled[order]) state.unsettled[order] = line.at
  } else if ((line.kind === 'late_refund' || line.kind === 'undelivered_penalty') && !state.settled[order]) {
    delete state.unsettled[order]
    state.settled[order] = true
    const dealer = state.dealerOf[order]
    if (dealer) state.trust[dealer] = Math.floor(trustOf(state, dealer, params) / 2)
  }
}

function settle(state: QuoteState, now: number, params: QuoteParams): void {
  for (const [order, at] of Object.entries(state.unsettled)) {
    if (at >= now) continue
    delete state.unsettled[order]
    if (state.settled[order]) continue
    state.settled[order] = true
    const dealer = state.dealerOf[order]
    if (dealer) state.trust[dealer] = Math.min(params.trustCap, (state.trust[dealer] ?? 0) + 1)
  }
}
