/** shadow: tails the competitor. A grid filter over today's competitor level (price / list), updated by every win
 * (the flip was above our price) and loss (below), with a per-place and per-dealer offset; the first requests of
 * each morning are probes at spread-out prices. Quotes maximise the expected margin under that belief. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  FeeStep,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import { DAY, HOUR, pickOption } from '../../ops/index.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import { starterGig } from '../starter/gig.ts'

export type ShadowParams = {
  priorLevel: number // prior mean of the competitor's level (flip / list)
  priorSd: number // prior log sd of the level
  scatter: number // log sd of a single request's flip around the level
  reset: number // share of the prior mixed in each morning
  widen: number // log sd of the overnight drift of yesterday's belief
  capitalMult: number // flip multiple for deliveries to the capital region
  otherMult: number // flip multiple for other towns
  placeLr: number // learning rate of the per-place (outage) offset, per day
  dealerLr: number // learning rate of the per-dealer offset
  undercut: number // dealer offset cut next morning when we won most of its requests
  trustPer: number // flip rise per on-time order of a dealer
  trustCap: number // orders that count for trust
  probes: number // probe requests each morning
  probeLow: number // lowest probe multiple of the belief
  probeHigh: number // highest probe multiple of the belief
  shade: number // multiple applied to the best price
  costMult: number // cost of a car as a multiple of the typical fee
  minMargin: number // minimum margin over cost, as a share of cost
  warDrop: number // a day level under this share of the previous day's is a war day
  warDecline: boolean // on a war day, decline instead of following
  winCap: number // highest share of a dealer's requests to win in a day (1 = no cap)
  capRaise: number // price multiple once a dealer is over its cap
  feeOpen: number // opening driver fee, as a multiple of the typical fee
  feeRise: number // fee rise per hour, as a multiple of the typical fee
  feeMax: number // highest driver fee multiple
  feeSteps: number // hourly steps in the fee schedule
}

const CAPITAL = ['helsinki', 'espoo', 'vantaa', 'hyvinkää', 'hyvinkaa', 'kauniainen']
const GRID: number[] = Array.from({ length: 121 }, (_, i) => 0.7 + i * 0.01 * 1.2) // 0.70 .. 2.14

const phi = (z: number): number => {
  // standard normal CDF, Abramowitz-Stegun
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const d = 0.3989423 * Math.exp((-z * z) / 2)
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))))
  return z > 0 ? 1 - p : p
}

type Quoted = { dealer: string; place: string; list: number; price: number; norm: number; day: number }

class Shadow extends Strategy<ShadowParams> {
  private belief: number[] = []
  private day = -1
  private prevLevel: number | null = null
  private war = false
  private probesLeft = 0
  private quotes = new Map<string, Quoted>()
  private placeOff = new Map<string, number>()
  private dealerOff = new Map<string, number>()
  private dealerWins = new Map<string, number>()
  private todayAsk = new Map<string, number>()
  private todayWin = new Map<string, number>()
  private capitalPlaces = new Set<string>()
  private wins = 0
  private losses = 0

  constructor(setup: Setup, params: ShadowParams) {
    super(setup, params)
    for (const place of setup.map.places)
      if (CAPITAL.some((name) => place.name.toLowerCase().includes(name))) this.capitalPlaces.add(place.id)
    this.belief = this.prior()
  }

  private prior(): number[] {
    const { priorLevel, priorSd } = this.params
    const w = GRID.map((l) => Math.exp(-((Math.log(l / priorLevel) / priorSd) ** 2) / 2))
    return normalise(w)
  }

  private mean(): number {
    return this.belief.reduce((s, w, i) => s + w * GRID[i]!, 0)
  }

  /** Rolls the belief to a new day: drift, part prior, dealer undercut, a fresh place offset. */
  private roll(now: number): void {
    const day = Math.floor(now / DAY)
    if (day === this.day) return
    if (this.day >= 0) {
      const level = this.mean()
      this.prevLevel = level
      const p = this.params
      const sd = p.widen
      const drift = GRID.map((l) =>
        this.belief.reduce((s, w, i) => s + w * Math.exp(-((Math.log(l / GRID[i]!) / sd) ** 2) / 2), 0),
      )
      const prior = this.prior()
      this.belief = normalise(normalise(drift).map((w, i) => (1 - p.reset) * w + p.reset * prior[i]!))
      for (const [dealer, asked] of this.todayAsk) {
        const won = this.todayWin.get(dealer) ?? 0
        if (asked >= 2 && won / asked > 0.5)
          this.dealerOff.set(dealer, (this.dealerOff.get(dealer) ?? 0) + Math.log(1 - p.undercut))
      }
      this.placeOff.clear()
      this.todayAsk.clear()
      this.todayWin.clear()
    }
    this.day = day
    this.war = false
    this.probesLeft = this.params.probes
  }

  /** The multiple of the day level that this request's flip sits at. */
  private adjust(dealer: string, place: string): number {
    const p = this.params
    const base = this.capitalPlaces.has(place) ? p.capitalMult : p.otherMult
    const trust = 1 + p.trustPer * Math.min(p.trustCap, this.dealerWins.get(dealer) ?? 0)
    return base * trust * Math.exp((this.placeOff.get(place) ?? 0) + (this.dealerOff.get(dealer) ?? 0))
  }

  /** P(win) at normalised price x under the belief and the request scatter. */
  private winAt(x: number): number {
    const s = this.params.scatter
    return this.belief.reduce((acc, w, i) => acc + w * (1 - phi(Math.log(x / GRID[i]!) / s)), 0)
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    this.roll(books.now)
    const p = this.params
    const option = pickOption(request, books.now, { map: this.setup.map, level: this.setup.level })
    if (!option) return null
    const place = request.legs[0]?.delivery.placeId ?? ''
    const adj = this.adjust(request.dealerId, place)
    const list = option.listPriceCents
    const cost = p.costMult * request.referenceFeeCents
    const floor = cost * (1 + p.minMargin)
    const scale = list * adj // price = norm * scale
    this.todayAsk.set(request.dealerId, (this.todayAsk.get(request.dealerId) ?? 0) + 1)
    if (this.war && p.warDecline) return null

    let price: number
    if (this.probesLeft > 0) {
      const k = p.probes - this.probesLeft
      const frac = p.probes > 1 ? k / (p.probes - 1) : 0.5
      // spread over the belief: low, high, middle ... (bit-reversed order)
      const order = [0, 1, 0.5, 0.25, 0.75, 0.125, 0.875, 0.375, 0.625]
      const f = order[k] ?? frac
      this.probesLeft--
      price = this.mean() * scale * (p.probeLow + f * (p.probeHigh - p.probeLow))
    } else {
      let best = -Infinity
      price = floor
      for (let x = 0.7; x <= 2.2; x += 0.01) {
        const pr = x * scale
        const value = (pr - cost) * this.winAt(x)
        if (value > best) {
          best = value
          price = pr
        }
      }
      price *= p.shade
    }
    const asked = this.todayAsk.get(request.dealerId) ?? 0
    const won = this.todayWin.get(request.dealerId) ?? 0
    if (p.winCap < 1 && asked >= 3 && won / asked > p.winCap) price *= p.capRaise
    price = Math.round(Math.max(price, floor))
    this.quotes.set(request.id, {
      dealer: request.dealerId,
      place,
      list,
      price,
      norm: price / scale,
      day: this.day,
    })
    return { [option.kind]: price }
  }

  sent(action: Action, result: ActionResult, books: Books): void {
    if (action.type !== 'quote' || !('ok' in result) || !result.ok) return
    const request = books.requests.get(action.requestId)
    if (!request || this.quotes.has(action.requestId)) return
    const [kind, price] = Object.entries(action.prices)[0] ?? []
    const option = request.options.find((o) => o.kind === kind)
    if (!option || typeof price !== 'number') return
    const place = request.legs[0]?.delivery.placeId ?? ''
    const scale = option.listPriceCents * this.adjust(request.dealerId, place)
    this.quotes.set(action.requestId, {
      dealer: request.dealerId,
      place,
      list: option.listPriceCents,
      price,
      norm: price / scale,
      day: Math.floor(books.now / DAY),
    })
  }

  observe(event: DeskEvent, books: Books): void {
    if (event.kind === 'price_request') this.roll(event.at)
    if (event.kind !== 'order_won' && event.kind !== 'order_lost') return
    const id = event.kind === 'order_won' ? event.order.id : event.requestId
    const q = this.quotes.get(id)
    if (!q) return
    this.quotes.delete(id)
    if (q.day !== this.day) return
    const won = event.kind === 'order_won'
    if (won) {
      this.wins++
      this.todayWin.set(q.dealer, (this.todayWin.get(q.dealer) ?? 0) + 1)
      this.dealerWins.set(q.dealer, (this.dealerWins.get(q.dealer) ?? 0) + 1)
    } else this.losses++
    const p = this.params
    const predicted = this.winAt(q.norm)
    // filter update of the day level
    const s = p.scatter
    this.belief = normalise(
      this.belief.map((w, i) => {
        const pw = 1 - phi(Math.log(q.norm / GRID[i]!) / s)
        return w * (won ? pw : 1 - pw) + 1e-12
      }),
    )
    // residuals: outage region and dealer
    const r = (won ? 1 : 0) - predicted
    this.placeOff.set(q.place, clamp((this.placeOff.get(q.place) ?? 0) + p.placeLr * r, -0.3, 0.3))
    this.dealerOff.set(q.dealer, clamp((this.dealerOff.get(q.dealer) ?? 0) + p.dealerLr * r, -0.4, 0.3))
    // war day
    if (!this.war && this.prevLevel !== null) {
      const asked = [...this.todayAsk.values()].reduce((a, b) => a + b, 0)
      if (asked >= 15 && this.mean() < p.warDrop * this.prevLevel) this.war = true
    }
    void books
  }

  gig(need: GigNeed, books: Books): GigPlan {
    const plan = starterGig(need, books, this.setup.level)
    if (books.urgent.has(need.order.id)) return plan
    const request = books.requests.get(need.order.id)
    if (!request) return plan
    const p = this.params
    const typical = (request.referenceFeeCents * need.legs.length) / need.order.legs.length
    const ageBump = need.why === 'repost' || need.why === 'retry' ? 0.15 : 0
    const schedule: FeeStep[] = []
    for (let k = 0; k < p.feeSteps; k++) {
      const mult = Math.min(p.feeMax, p.feeOpen + ageBump + k * p.feeRise)
      schedule.push({ at: books.now + k * HOUR, feeCents: Math.max(1, Math.round(typical * mult)) })
    }
    return { ...plan, schedule }
  }

  summary(): string {
    return `shadow: level ${this.mean().toFixed(2)}, ${this.wins} wins, ${this.losses} losses, war ${this.war}`
  }
}

const normalise = (w: number[]): number[] => {
  const s = w.reduce((a, b) => a + b, 0) || 1
  return w.map((x) => x / s)
}
const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x))

export const shadow: StrategyKind<ShadowParams> = {
  defaults: {
    priorLevel: 1.32,
    priorSd: 0.15,
    scatter: 0.15,
    reset: 0.3,
    widen: 0.08,
    capitalMult: 0.9,
    otherMult: 1.05,
    placeLr: 0.08,
    dealerLr: 0.04,
    undercut: 0.08,
    trustPer: 0.01,
    trustCap: 25,
    probes: 6,
    probeLow: 0.85,
    probeHigh: 1.2,
    shade: 1,
    costMult: 1.25,
    minMargin: 0.08,
    warDrop: 0.85,
    warDecline: false,
    winCap: 1,
    capRaise: 1.08,
    feeOpen: 0.85,
    feeRise: 0.06,
    feeMax: 1.5,
    feeSteps: 12,
  },
  build: (setup, params) => new Shadow(setup, params),
}
