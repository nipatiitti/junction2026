/** Thompson: pricing as a contextual bandit. Arms are multiples of the list price on a grid; a context is the
 * dealer's trust bucket x option x whether the delivery goes to the capital region. Each arm keeps a Beta posterior
 * of its win chance, started from the measured flip quantiles. A request answers with a threshold, so a win at m
 * counts as a win for every arm at or under m and a loss for every arm at or over m. The arm and option are chosen
 * by Thompson sampling of (price - cost) x win chance, with a seeded generator so a week repeats. */
import type { DeliveryOption, DeskEvent, FeeStep, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { canServe } from '../../ops/index.ts'
import { type Books, type GigNeed, type GigPlan, type Prices, Strategy, type StrategyKind } from '../../strategy.ts'
import { HOUR } from '../../time.ts'
import { starterGig } from '../starter/gig.ts'

export type ThompsonParams = {
  seed: number
  gridLo: number
  gridHi: number
  gridStep: number
  /** Pseudo-observations of the prior on each arm. */
  priorN: number
  /** Scale on the flip quantiles for a delivery into the capital region, and elsewhere. */
  capitalScale: number
  otherScale: number
  /** Scale on the flip quantiles for each option. */
  sameDayScale: number
  nextDayScale: number
  threeDayScale: number
  /** Flip scale gained per trust point, and its cap in points. */
  trustSlope: number
  trustCap: number
  /** Trust bucket edges. */
  trustMid: number
  trustHigh: number
  /** Weight that each day's observations keep when the day turns. */
  dayDecay: number
  /** Expected driver cost over the typical fee, and the premium extra. */
  costMult: number
  premiumCost: number
  /** Least expected margin in euros cents to quote at all. */
  minValueCents: number
  /** Fee schedule: opening and top multiple of the typical fee, steps, minutes between steps. */
  feeOpen: number
  feeTop: number
  feeSteps: number
  feeStepMinutes: number
  repostOpen: number
  premiumFee: number
}

const DEFAULTS: ThompsonParams = {
  seed: 1,
  gridLo: 0.95,
  gridHi: 2.0,
  gridStep: 0.05,
  priorN: 4,
  capitalScale: 0.9,
  otherScale: 1.06,
  sameDayScale: 1.08,
  nextDayScale: 1.0,
  threeDayScale: 0.92,
  trustSlope: 0.025,
  trustCap: 16,
  trustMid: 5,
  trustHigh: 15,
  dayDecay: 0.6,
  costMult: 1.25,
  premiumCost: 1.25,
  minValueCents: 300,
  feeOpen: 1.0,
  feeTop: 1.45,
  feeSteps: 8,
  feeStepMinutes: 60,
  repostOpen: 1.2,
  premiumFee: 1.3,
}

const CAPITAL = new Set(['helsinki', 'espoo', 'vantaa', 'hyvinkää', 'hyvinkaa', 'kauniainen'])

/** Flip quantiles over list at trust 0 (src/BRIEF.md finding 3): [multiple, share of flips under it]. */
const FLIPS: [number, number][] = [
  [0.7, 0],
  [0.98, 0.1],
  [1.15, 0.25],
  [1.29, 0.5],
  [1.46, 0.75],
  [1.62, 0.9],
  [1.95, 0.99],
  [2.5, 1],
]

/** Chance that the flip lies above m (the quote wins). */
function winPrior(m: number): number {
  if (m <= FLIPS[0]![0]) return 0.995
  for (let i = 1; i < FLIPS.length; i++) {
    const [x1, y1] = FLIPS[i]!
    const [x0, y0] = FLIPS[i - 1]!
    if (m <= x1) return Math.min(0.995, Math.max(0.005, 1 - (y0 + ((m - x0) / (x1 - x0)) * (y1 - y0))))
  }
  return 0.005
}

/** A small seeded generator (mulberry32). */
function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}

function normal(rand: () => number): number {
  const u = Math.max(1e-12, rand())
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rand())
}

/** Gamma(shape, 1) by Marsaglia and Tsang. */
function gamma(shape: number, rand: () => number): number {
  if (shape < 1) return gamma(shape + 1, rand) * rand() ** (1 / shape)
  const d = shape - 1 / 3
  const c = 1 / Math.sqrt(9 * d)
  for (;;) {
    const x = normal(rand)
    const v = (1 + c * x) ** 3
    if (v <= 0) continue
    const u = rand()
    if (Math.log(u) < 0.5 * x * x + d - d * v + d * Math.log(v)) return d * v
  }
}

const beta = (a: number, b: number, rand: () => number): number => {
  const x = gamma(a, rand)
  return x / (x + gamma(b, rand))
}

type Arms = { wins: number[]; losses: number[] }
type Quoted = { context: string; m: number }

class Thompson extends Strategy<ThompsonParams> {
  private readonly grid: number[] = []
  private readonly arms = new Map<string, Arms>()
  private readonly quoted = new Map<string, Quoted>()
  private readonly trust = new Map<string, number>()
  private readonly delivered = new Map<string, number>()
  private readonly placeName = new Map<string, string>()
  private day = -1
  private wins = 0
  private losses = 0

  constructor(setup: ThompsonStrategySetup, params: ThompsonParams) {
    super(setup, params)
    const { gridLo, gridHi, gridStep } = params
    for (let m = gridLo; m <= gridHi + 1e-9; m += gridStep) this.grid.push(Math.round(m * 1000) / 1000)
    for (const place of setup.map.places) this.placeName.set(place.id, place.name.toLowerCase())
  }

  private capital(request: PriceRequest): boolean {
    const id = request.legs[0]?.delivery.placeId
    return id !== undefined && CAPITAL.has(this.placeName.get(id) ?? '')
  }

  private trustOf(dealer: string): number {
    return this.trust.get(dealer) ?? 0
  }

  private bucket(trust: number): number {
    return trust >= this.params.trustHigh ? 2 : trust >= this.params.trustMid ? 1 : 0
  }

  private armsOf(context: string): Arms {
    let arms = this.arms.get(context)
    if (!arms) {
      arms = { wins: this.grid.map(() => 0), losses: this.grid.map(() => 0) }
      this.arms.set(context, arms)
    }
    return arms
  }

  private optionScale(kind: DeliveryOption['kind']): number {
    const p = this.params
    return kind === 'same_day' ? p.sameDayScale : kind === 'next_day' ? p.nextDayScale : p.threeDayScale
  }

  private newDay(now: number): void {
    const day = Math.floor(now / (24 * HOUR))
    if (day === this.day) return
    if (this.day >= 0) {
      for (const arms of this.arms.values()) {
        for (let i = 0; i < this.grid.length; i++) {
          arms.wins[i]! *= this.params.dayDecay
          arms.losses[i]! *= this.params.dayDecay
        }
      }
    }
    this.day = day
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    const p = this.params
    this.newDay(books.now)
    const rand = rng(hash(`${p.seed}:${request.id}`))
    const trust = this.trustOf(request.dealerId)
    const capital = this.capital(request)
    const trustScale = 1 + p.trustSlope * Math.min(trust, p.trustCap)
    const premium = request.legs.some((leg) => leg.car.premium)
    const cost = request.referenceFeeCents * p.costMult * (premium ? p.premiumCost : 1)
    let best: { kind: DeliveryOption['kind']; price: number; sampled: number; mean: number; quoted: Quoted } | null =
      null
    for (const option of request.options) {
      if (!canServe(request, option, books.now, { map: this.setup.map, level: this.setup.level }).ok) continue
      const scale = trustScale * (capital ? p.capitalScale : p.otherScale) * this.optionScale(option.kind)
      const context = `${this.bucket(trust)}|${option.kind}|${capital ? 'c' : 'o'}`
      const arms = this.armsOf(context)
      for (let i = 0; i < this.grid.length; i++) {
        const m = this.grid[i]!
        const prior = winPrior(m / scale)
        const a = p.priorN * prior + arms.wins[i]!
        const b = p.priorN * (1 - prior) + arms.losses[i]!
        const price = Math.round(option.listPriceCents * m)
        const sampled = (price - cost) * beta(a, b, rand)
        if (!best || sampled > best.sampled) {
          const mean = (price - cost) * (a / (a + b))
          best = { kind: option.kind, price, sampled, mean, quoted: { context, m } }
        }
      }
    }
    if (!best || best.mean < p.minValueCents || best.sampled <= 0) return null
    this.quoted.set(request.id, best.quoted)
    return { [best.kind]: best.price }
  }

  observe(event: DeskEvent, books: Books): void {
    if (event.kind === 'order_won') this.learn(event.order.id, true)
    else if (event.kind === 'order_lost') this.learn(event.requestId, false)
    else if (event.kind === 'delivered') {
      const order = books.orders.get(event.orderId)
      if (!order) return
      const count = (this.delivered.get(order.id) ?? 0) + 1
      this.delivered.set(order.id, count)
      if (count < order.legs.length) return
      const trust = this.trustOf(order.dealerId)
      this.trust.set(order.dealerId, event.at <= order.deadline ? Math.min(25, trust + 1) : Math.floor(trust / 2))
    }
  }

  /** A threshold: a win at m wins every arm at or under m; a loss loses every arm at or over m. */
  private learn(requestId: string, won: boolean): void {
    const quoted = this.quoted.get(requestId)
    if (!quoted) return
    this.quoted.delete(requestId)
    const arms = this.armsOf(quoted.context)
    if (won) this.wins++
    else this.losses++
    for (let i = 0; i < this.grid.length; i++) {
      const m = this.grid[i]!
      if (won && m <= quoted.m + 1e-9) arms.wins[i]! += 1
      if (!won && m >= quoted.m - 1e-9) arms.losses[i]! += 1
    }
  }

  gig(need: GigNeed, books: Books): GigPlan {
    const plan = starterGig(need, books, this.setup.level)
    const { order } = need
    if (books.urgent.has(order.id) || need.why === 'urgent') return plan
    const p = this.params
    const request = books.requests.get(order.id)!
    const premium = order.legs.some((leg) => leg.car.premium)
    const fee = ((request.referenceFeeCents * need.legs.length) / order.legs.length) * (premium ? p.premiumFee : 1)
    const open = need.previous || need.why === 'retry' ? Math.max(p.repostOpen, p.feeOpen) : p.feeOpen
    const top = Math.max(open, p.feeTop)
    const steps = Math.max(1, Math.min(48, Math.round(p.feeSteps)))
    const schedule: FeeStep[] = []
    for (let k = 0; k < steps; k++) {
      const mult = steps === 1 ? open : open + ((top - open) * k) / (steps - 1)
      schedule.push({ at: books.now + k * p.feeStepMinutes, feeCents: Math.max(1, Math.round(fee * mult)) })
    }
    return { ...plan, schedule }
  }

  summary(): string {
    return `thompson: ${this.wins} wins, ${this.losses} losses learned, ${this.arms.size} contexts`
  }
}

type ThompsonStrategySetup = ConstructorParameters<typeof Strategy>[0]

export const thompson: StrategyKind<ThompsonParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Thompson(setup, params),
}
