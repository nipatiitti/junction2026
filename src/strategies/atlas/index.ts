/** atlas: price by place. A price level per delivery town, pooled per region while a town has few observations,
 * started from a prior that falls with the drivers living near the delivery, and learned from wins and losses by a
 * stochastic-approximation step aimed at a target win rate. A region whose win rate jumps on one day (the
 * competitor is out there) is priced up for the rest of that day. A trust premium per dealer on top. */
import { DAY } from '../../ops/index.ts'
import { type BaseParams, type OptionKind, type Outcome, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  /** Prior level (within_3_days, trust 0, × list) for the capital region and elsewhere. */
  priorCapital: 1.22,
  priorOther: 1.38,
  /** Elsewhere, the prior falls by up to `nearDrop` as drivers near the delivery reach `nearFull`. */
  nearDrop: 0.08,
  nearFull: 12,
  /** Option factors over within_3_days. */
  nextDay: 1.12,
  sameDay: 1.33,
  /** The SA step: level × exp(eta × (won − target)); eta falls from `eta0` towards `etaMin` with observations. */
  target: 0.25,
  eta0: 0.08,
  etaMin: 0.025,
  etaDecay: 20,
  /** A town's own level gets weight n / (n + `townPool`) over its region's. */
  townPool: 8,
  /** Levels stay within these bounds. */
  minLevel: 1.18,
  maxLevel: 2.0,
  /** Outage: a region winning over `outageRate` of at least `outageMin` quotes today is priced × `outageBoost`. */
  outageRate: 0.8,
  outageMin: 5,
  outageBoost: 1.12,
  /** Trust premium: × (1 + trustStep × trust). */
  trustStep: 0.012,
}
type P = typeof OWN & BaseParams
type Level = { level: number; n: number }
type Quoted = { town: string; region: string; day: number }

const CAPITAL = ['helsinki', 'espoo', 'vantaa', 'hyvink', 'kauniainen']

class Atlas extends PricedStrategy<P> {
  private readonly towns = new Map<string, Level>()
  private readonly regions = new Map<string, Level>()
  private readonly days = new Map<string, { won: number; lost: number }>()
  private readonly quoted = new Map<string, Quoted>()
  private readonly placeRegion = new Map<string, { region: string; capital: boolean }>()

  private regionOf(placeId: string): { region: string; capital: boolean } {
    const hit = this.placeRegion.get(placeId)
    if (hit) return hit
    const place = this.setup.map.places.find((p) => p.id === placeId)
    const name = (place?.name ?? '').toLowerCase()
    const capital = CAPITAL.some((c) => name.includes(c))
    const lat = place?.lat ?? 60
    const region = capital
      ? 'capital'
      : lat < 61.2
        ? 'south'
        : lat < 62.5
          ? 'west-middle'
          : lat < 64
            ? 'middle'
            : 'north'
    const v = { region, capital }
    this.placeRegion.set(placeId, v)
    return v
  }

  private prior(capital: boolean, near: number): number {
    const p = this.params
    if (capital) return p.priorCapital
    return p.priorOther - p.nearDrop * Math.min(1, near / p.nearFull)
  }

  price(ctx: PriceCtx): number {
    const p = this.params
    const town = ctx.request.legs.at(-1)?.delivery.placeId ?? ''
    const { region, capital } = this.regionOf(town)
    const prior = this.prior(capital, ctx.nearDelivery)
    const r = this.regions.get(region) ?? { level: prior, n: 0 }
    if (!this.regions.has(region)) this.regions.set(region, r)
    const t = this.towns.get(town) ?? { level: r.level, n: 0 }
    if (!this.towns.has(town)) this.towns.set(town, t)
    const w = t.n / (t.n + p.townPool)
    let level = w * t.level + (1 - w) * r.level
    const day = Math.floor(ctx.now / DAY)
    const today = this.days.get(`${region}/${day}`)
    if (today && today.won + today.lost >= p.outageMin && today.won / (today.won + today.lost) > p.outageRate)
      level *= p.outageBoost
    this.quoted.set(ctx.request.id, { town, region, day: Math.floor(ctx.request.arrivedAt / DAY) })
    const factor: Record<OptionKind, number> = { same_day: p.sameDay, next_day: p.nextDay, within_3_days: 1 }
    return level * factor[ctx.option.kind] * (1 + p.trustStep * ctx.trust)
  }

  override onOutcome(outcome: Outcome, won: boolean): void {
    const q = this.quoted.get(outcome.request.id)
    if (!q) return
    this.quoted.delete(outcome.request.id)
    const p = this.params
    for (const lv of [this.towns.get(q.town), this.regions.get(q.region)]) {
      if (!lv) continue
      const eta = Math.max(p.etaMin, p.eta0 / (1 + lv.n / p.etaDecay))
      lv.level = Math.min(p.maxLevel, Math.max(p.minLevel, lv.level * Math.exp(eta * ((won ? 1 : 0) - p.target))))
      lv.n++
    }
    const key = `${q.region}/${q.day}`
    const tally = this.days.get(key) ?? { won: 0, lost: 0 }
    if (won) tally.won++
    else tally.lost++
    this.days.set(key, tally)
  }

  override summary(): string {
    const regions = [...this.regions].map(([k, v]) => `${k} ${v.level.toFixed(2)}/${v.n}`).join(', ')
    return `${super.summary()}; atlas levels: ${regions}`
  }
}

export const atlas = priced(OWN, Atlas)
