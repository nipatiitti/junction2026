/** haggle: a bazaar haggler who remembers every face. A pure feedback controller, no statistical model.
 *
 * Price of an option = list x exp(dealer level + option offset + region offset), floored at cost plus a margin.
 * After a win the dealer's level steps up by `up`; after a loss it steps down by `down`. The level drifts until
 * the expected step is zero: w*up = (1-w)*down, so it settles at the win rate w = down/(up+down). We pick w as
 * the win rate that maximises (price - cost) x W(price) and derive `down = up * w/(1-w)`.
 * Unseen dealers start from the pooled level, which every win and loss also moves.
 * Fees: open near the typical fee, rise linearly towards the last pickup, steep after the deadline warning. */
import type { DeskEvent, Order, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import {
  type Context,
  canServe,
  FIRST_TRY,
  gigShape,
  type Retry,
  readNote,
  retryAfter,
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

export type HaggleParams = {
  /** Starting price level, as a multiple of list, for the pool (and so every new dealer). */
  startMult: number
  /** Win rate the controller settles at: down/(up+down). */
  targetWin: number
  /** Log step up after a win, at the start of a dealer's history. */
  stepStart: number
  /** Log step up after a win, once the dealer has many results. */
  stepMin: number
  /** Results over which the step decays from stepStart to stepMin. */
  stepDecay: number
  /** Option and region offsets move by this share of the dealer's step. */
  offsetGain: number
  /** Offsets stay within +-this (log). */
  offsetCap: number
  /** The pool moves by this share of a dealer's step on every result. */
  poolGain: number
  /** Level bounds, as multiples of list. */
  minMult: number
  maxMult: number
  /** Estimated driver fee we really pay, as a multiple of the typical fee. */
  costMult: number
  /** Never quote under cost x (1 + minMargin) ... */
  minMargin: number
  /** ... nor under cost + this many cents. */
  minMarginCents: number
  /** Quote every servable option (false: only pickOption's comfortable option and slower ones). */
  allOptions: boolean
  /** Fee schedule: opening multiple of typical, the multiple reached `riseLeadMin` before the last pickup. */
  feeOpen: number
  feeTop: number
  riseLeadMin: number
  /** A repost opens this much higher (multiple of typical). */
  repostBump: number
  /** After the deadline warning: from urgentOpen up to urgentTop, in 30-minute steps. */
  urgentOpen: number
  urgentTop: number
  /** A premium car's fee multiple (fewer experienced drivers). */
  premiumMult: number
}

type Kind = PriceRequest['options'][number]['kind']

class Haggle extends Strategy<HaggleParams> {
  override readonly every = 30
  private pool: number
  private readonly dealer = new Map<string, { level: number; n: number }>()
  private readonly option = new Map<Kind, number>()
  private readonly region = new Map<string, number>()
  private readonly retries = new Map<string, Retry>()
  private readonly forecasts: Snowfall[] = []
  private wins = 0
  private losses = 0

  constructor(setup: Setup, params: HaggleParams) {
    super(setup, params)
    this.pool = Math.log(params.startMult)
  }

  private get down(): number {
    const w = Math.min(0.9, Math.max(0.05, this.params.targetWin))
    return w / (1 - w)
  }

  private context(): Context {
    return { map: this.setup.map, level: this.setup.level, forecasts: this.forecasts }
  }

  private regionOf(request: PriceRequest): string {
    return request.legs[0]?.delivery.placeId ?? '?'
  }

  private levelOf(dealerId: string): { level: number; n: number } {
    let d = this.dealer.get(dealerId)
    if (!d) {
      d = { level: this.pool, n: 0 }
      this.dealer.set(dealerId, d)
    }
    return d
  }

  private step(n: number): number {
    const p = this.params
    return p.stepMin + (p.stepStart - p.stepMin) * Math.exp(-n / Math.max(1, p.stepDecay))
  }

  /** One result: +1 for a win (with the option taken), -1 for a loss. */
  private learn(request: PriceRequest, won: boolean, taken?: Kind): void {
    const p = this.params
    const d = this.levelOf(request.dealerId)
    const s = this.step(d.n)
    const move = won ? s : -s * this.down
    const lo = Math.log(p.minMult)
    const hi = Math.log(p.maxMult)
    const clip = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x))
    d.level = clip(d.level + move, lo, hi)
    d.n++
    this.pool = clip(this.pool + move * p.poolGain, lo, hi)
    const off = move * p.offsetGain
    const region = this.regionOf(request)
    this.region.set(region, clip((this.region.get(region) ?? 0) + off, -p.offsetCap, p.offsetCap))
    if (won && taken) this.option.set(taken, clip((this.option.get(taken) ?? 0) + off, -p.offsetCap, p.offsetCap))
    if (!won)
      for (const o of request.options)
        this.option.set(o.kind, clip((this.option.get(o.kind) ?? 0) + off, -p.offsetCap, p.offsetCap))
    if (won) this.wins++
    else this.losses++
  }

  override observe(event: DeskEvent, books: Books): void {
    if (event.kind === 'order_won') {
      const request = books.requests.get(event.order.id)
      if (request) this.learn(request, true, event.order.option)
    } else if (event.kind === 'order_lost') {
      const request = books.requests.get(event.requestId)
      if (request) this.learn(request, false)
    } else if (event.kind === 'forecast') {
      this.forecasts.push(event)
    }
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const p = this.params
    const context = this.context()
    const servable = request.options.filter((o) => canServe(request, o, books.now, context).ok)
    if (servable.length === 0) return null
    const pick = pickOption(request, books.now, context)
    const from = pick ? servable.findIndex((o) => o.kind === pick.kind) : -1
    const chosen = p.allOptions || from < 0 ? servable : servable.slice(from)
    const d = this.levelOf(request.dealerId)
    const region = this.region.get(this.regionOf(request)) ?? 0
    const cost = request.referenceFeeCents * p.costMult * (request.legs.some((l) => l.car.premium) ? p.premiumMult : 1)
    const floor = Math.max(cost * (1 + p.minMargin), cost + p.minMarginCents)
    const prices: Prices = {}
    for (const o of chosen) {
      const mult = Math.exp(d.level + region + (this.option.get(o.kind) ?? 0))
      prices[o.kind] = Math.round(Math.max(floor, o.listPriceCents * mult))
    }
    return prices
  }

  gig(need: GigNeed, books: Books): GigPlan | GigPlan[] {
    const p = this.params
    const { order } = need
    const request = books.requests.get(order.id)
    const facts = readNote(request?.note ?? null, request?.arrivedAt ?? books.now)
    let retry = this.retries.get(order.id) ?? FIRST_TRY
    if (need.why === 'retry' && need.failed)
      retry = retryAfter(need.failed, order, request, need.legs[0] ?? 0, books.now, retry)
    if (need.why === 'repost') retry = retryAfter('expired', order, request, need.legs[0] ?? 0, books.now, retry)
    this.retries.set(order.id, retry)
    const shapes = gigShape(order, need.legs, facts, retry, books.now, this.context())
    const typical = request?.referenceFeeCents ?? 10000
    return shapes.map((shape) => {
      const cars = shape.stops.filter((s) => s.kind === 'pickup').length
      const premium = shape.audience.experienced ? p.premiumMult : 1
      const fee = ((typical * cars) / Math.max(1, order.legs.length)) * premium
      const urgent = books.urgent.has(order.id) || need.why === 'urgent'
      return { ...shape, schedule: this.schedule(order, fee, books.now, urgent, need.why === 'repost') }
    })
  }

  private schedule(order: Order, fee: number, now: number, urgent: boolean, repost: boolean) {
    const p = this.params
    if (urgent) {
      const steps = 5
      return Array.from({ length: steps }, (_, k) => ({
        at: now + k * 30,
        feeCents: Math.max(1, Math.round(fee * (p.urgentOpen + ((p.urgentTop - p.urgentOpen) * k) / (steps - 1)))),
      }))
    }
    const open = p.feeOpen + (repost ? p.repostBump : 0)
    const top = Math.max(open, p.feeTop)
    const end = order.lastPickupAt - p.riseLeadMin
    const horizon = end - now
    if (!Number.isFinite(horizon) || horizon <= 60) return [{ at: now, feeCents: Math.round(fee * top) }]
    const steps = Math.min(24, Math.max(2, Math.floor(horizon / 60)))
    const gap = Math.floor(horizon / steps)
    return Array.from({ length: steps + 1 }, (_, k) => ({
      at: now + k * gap,
      feeCents: Math.max(1, Math.round(fee * (open + ((top - open) * k) / steps))),
    }))
  }

  override summary(): string {
    const top = [...this.dealer.entries()]
      .sort((a, b) => b[1].n - a[1].n)
      .slice(0, 5)
      .map(([id, d]) => `${id}:${Math.exp(d.level).toFixed(2)}`)
      .join(' ')
    return `haggle wins ${this.wins} losses ${this.losses} pool ${Math.exp(this.pool).toFixed(2)} ${top}`
  }
}

export const haggle: StrategyKind<HaggleParams> = {
  defaults: {
    startMult: 1.3,
    targetWin: 0.3,
    stepStart: 0.08,
    stepMin: 0.03,
    stepDecay: 15,
    offsetGain: 0.3,
    offsetCap: 0.25,
    poolGain: 0.3,
    minMult: 0.9,
    maxMult: 2.2,
    costMult: 1.25,
    minMargin: 0.25,
    minMarginCents: 1500,
    allOptions: false,
    feeOpen: 1.1,
    feeTop: 1.8,
    riseLeadMin: 240,
    repostBump: 0.2,
    urgentOpen: 1.6,
    urgentTop: 2.6,
    premiumMult: 1.2,
  },
  build: (setup, params) => new Haggle(setup, params),
}
