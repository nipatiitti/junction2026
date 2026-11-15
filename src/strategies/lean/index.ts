/** The lean strategy: the whole policy in three decisions, each from the measured level 8 facts (README.md).
 *
 * 1. Price. Each option is quoted at the price that earns the most: the chance that the dealer takes it (demand.ts,
 *    learned from this week's wins and losses) times what the win leaves after the drivers (supply.ts, learned from
 *    this week's bookings, and outlook.ts, what this request costs against the mean order).
 * 2. Fee. A gig holds `open` × typical and raises only at a few hours of its own before the last pickup (fees.ts):
 *    drivers who see fees rise wait for the rise. It climbs fast only when the last pickup is near.
 * 3. Serve. Only options that can arrive on time with room to spare are quoted, and the note decides the windows,
 *    plates and licence of every gig (src/ops). Open cars that one driver can take in a row go out as one gig
 *    (planner.ts, chains.ts).
 *
 * All state is rebuilt from `observe` and `sent`, so a restart in the final loses nothing. */
import type {
  Action,
  ActionResult,
  DeliveryOption,
  DeskEvent,
  FeeStep,
  Order,
  PriceRequest,
  StopRef,
} from '../../../vendor/spread-typescript/spread.ts'
import {
  type Context,
  canServe,
  DAY,
  driveMinutes,
  earliestPickup,
  FIRST_TRY,
  features,
  gigShape,
  HOUR,
  type NoteFacts,
  type Retry,
  readNote,
  retryAfter,
  type Setback,
  type Snowfall,
} from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import { loadChains } from './chains.ts'
import { bestPrice, Demand } from './demand.ts'
import { awake, BOOK_AHEAD, fast, feeAt, planBy, SHORT, stepped } from './fees.ts'
import { loadOrders, type OrderModel, outlook } from './outlook.ts'
import { Planner } from './planner.ts'
import { Supply } from './supply.ts'
import { valueCharge } from './value.ts'

export const DEFAULTS = {
  /** The fee a gig opens at, × typical (fees.ts, `stepped`). It holds it and raises three times over the waking
   * time that drivers have to plan the gig: after `raiseAt1` to `raiseAt3` of that time, to `raise1` to `raise3` ×
   * typical, and to `urgentTop` when the time is over. The opening is measured (README.md); the raises are not. */
  open: 0.88,
  raiseAt1: 0.3,
  raise1: 1.05,
  raiseAt2: 0.55,
  raise2: 1.25,
  raiseAt3: 0.8,
  raise3: 1.55,
  /** 1 moves each gig's raises by up to 20 minutes either way and their size by up to 5%, drawn from the order id,
   * so that drivers cannot time a second look; 0 keeps the table. */
  jitter: 1,
  /** The fee a gig for a later day shows in its first waking hour, × typical; 0 opens at `open`. */
  early: 0.8,
  /** A gig whose last pickup is on the Monday after the weekend raises on that Monday from 06:00, not over the
   * weekend, when 2 drivers a week book (fees.ts, `rested`); false spreads the raises over the weekend as before. */
  rest: true,
  /** A gig posted with under `lateWithin` waking minutes left to plan it opens at `lateOpen` × typical and climbs
   * as an urgent one does: 5 such cars a week opened at 2 × typical and were booked within 3 minutes. */
  lateWithin: 60,
  lateOpen: 1.15,
  /** The urgent climb, for a gig after its deadline warning or with under 45 minutes left to book: it opens at
   * `urgentOpen` × typical (and 0.05 over the fee it showed), and rises `urgentStep` every `urgentEvery` waking
   * minutes to `urgentTop`. The top was 2 until 15 November: with 1.6 here and `lateTop` 1.3, 30 fresh server seeds
   * made +€483 to +€558 a week at 0.2 to 0.5 points fewer orders on time (#367). The other three are not measured. */
  urgentOpen: 1.15,
  urgentStep: 0.125,
  urgentEvery: 15,
  urgentTop: 1.45,
  /** The climb of a car that is late already: from `lateFrom` × typical, `lateStep` every `lateEvery` waking
   * minutes, to `lateTop` (1.7 until 15 November, measured with `urgentTop`). The other three are not measured. */
  lateFrom: 1.1,
  lateStep: 0.05,
  lateEvery: 30,
  lateTop: 1.3,
  /** What a booking costs × typical before this week's bookings say (supply.ts). */
  feeRatio: 0.8,
  /** `lateCost` × the list price for each unit of the request's chance to be late (outlook.ts). */
  lateCost: 1,
  /** A premium car's cost × this. Below level 7, where the order model does not play: what a private pickup and a
   * private delivery add × typical. */
  premium: 3,
  privatePickup: 0.25,
  privateDelivery: 0.25,
  /** The level of the cost in a price: this × what this week's bookings pay for such a car (supply.ts) × what the
   * order model says of this request against the mean order (outlook.ts, mean 1). It is the only level: 0.98 is the
   * one that the server played (five seeds, 351 orders a week); at 1.07 every quote rose 5% and 29 orders a week
   * were lost for the same margin. */
  costLevel: 1.01,
  /** × what the order model adds to the cost of a long drive (outlook.ts: over three hours of driving, up to 0.21 ×
   * typical). 1 is the fit; the chance to be late keeps its long-drive terms, and `lateCost` prices them. */
  longCost: 1,
  /** An option needs this many waking hours between now and the last minute to book, or we do not quote it. */
  minHours: 4,
  /** The noise that stays in one request's threshold, as a logistic scale in log price: 0.12 ± 0.006 on 60 server
   * weeks of ten seeds at different volumes (analysis/supply_curve.py), 0.10 to 0.12 in per-day fits. It is also a
   * markup: the best price keeps at least this share of itself over the cost it is chosen over. Until 15 November
   * it was 0.28 and did the work of the charge below as well: no price under 1.39 × cost. */
  noise: 0.11,
  /** A lost request's quoted options share one world, day, dealer and route. True averages their contributions to
   * those effects instead of training them once per option; each option effect still learns separately. 63% of
   * the requests have several options, so a loss counted two or three times where a win counts once. 35 server
   * seeds: about +€366 ± 147 a week, with 5% fewer orders at a price 2 to 3% higher. */
  sharedOutcome: true,
  /** What one more order costs the rest of the week's orders, in higher fees and late cars, added to the cost
   * that the price is chosen over: a request whose best price is under (cost + charge) ÷ (1 − `noise`) is not
   * worth its place. The charge is (`tax` + `taxLoad` × the orders per driver that the week is heading for) × the
   * order's cost, plus `taxEuros` euros. The fit: each order per driver more raised the fee paid by 0.355 × typical
   * and the refunds by €6.51 an order, so one more order costs the others €28.7 × orders per driver, which is
   * 0.47 of the mean order's cost. A week that wins more raises its own charge, and settles where the next order
   * earns nothing. Ten server seeds against `noise` 0.28: +€972 ± 386 a week; a fixed `tax` of 0.24 to 0.32 made
   * +€513 to +€729, and under 0.24 or over 0.32 nothing. */
  tax: 0,
  taxEuros: 0,
  taxLoad: 0.47,
  /** The multiple of the list price at which half of the quotes win at level 8, before the week's wins and losses
   * say (demand.ts). Measured over whole weeks, so with some trust in it: at zero trust the 349 recorded seeds
   * give 1.25. On the simulator 1.3 and 1.5 were flat or worse. */
  middle: 1.55,
  /** How much of the dealer's trust (1% for each order on time) goes into the price. */
  trust: 0.55,
  /** The late share from which options need twice the room. */
  lateHard: 0.05,
  /** Chains (chains.ts): post open cars together when one driver can take them one after the other. A car joins
   * when the next is collected within `maxHop` road minutes of its delivery, a chain holds `maxCars` at most and
   * must cost a driver `minSaving` less than its cars alone. */
  chains: true,
  maxHop: 60,
  maxCars: 4,
  minSaving: 0.15,
  /** The most hours of driving in a chain. The rules allow 12; chains of 8 book 50% of the time and of 10 25%, and
   * their drivers finish the next day. */
  maxDrive: 8,
  /** Only a chain with this many hours to its first last pickup is posted, from Monday to Thursday and with a car
   * that no driver has seen: such chains booked 69% of the time, the others 23% (28 server weeks). */
  pickLead: 20,
  /** A chain may be in the app while drivers have this many waking hours left to plan the day of its last start
   * (planner.ts, `mayBeOpen`); then its cars go back to single gigs. */
  chainLast: 3,
  /** A new car that may join a chain waits this many hours for a partner before it is posted alone: half of the
   * single gigs book within half an hour, before a partner can arrive. 0 posts at once. */
  holdHours: 3,
  /** A chain that no driver took this many waking hours after its post is taken apart: 51% of the chains book
   * within the hour, and one still open then books 24% of the time. 0 waits until `chainLast`. */
  chainPatience: 1,
  /** A car may be in this many chains that no driver took before it stays a single gig: a failed chain costs its
   * cars 0.01 × typical (1.04 against 1.03, 15 server weeks). A later chain needs a car that no driver has seen,
   * so it is never the same chain again. With the chain model, 3 made €212 a week more than 2 over 20 server seeds
   * and 5 made €193 less than 3 over ten; without the model 2 lost. */
  chainTries: 3,
  /** How much a chain's chance to book counts when two chains want the same car (chains.ts, `bookChance`): the
   * best chain saves the most × its chance to this power. 0 ranks by the saving alone. */
  chainFit: 0,
  /** A chain's fees × what the chain is worth to a driver (chains.ts): 1 opens it at `open` × that worth. */
  chainOpen: 1,
  /** 1 draws each chain's fee level from 0.78, 0.88, 1 and 1.12 × `chainOpen` by its cars' orders: an experiment
   * that measures how a chain's fee moves its chance to book. 0 is off. */
  chainSpread: 0,
  /** Price and rank the chains by the chain model (chains.ts, chain.json): each chain gets the fee level from
   * 0.85 to 1.3 that earns the most over its cars as single gigs, by its chance to book at that level, the best
   * chain earns the most a car, and a chain that earns nothing is not posted. With `chainTries` 3 on 20 server
   * seeds: +€1,126 a week, 71% of the chains book where 53% did, and 197 cars a week ride in them where 117 did. */
  chainModel: true,
  /** With the model: × what a chain's cars are taken to pay as single gigs (0.94 on the Monday, 0.99 after). Over
   * 1 the model pays chains more, so more of them book. */
  chainAlone: 0.97,
  /** Direct offers of an open chain to the drivers who viewed it and did not book, at this × the fee in the app
   * (planner.ts). 0 sends none. `chainOfferSpread` 1 draws each chain's offer level from 1, 1.15 and 1.3: an
   * experiment that measures what such offers do. */
  chainOffers: 0,
  chainOfferSpread: 0,
  /** A chain opens at `chainStart` × its fee and reaches the fee in steps over `chainRamp` waking minutes; its
   * `chainPatience` counts from the end of the ramp. 97% of the chains book at their opening fee, after 3 minutes
   * at the median (five ranking runs). 1 opens at the fee. */
  chainStart: 1,
  chainRamp: 20,
  /** Chains are posted on the first `chainDays` days of the week: 4 is Monday to Thursday, 5 adds Friday (+€119 to
   * +€310 a week on 20 server seeds; 6 plays the same weeks, as no car is won on a Saturday). */
  chainDays: 5,
  /** The rescue of the delivery minimum (a week under 90% on time scores nothing). When the late orders and the
   * warned cars without a driver reach this share of the orders won, the week stops adding risk and buys drivers:
   * no `taxFade`, no `pairShare`, and a warned car climbs from 1.6 × typical by 0.2 every 10 waking minutes to 3 ×.
   * A late car gives 25 to 50% of its price back anyway. It stays on to the end of the week. 0 is off. */
  rescue: 0,
  /** The guard of the flu day (the rules: in every level 8 week 30% of the drivers stay at home for one day, and
   * nobody announces it). The drivers give their gigs of that day back in its first hour: 10 of them at the
   * median, against 3 on the next-worst day (41 server weeks). When that hour holds this many, the day and the
   * next play safe: no `taxFade`, no `pairShare`, and the urgent and late climbs go to 2 and 1.7 × typical at
   * least. 0 is off. */
  guard: 0,
  /** The share of a chain's saving that comes off the cost of a request which would ride in that chain with open
   * cars we hold (planner.ts, `saving`): such a car costs the chain's rate, not a single gig's, and it makes its
   * partners cheaper too. 0 prices every request as a single gig. */
  pairShare: 0.3,
  /** How much of the `taxLoad` charge is gone on Friday, and half of that on Thursday: an order costs the cars booked
   * after it, and few are booked after a Friday's. 0 keeps the charge all week, 1 has none on Friday. */
  taxFade: 1,
  /** Not 0: the charge of `taxLoad` gives way to this × the value table's (value.ts, value.json, fitted by
   * analysis/lean_value.py): what the order costs the cars booked after it, by the hour of the week and the orders
   * won so far per driver (dear on Monday, cheap on Friday; at 1 it has the mean of the `taxLoad` charge), and
   * what it adds to the risk of a week under 90% on time, which grows with the late share so far. */
  value: 0,
  /** The room for late orders (a week under 90% on time scores nothing). After the last request the week knows how
   * many more late orders it can take: a tenth of its orders, less the late ones. Each order without a driver has a
   * measured chance to be late (ROOM_RISK), and the worst saved week had 3.2 × the sum of those chances. When this ×
   * the sum is more than the room, the fees of the orders at risk rise step by step on Saturday and Monday, until
   * enough of them have a driver. In 174 of 188 saved weeks the sum stays under the room and nothing changes. 0 is
   * off. */
  room: 3.5,
  /** Not 0: a car that has missed its last pickup, and is late whatever happens, starts again as a car for a later
   * day (#387). Its single gig is taken out and posted again at once, with windows that run to the end of the
   * world, at this × typical, and takes the usual raises towards the next weekday on which it can be collected.
   * Without it the gig stays in the app until a window ends, 2.5 hours on average, where no driver can book it, and
   * the repost holds the 1.65 × typical that the urgent climb reached: 15 cars a week, half of them booked within
   * 10 minutes of the repost, mostly between 18:00 and 21:00, and €774 a week paid over 1.0 × typical (50 server
   * weeks). At 1 on eight fresh server seeds: +€545 ± 187 a week, ahead on 7 of 8; such cars paid 1.20 × typical.
   * 0 is off. */
  lateRestart: 0.9,
}
export type LeanParams = typeof DEFAULTS

type OptionKind = DeliveryOption['kind']
const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))
const pickups = (stops: readonly StopRef[]): StopRef[] => stops.filter((stop) => stop.kind === 'pickup')
/** An urgent climb opens this much × typical over the fee the gig showed. */
const URGENT_RAISE = 0.05
/** The last pickup of an option, before the world says it: its deadline less the road minutes × DRIVE_PAD and
 * ARRIVE_AHEAD minutes. A quote goes out up to QUOTE_WAIT minutes after it is decided (one step of the harness). */
const DRIVE_PAD = 1.1
const ARRIVE_AHEAD = 30
const QUOTE_WAIT = 15
/** The median number of drivers in a world: the order model counts a world's drivers against it. */
const MEDIAN_DRIVERS = 777
/** The requests of a level 8 week, and the load that the charge of `taxLoad` assumes before the week says: 0.5
 * orders per driver, held as if `LOAD_PRIOR` requests had been seen at it. */
const WEEK_REQUESTS = 1033
const LOAD_START = 0.5
const LOAD_PRIOR = 150
/** The late share starts as if this many orders had arrived on time, and an order warned without a driver counts
 * as this much of a late one. From `lateHard` on, options need 1 / HARD_ROOM times the room (src/ops/serve.ts takes
 * no less than 0.5). */
const LATE_PRIOR = 20
const AT_RISK = 0.5
const HARD_ROOM = 0.5
/** The rescue (`rescue`): not before this many orders are won, and a warned car's climb × typical. */
const RESCUE_ORDERS = 50
const [RESCUE_OPEN, RESCUE_STEP, RESCUE_EVERY, RESCUE_TOP] = [1.6, 0.2, 10, 3]
/** The room for late orders (`room`). It counts from Friday 21:00: the last request of a level 8 week comes on
 * Friday before 18:20. The chance of an order without a driver on Saturday 07:00 to be late, by whether its typical
 * fee is ROOM_LONG or more and whether its last pickup is before ROOM_EARLY on its day (5,911 such orders of 188
 * server weeks): 38%, 15%, 19% and 5%. */
const ROOM_FROM = 4 * DAY + 21 * HOUR
const ROOM_LONG = 8000
const ROOM_EARLY = 15 * HOUR
const ROOM_RISK = { longEarly: 0.4, longLate: 0.16, shortEarly: 0.22, shortLate: 0.06 }
/** The fees rise for the orders with this chance or more. A rise is ROOM_STEP × typical over the fee shown, to
 * ROOM_OPEN × typical at least and ROOM_TOP at most: every 60 minutes on Saturday and every 30 on Monday, between
 * 05:00 and 21:00 (Saturday's drivers book from 05:00 to 10:00, Monday's from 06:00 to 09:00, and nobody books on
 * a Sunday: 12 bookings in 62,000 views). */
const ROOM_RAISE = 0.15
const [ROOM_OPEN, ROOM_STEP, ROOM_TOP] = [1.1, 0.1, 2.5]
const [ROOM_WAKE, ROOM_SLEEP, ROOM_REST] = [5 * HOUR, 21 * HOUR, 6]
/** The guard (`guard`) counts the gigs given back in the first GUARD_HOUR minutes of a day, and lifts the climbs to
 * these × typical. */
const [GUARD_HOUR, GUARD_URGENT, GUARD_LATE] = [60, 2, 1.7]
/** A request's cost with a chain partner is no less than this × its cost alone (`pairShare`). */
const PAIR_LEAST = 0.4
/** A car past its last pickup (`lateRestart`) aims at the same minute of a later weekday, this far ahead or more. */
const LATE_AHEAD = 3 * HOUR
/** The last pickup that a car past its own aims at: the refund steps count hours and then business days, so the
 * next weekday is the next step. */
function laterPickup(lastPickup: number, now: number): number {
  let at = lastPickup + DAY
  while (at < now + LATE_AHEAD || Math.floor(at / DAY) % 7 >= 5) at += DAY
  return at
}
/** A booking teaches the supply no less and no more than these × typical. */
const BOOKED_LOW = 0.3
const BOOKED_HIGH = 2.5
/** Below level 7, where the order model does not play: what a trade-in, a delivery over a weekend and a note that
 * narrows the work add × typical. */
const TRADE_IN = 0.05
const WEEKEND = 0.05
const NARROW_NOTE = 0.03
/** Whether a car with this last pickup must be collected on the day of the minute `at`. */
const goesToday = (lastPickup: number, at: number): boolean => lastPickup < (Math.floor(at / DAY) + 1) * DAY

class Lean extends Strategy<LeanParams> {
  override readonly every = 15
  private readonly demand: Demand
  private readonly planner: Planner
  private readonly supply: Supply
  private readonly outlooks: OrderModel | undefined
  /** Place id -> the drivers who live there; day -> the orders won on it. */
  private readonly homes = new Map<string, number>()
  private readonly wonOn = new Map<number, number>()
  /** Our orders as their events told them: the books of a rebuilt week hold them as they are at the rebuild. */
  private readonly orders = new Map<string, Order>()
  /** Our quotes that wait for the dealer: request id -> prices, and the dealer's trust when they were sent. */
  private readonly pending = new Map<string, { prices: Prices; offset: number }>()
  /** Order id -> what the supply learns from its booking: its effects, and what the order model expected of it
   * when it was won. */
  private readonly wonAs = new Map<string, { keys: string[]; expected: number }>()
  /** Gig id -> the schedule in the app. */
  private readonly schedules = new Map<string, FeeStep[]>()
  /** Gig id -> the fee its driver booked at, for the gigs a driver gave back. */
  private readonly dropped = new Map<string, number>()
  private readonly bookedAt = new Map<string, number>()
  /** "<order id> <leg>" -> what the car's setbacks taught. */
  private readonly retries = new Map<string, Retry>()
  /** Order id -> the fee that its last gig showed when its window ended, × that gig's fee unit. */
  private readonly floors = new Map<string, number>()
  private readonly forecasts: Snowfall[] = []
  /** Dealer id -> its delivered orders, in order; and the orders with a refund. */
  private readonly delivered = new Map<string, string[]>()
  private readonly late = new Set<string>()
  private done = 0
  /** The minutes at which a driver gave a gig back in the first hour of a day; and the guard's state. */
  private readonly troubles: number[] = []
  private guardSeen = 0
  /** Whether the rescue is on, and the gigs it gave a new schedule. */
  private rescueOn = false
  private readonly rescued = new Set<string>()
  private guardUntil = -1
  /** The room for late orders: the orders whose car a driver has, the minute of the last rise, the rises made and
   * the weeks' state at the first one. */
  private readonly picked = new Set<string>()
  private roomAt = -1
  /** The orders whose gig `lateRestart` has looked at: each is posted again once. */
  private readonly restarted = new Set<string>()
  private readonly roomTally = { rises: 0, gigs: 0, first: '' }
  private readonly tally = {
    requests: 0,
    quoted: 0,
    won: 0,
    multiples: 0,
    bookings: 0,
    ratios: 0,
    pairs: 0,
    pairCents: 0,
    restarts: 0,
  }
  constructor(setup: Setup, params: LeanParams) {
    super(setup, params)
    this.supply = new Supply(params.feeRatio)
    this.outlooks = setup.level >= 7 ? loadOrders() : undefined
    for (const d of setup.roster) this.homes.set(d.homePlaceId, (this.homes.get(d.homePlaceId) ?? 0) + 1)
    this.demand = new Demand(setup.level, params.noise, params.middle)
    this.planner = new Planner(params, setup.map, params.chains && setup.level >= 3, {
      context: () => this.context(),
      troubled: (orderId) => this.retries.has(`${orderId} 0`),
      homes: this.homes,
      load: () => this.tally.bookings / (setup.roster.length || MEDIAN_DRIVERS),
      model: params.chainModel ? loadChains() : undefined,
    })
  }

  // ------------------------------------------------------------------------------------------------- the price

  quote(request: PriceRequest, books: Books): Prices | null {
    const now = books.now
    const lateShare = this.lateShare(books)
    this.rescuing(books)
    const context = this.context(lateShare > this.params.lateHard ? HARD_ROOM : 1)
    const facts = readNote(request.note, request.arrivedAt)
    const options = this.setup.level <= 3 ? request.options.slice(0, 1) : request.options
    const quotes: [OptionKind, number][] = []
    const open = this.openGigs(books)
    // The load charge fades from Wednesday to Friday by `taxFade`: few cars are booked after a Friday order.
    const fade = this.guarded(now) ? 1 : 1 - this.params.taxFade * clamp((Math.floor(now / DAY) - 2) / 2, 0, 1)
    const tax = this.params.tax + (this.params.value ? 0 : this.params.taxLoad * this.load() * fade)
    const won = this.tally.won / (this.setup.roster.length || MEDIAN_DRIVERS)
    for (const option of options) {
      if (!canServe(request, option, now, context).ok) continue
      if (this.setup.level <= 3) return { [option.kind]: option.listPriceCents }
      const cost = this.cost(request, option, facts, now, open, books)
      if (cost === null) continue
      const belief = this.demand.belief(this.demand.keys(request, option.kind), this.trustOffset(request.dealerId))
      const charge = this.params.value
        ? this.params.value * valueCharge(now, won, lateShare, option.kind, request.referenceFeeCents)
        : 0
      const best = bestPrice(belief, option.listPriceCents, cost * (1 + tax) + this.params.taxEuros * 100 + charge)
      if (best === null) continue
      quotes.push([option.kind, Math.round(best)])
    }
    return quotes.length > 0 ? Object.fromEntries(quotes) : null
  }

  /** The orders per driver that the week is heading for: the share of the requests won so far, over a week's
   * requests and the world's drivers. */
  private load(): number {
    const drivers = this.setup.roster.length || MEDIAN_DRIVERS
    const start = (LOAD_START * drivers) / WEEK_REQUESTS
    const share = (this.tally.won + LOAD_PRIOR * start) / (this.tally.requests + LOAD_PRIOR)
    return (share * WEEK_REQUESTS) / drivers
  }

  /** What the drivers of an option cost: the typical fee × what bookings pay this week, more when the gig has
   * little time to find its driver or is work that drivers ask more for. */
  private cost(
    request: PriceRequest,
    option: DeliveryOption,
    facts: NoteFacts,
    now: number,
    open: number,
    books: Books,
  ): number | null {
    const f = features(request, this.setup.map, option)
    const deadline = Math.min(option.deadline, facts.deadline ?? Infinity)
    const lastPickup = deadline - DRIVE_PAD * driveMinutes(this.setup.map, request.legs) - ARRIVE_AHEAD
    const time = awake(now + QUOTE_WAIT, lastPickup - BOOK_AHEAD)
    if (time < this.params.minHours * HOUR) return null // too little time for the raises to find a driver
    const leg = request.legs[0]
    const keys = this.supply.keys(leg?.pickup.placeId, leg?.delivery.placeId, goesToday(lastPickup, now))
    // The one level of the cost: what this week's bookings pay for such a car, × `costLevel`.
    let ratio = this.params.costLevel * this.supply.ratio(keys)
    const readyAt = Math.max(leg?.pickup.window.from ?? now, earliestPickup(facts) ?? 0)
    const view = this.view(request, deadline, lastPickup, readyAt, now, open)
    if (view) {
      ratio *= view.cost
      if (f.premium) ratio *= this.params.premium
      const cents = request.referenceFeeCents * ratio + view.late * this.params.lateCost * option.listPriceCents
      return this.paired(cents, request, readyAt, lastPickup, deadline, books)
    }
    if (f.privatePickup) ratio += this.params.privatePickup
    else if (f.privateDelivery) ratio += this.params.privateDelivery
    if (f.tradeIn) ratio += TRADE_IN
    if (f.weekendDelivery) ratio += WEEKEND
    if (facts.deadline !== null || facts.pickupHours !== null || facts.deliveryHours !== null) ratio += NARROW_NOTE
    if (f.premium) ratio *= this.params.premium // one driver in twelve may take it
    return request.referenceFeeCents * ratio
  }

  /** Whether the rescue is on (`rescue`): from the tick at which the late orders and the warned cars without a
   * driver are `rescue` of the orders won. */
  private rescuing(books: Books): boolean {
    const least = this.params.rescue
    if (!(least > 0) || this.rescueOn) return this.rescueOn
    let atRisk = 0
    for (const id of books.urgent) {
      const order = books.orders.get(id)
      const waits = order?.deliveredAt.some((at) => at === null) && !books.gigsOf(id).some((g) => books.booked.has(g))
      if (waits) atRisk++
    }
    this.rescueOn = this.tally.won >= RESCUE_ORDERS && (this.late.size + atRisk) / this.tally.won >= least
    return this.rescueOn
  }

  /** Whether the guard is up at `now` (`guard`): from the minute that the first hour of a day held `guard` gigs
   * given back, to the end of the next day. It depends only on the events, so a rebuilt week decides the same. */
  private guarded(now: number): boolean {
    if (this.rescueOn) return true
    const least = this.params.guard
    if (!(least > 0)) return false
    while (this.guardSeen < this.troubles.length) {
      const at = this.troubles[this.guardSeen++] as number
      const day = Math.floor(at / DAY) * DAY
      const burst = this.troubles.filter((other) => other >= day && other <= at).length
      if (burst >= least) this.guardUntil = day + 2 * DAY
    }
    return now < this.guardUntil
  }

  /** The cost of a request that would ride in a chain with open cars we hold: less `pairShare` of what that chain
   * saves (planner.ts, `saving`), and no less than PAIR_LEAST of the cost. */
  private paired(
    cents: number,
    request: PriceRequest,
    ready: number,
    lastPickup: number,
    deadline: number,
    books: Books,
  ): number {
    if (!(this.params.pairShare > 0) || this.guarded(books.now)) return cents
    const saving = this.planner.saving(request, ready, lastPickup, deadline, books)
    if (saving <= 0) return cents
    this.tally.pairs++
    this.tally.pairCents += saving
    return Math.max(PAIR_LEAST * cents, cents - this.params.pairShare * saving)
  }

  /** What the order model expects of this work at the minute `at` (outlook.ts): its cost against the mean order's,
   * and its chance to be late. Undefined below level 7, where the model does not play. */
  private view(
    request: PriceRequest,
    deadline: number,
    lastPickupAt: number,
    readyAt: number,
    at: number,
    open: number,
  ): { cost: number; late: number } | undefined {
    if (!this.outlooks) return undefined
    const leg = request.legs[0]
    const f = features(request, this.setup.map)
    return outlook(
      this.outlooks,
      {
        typicalCents: request.referenceFeeCents,
        at,
        readyAt,
        lastPickupAt,
        deadline,
        driveMinutes: leg ? driveMinutes(this.setup.map, [leg]) : 0,
        privatePickup: f.privatePickup,
        privateDelivery: f.privateDelivery,
        premium: f.premium,
        electric: request.legs.some((l) => l.car.electric),
        tradeIn: f.tradeIn,
        hasNote: Boolean(request.note),
        homePickup: this.homes.get(leg?.pickup.placeId ?? '') ?? 0,
        homeDelivery: this.homes.get(leg?.delivery.placeId ?? '') ?? 0,
        drivers: this.setup.roster.length || MEDIAN_DRIVERS,
        won: this.tally.won,
        wonToday: this.wonOn.get(Math.floor(at / DAY)) ?? 0,
        open,
      },
      this.params.longCost,
    )
  }

  /** Our gigs that wait for a driver. */
  private openGigs(books: Books): number {
    let open = 0
    for (const order of books.orders.values())
      for (const gigId of books.gigsOf(order.id)) if (!books.booked.has(gigId)) open++
    return open
  }

  /** Late orders, and half of each one warned without a driver, over the orders done (and 20 on time for a start). */
  private lateShare(books: Books): number {
    let atRisk = 0
    for (const id of books.urgent) {
      const order = books.orders.get(id)
      const waits = order?.deliveredAt.some((at) => at === null) && !books.gigsOf(id).some((g) => books.booked.has(g))
      if (waits) atRisk++
    }
    return (this.late.size + AT_RISK * atRisk) / (this.done + atRisk + LATE_PRIOR)
  }

  /** The dealer's trust as a move of its threshold: each order on time adds 1%, a late one halves the count. */
  private trustOffset(dealerId: string): number {
    return this.params.trust * Math.log(1 + this.trustCount(dealerId) / 100)
  }

  /** The dealer's count of orders on time, up to 25; a late one halves it. */
  private trustCount(dealerId: string): number {
    let count = 0
    for (const id of this.delivered.get(dealerId) ?? [])
      count = this.late.has(id) ? Math.floor(count / 2) : Math.min(25, count + 1)
    return count
  }

  /** A quote won (with the option the dealer took) or lost: the demand learns. */
  private outcome(requestId: string, won: OptionKind | null, at: number, books: Books): void {
    const quoted = this.pending.get(requestId)
    const request = books.requests.get(requestId)
    this.pending.delete(requestId)
    if (won) {
      this.tally.won++
      const day = Math.floor(at / DAY)
      this.wonOn.set(day, (this.wonOn.get(day) ?? 0) + 1)
    }
    if (!quoted || !request) return
    const { prices, offset } = quoted
    if (this.params.sharedOutcome && won === null) {
      const outcomes = request.options.flatMap((option) => {
        const cents = prices[option.kind]
        if (cents === undefined) return []
        return [
          {
            keys: this.demand.keys(request, option.kind),
            offset,
            multiple: cents / option.listPriceCents,
            won: false,
          },
        ]
      })
      this.demand.learnShared(outcomes)
      return
    }
    for (const option of request.options) {
      const cents = prices[option.kind]
      if (cents === undefined || (won && option.kind !== won)) continue
      const multiple = cents / option.listPriceCents
      this.demand.learn(this.demand.keys(request, option.kind), offset, multiple, won !== null)
      if (won) this.tally.multiples += multiple
    }
  }

  // --------------------------------------------------------------------------------------------------- the gig

  gig(need: GigNeed, books: Books): GigPlan[] {
    const { order, legs, previous } = need
    const request = books.requests.get(order.id)
    if (!request) throw new Error(`no request for order ${order.id}`)
    const now = books.now
    const typical = (stops: readonly StopRef[]) => this.typicalOf(stops, books)
    if (need.why === 'urgent' && previous) {
      const gigId = books.gigsOf(order.id).find((id) => books.posts.get(id) === previous)
      // A gig that a driver gave back starts again from the fee that booked it, not from the fee of the hours since.
      const cents = gigId ? (this.dropped.get(gigId) ?? feeAt(this.schedules.get(gigId) ?? previous.schedule, now)) : 0
      const unit = typical(previous.stops)
      const schedule = this.fees(order, unit, now, cents / unit, true)
      return [{ stops: previous.stops, audience: previous.audience, schedule }]
    }
    const facts = readNote(request.note, request.arrivedAt)
    const shapes = gigShape(order, legs, facts, this.retryOf(order.id, legs), now, this.context())
    if (shapes.length === 0) throw new Error(`cannot read order ${order.id}`)
    const floor = this.floors.get(order.id) ?? 0
    return shapes.map(({ stops, audience }) => ({
      stops,
      audience,
      schedule: this.fees(order, typical(stops), now, floor),
    }))
  }

  /** The schedule of a gig from now, never under `shown` × `typical` (the fee the car showed before): a climb for a
   * car that is late already, the urgent climb when the gig is warned, has no time left to book or was posted after
   * its planning time, and the stepped schedule otherwise. */
  private fees(order: Order, typical: number, now: number, shown: number, warned = false): FeeStep[] {
    const guarded = this.guarded(now)
    const p = guarded
      ? {
          ...this.params,
          urgentTop: Math.max(this.params.urgentTop, GUARD_URGENT),
          lateTop: Math.max(this.params.lateTop, GUARD_LATE),
        }
      : this.params
    if (now > order.lastPickupAt && p.lateRestart > 0)
      return stepped(now, typical, laterPickup(order.lastPickupAt, now), 0, order.id, {
        open: p.lateRestart,
        early: 0,
        raises: [
          [p.raiseAt1, Math.max(p.raise1, p.lateRestart)],
          [p.raiseAt2, Math.max(p.raise2, p.lateRestart)],
          [p.raiseAt3, Math.max(p.raise3, p.lateRestart)],
        ],
        top: Math.max(p.urgentTop, p.lateRestart),
        jitter: p.jitter,
        rest: p.rest,
      })
    if (now > order.lastPickupAt)
      return fast(now, typical, Math.max(shown, p.lateFrom), p.lateStep, p.lateEvery, Math.max(p.lateTop, shown))
    const urgent = warned || awake(now, order.lastPickupAt - BOOK_AHEAD) < SHORT
    if (urgent && this.rescueOn) {
      const open = Math.max(shown + URGENT_RAISE, RESCUE_OPEN)
      return fast(now, typical, open, RESCUE_STEP, RESCUE_EVERY, Math.max(RESCUE_TOP, open))
    }
    if (urgent || awake(now, planBy(now, order.lastPickupAt)) < p.lateWithin) {
      const open = Math.max(shown + URGENT_RAISE, urgent ? p.urgentOpen : p.lateOpen)
      return fast(now, typical, open, p.urgentStep, p.urgentEvery, Math.max(p.urgentTop, open))
    }
    return stepped(now, typical, order.lastPickupAt, shown, order.id, {
      open: p.open,
      early: p.early,
      raises: [
        [p.raiseAt1, p.raise1],
        [p.raiseAt2, p.raise2],
        [p.raiseAt3, p.raise3],
      ],
      top: p.urgentTop,
      jitter: p.jitter,
      rest: p.rest,
    })
  }

  private retryOf(orderId: string, legs: readonly number[]): Retry {
    return legs
      .map((leg) => this.retries.get(`${orderId} ${leg}`) ?? FIRST_TRY)
      .reduce((a, b) => ({
        pickupFrom: Math.max(a.pickupFrom, b.pickupFrom),
        manualLicence: a.manualLicence || b.manualLicence,
        plates: a.plates || b.plates,
        late: a.late || b.late,
      }))
  }

  private setback(orderId: string, leg: number, reason: Setback, at: number, books: Books): void {
    const order = this.orders.get(orderId)
    if (!order) return
    const key = `${orderId} ${leg}`
    this.retries.set(key, retryAfter(reason, order, books.requests.get(orderId), leg, at, this.retries.get(key)))
  }

  /** A gig that a driver gave back shows the fee of the hours it was held. It takes a new schedule from the fee
   * that booked it. The entry goes when the world has the new schedule (`sent`), so a rebuilt week has the same
   * entries; a car past its deadline warning gets its schedule from `gig`. */
  tick(books: Books): Action[] {
    const actions: Action[] = []
    for (const [gigId, fee] of this.dropped) {
      const post = books.posts.get(gigId)
      const order = post && books.orders.get(post.stops[0]?.orderId ?? '')
      const open = order && !books.booked.has(gigId) && books.gigsOf(order.id).includes(gigId)
      if (!post || !order || !open || books.urgent.has(order.id)) {
        this.dropped.delete(gigId)
        continue
      }
      const unit = this.typicalOf(post.stops, books)
      actions.push({ type: 'reprice', gigId, schedule: this.fees(order, unit, books.now, fee / unit) })
    }
    // The rescue: each warned car that waits for a driver gets the rescue's climb, once.
    if (this.rescuing(books))
      for (const id of books.urgent) {
        const order = books.orders.get(id)
        if (!order || books.now > order.lastPickupAt || !order.deliveredAt.some((at) => at === null)) continue
        for (const gigId of books.gigsOf(id)) {
          const post = books.posts.get(gigId)
          if (!post || books.booked.has(gigId) || this.rescued.has(gigId) || this.dropped.has(gigId)) continue
          this.rescued.add(gigId)
          const unit = this.typicalOf(post.stops, books)
          const shown = feeAt(this.schedules.get(gigId) ?? post.schedule, books.now) / unit
          actions.push({ type: 'reprice', gigId, schedule: this.fees(order, unit, books.now, shown, true) })
        }
      }
    actions.push(...this.roomRises(books))
    actions.push(...this.lateRestarts(books))
    return [...actions, ...this.planner.actions(books)]
  }

  /** The restart of the cars that missed their last pickup (`lateRestart`): the single gig of such an order, which
   * no driver can book before one of its windows ends, is taken out and posted again with windows that run to the
   * end of the world and the schedule of a late car (`fees`). Once for each order; a gig that has such a window
   * already is left, so a rebuilt week does not post it twice. A private pickup has its slot only. */
  private lateRestarts(books: Books): Action[] {
    if (!(this.params.lateRestart > 0)) return []
    const now = books.now
    const actions: Action[] = []
    for (const order of books.orders.values()) {
      if (now <= order.lastPickupAt || this.restarted.has(order.id) || this.picked.has(order.id)) continue
      const leg = order.legs[0]
      if (order.legs.length !== 1 || !leg || leg.pickup.privateAddress || order.deliveredAt[0] !== null) continue
      const [gigId, ...more] = books.gigsOf(order.id)
      const post = gigId ? books.posts.get(gigId) : undefined
      if (!gigId || !post || more.length > 0 || books.booked.has(gigId) || pickups(post.stops).length !== 1) continue
      this.restarted.add(order.id)
      if (post.stops.some((stop) => stop.kind === 'delivery' && (stop.window?.to ?? 0) >= books.endsAt)) continue
      const request = books.requests.get(order.id)
      if (!request) continue
      const facts = readNote(request.note, request.arrivedAt)
      const retry = { ...this.retryOf(order.id, [0]), late: true }
      const [shape] = gigShape(order, [0], facts, retry, now, this.context())
      if (!shape || pickups(shape.stops).length !== 1) continue
      const stops = shape.stops.map((stop) =>
        stop.window ? stop : { ...stop, window: { from: now, to: books.endsAt } },
      )
      const schedule = this.fees(order, this.typicalOf(stops, books), now, 0)
      actions.push({ type: 'withdraw', gigId }, { type: 'post', stops, audience: shape.audience, schedule })
    }
    this.tally.restarts += actions.length / 2
    return actions
  }

  /** The rises of the room for late orders (`room`): a new schedule, from a higher fee, for each single gig of an
   * order at risk. */
  private roomRises(books: Books): Action[] {
    const now = books.now
    const [day, minute] = [Math.floor(now / DAY), now % DAY]
    if (!(this.params.room > 0) || now < ROOM_FROM || day % 7 === ROOM_REST) return []
    if (minute < ROOM_WAKE || minute >= ROOM_SLEEP || now - this.roomAt < (day % 7 === 5 ? 60 : 30)) return []
    let late = this.late.size
    let risk = 0
    const raise: Order[] = []
    for (const order of books.orders.values()) {
      if (this.late.has(order.id) || !order.deliveredAt.some((at) => at === null) || this.picked.has(order.id)) continue
      // A car that nobody has collected by its last pickup is late.
      if (now > order.lastPickupAt) late++
      else if (!books.gigsOf(order.id).some((gigId) => books.booked.has(gigId))) {
        const long = (books.requests.get(order.id)?.referenceFeeCents ?? 0) >= ROOM_LONG
        const early = order.lastPickupAt % DAY < ROOM_EARLY
        const chance = long
          ? early
            ? ROOM_RISK.longEarly
            : ROOM_RISK.longLate
          : early
            ? ROOM_RISK.shortEarly
            : ROOM_RISK.shortLate
        risk += chance
        if (chance >= ROOM_RAISE) raise.push(order)
      }
    }
    const room = Math.floor(books.orders.size / 10) - late
    if (this.params.room * risk <= room) return []
    this.roomAt = now
    const actions: Action[] = []
    for (const order of raise)
      for (const gigId of books.gigsOf(order.id)) {
        const post = books.posts.get(gigId)
        // A chain keeps its own schedule (planner.ts): one driver for its cars is the cheapest way to be on time.
        if (!post || books.booked.has(gigId) || pickups(post.stops).length !== 1) continue
        const unit = this.typicalOf(post.stops, books)
        const shown = feeAt(this.schedules.get(gigId) ?? post.schedule, now) / unit
        if (shown >= ROOM_TOP) continue
        const from = Math.min(ROOM_TOP, Math.max(shown + ROOM_STEP, ROOM_OPEN))
        actions.push({ type: 'reprice', gigId, schedule: this.fees(order, unit, now, from) })
      }
    if (actions.length > 0) {
      if (this.roomTally.rises++ === 0)
        this.roomTally.first = `room for ${room} late orders with ${risk.toFixed(1)} expected of the orders without a driver`
      this.roomTally.gigs += actions.length
    }
    return actions
  }

  override hold(need: GigNeed, books: Books): boolean {
    return this.planner.hold(need, books)
  }

  /** The typical fees of a gig's cars as single gigs, summed. */
  private singlesOf(stops: readonly StopRef[], books: Books): number {
    let sum = 0
    for (const stop of pickups(stops)) {
      const request = books.requests.get(stop.orderId)
      if (request)
        sum += request.referenceFeeCents / (this.orders.get(stop.orderId)?.legs.length ?? request.legs.length)
    }
    return sum
  }

  /** The unit of a gig's fee schedule: what a chain is worth to its driver, or the cars' typical fees. */
  private typicalOf(stops: readonly StopRef[], books: Books): number {
    return this.planner.typical(stops) ?? this.singlesOf(stops, books)
  }

  // ------------------------------------------------------------------------------------------------- the books

  override observe(event: DeskEvent, books: Books): void {
    switch (event.kind) {
      case 'gig_viewed':
        this.planner.viewed(event.gigId, event.driverId, event.at)
        break
      case 'offer_answered':
        if (event.answer === 'accepted') this.planner.took(event.gigId)
        break
      case 'price_request':
        this.tally.requests++
        this.demand.dawn(Math.floor(event.at / DAY))
        break
      case 'order_won': {
        const { order } = event
        this.orders.set(order.id, order)
        this.planner.won(order.id, event.at)
        const request = books.requests.get(order.id)
        const leg = order.legs[0]
        if (request && leg) {
          const ready = leg.pickup.window.from
          const view = this.view(request, order.deadline, order.lastPickupAt, ready, event.at, 0)
          const today = goesToday(order.lastPickupAt, event.at)
          this.wonAs.set(order.id, {
            keys: this.supply.keys(leg.pickup.placeId, leg.delivery.placeId, today),
            expected: view?.cost ?? 1,
          })
        }
        this.outcome(order.id, order.option, event.at, books)
        break
      }
      case 'order_changed':
        this.orders.set(event.order.id, event.order)
        break
      case 'order_lost':
        this.outcome(event.requestId, null, event.at, books)
        break
      case 'gig_booked': {
        this.dropped.delete(event.gigId)
        this.bookedAt.set(event.gigId, event.feeCents)
        const post = books.posts.get(event.gigId)
        const singles = post ? this.singlesOf(post.stops, books) : 0
        if (!post || !(singles > 0)) break
        this.planner.booked(event.gigId, event.feeCents / singles)
        const ratio = clamp(event.feeCents / singles, BOOKED_LOW, BOOKED_HIGH)
        // The supply learns what the order model did not expect of each car, with the effects it had at its win.
        for (const stop of pickups(post.stops)) {
          const won = this.wonAs.get(stop.orderId)
          if (won) this.supply.learn(won.keys, ratio / won.expected)
        }
        this.tally.bookings++
        this.tally.ratios += ratio
        break
      }
      case 'gig_dropped':
      case 'no_show':
        if (event.kind === 'gig_dropped' && event.at % DAY < GUARD_HOUR) this.troubles.push(event.at)
        this.dropped.set(event.gigId, this.bookedAt.get(event.gigId) ?? 0)
        break
      case 'picked_up':
        this.picked.add(event.orderId)
        break
      case 'visit_failed':
        this.setback(event.orderId, event.leg, event.reason, event.at, books)
        break
      case 'gig_expired': {
        const post = books.posts.get(event.gigId)
        this.planner.expired(event.gigId, post?.stops ?? [])
        const shown = feeAt(this.schedules.get(event.gigId) ?? post?.schedule ?? [], event.at)
        for (const stop of pickups(post?.stops ?? [])) {
          this.setback(stop.orderId, stop.leg, 'expired', event.at, books)
          this.floors.set(stop.orderId, shown / this.typicalOf(post?.stops ?? [], books))
        }
        break
      }
      case 'forecast':
        this.forecasts.push({ from: event.from, to: event.to, placeIds: event.placeIds })
        break
      case 'ledger': {
        const { kind, orderId } = event.line
        if (!orderId) break
        if (kind === 'late_refund' || kind === 'undelivered_penalty') this.late.add(orderId)
        const dealerId = books.requests.get(orderId)?.dealerId
        if (kind === 'revenue' && dealerId) {
          this.done++
          this.delivered.set(dealerId, [...(this.delivered.get(dealerId) ?? []), orderId])
        }
        break
      }
    }
  }

  override sent(action: Action, result: ActionResult, books: Books): void {
    this.planner.sent(action, result, books)
    if (!result.ok) return
    if (action.type === 'quote') {
      const dealerId = books.requests.get(action.requestId)?.dealerId
      this.pending.set(action.requestId, { prices: action.prices, offset: dealerId ? this.trustOffset(dealerId) : 0 })
      this.tally.quoted++
    } else if (action.type === 'post') this.schedules.set(result.id, action.schedule)
    else if (action.type === 'reprice') {
      this.schedules.set(action.gigId, action.schedule)
      this.dropped.delete(action.gigId)
    }
  }

  override summary(): string {
    const t = this.tally
    const share = t.requests > 0 ? (100 * t.won) / t.requests : 0
    const multiple = t.won > 0 ? t.multiples / t.won : 0
    const paid = t.bookings > 0 ? t.ratios / t.bookings : 0
    return `lean: won ${t.won} of ${t.requests} requests (${share.toFixed(1)}%) at ${multiple.toFixed(2)} × list, ${t.bookings} bookings at ${paid.toFixed(2)} × typical, ${this.late.size} late of ${this.done} done. ${this.planner.summary()}${this.rescueOn ? ` Rescue: on, ${this.rescued.size} warned gigs repriced.` : ''}${this.roomTally.rises > 0 ? ` Room: ${this.roomTally.rises} rises of ${(this.roomTally.gigs / this.roomTally.rises).toFixed(0)} gigs each (at the first, ${this.roomTally.first}).` : ''}${t.restarts > 0 ? ` Late restarts: ${t.restarts}.` : ''}${t.pairs > 0 ? ` Pairs: ${t.pairs} options priced with a chain partner, saving €${(t.pairCents / t.pairs / 100).toFixed(0)} each.` : ''}`
  }

  private context(tightening = 1): Context {
    return { map: this.setup.map, level: this.setup.level, forecasts: this.forecasts, tightening }
  }
}

export const lean: StrategyKind<LeanParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Lean(setup, params),
}
