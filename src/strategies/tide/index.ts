/** tide: the week has a shape and the price follows it. A price is a base markup per option × a weekday schedule ×
 * a global level held by a PI controller on the recent win rate (against a target that falls through the week) ×
 * a per-dealer trust premium × a Friday late-delivery premium. On the price-war day (today's win rate collapses) the
 * controller freezes and the level is cut by `warCut` (1 = sit the day out at normal prices). */
import { DAY, HOUR } from '../../ops/index.ts'
import { type BaseParams, type OptionKind, type Outcome, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  sameDay: 1.42,
  nextDay: 1.36,
  within3: 1.3,
  /** Weekday schedule (Monday .. Sunday) on the price. */
  mon: 0.96,
  tue: 1.0,
  wed: 1.04,
  thu: 1.08,
  fri: 1.1,
  wkd: 1.1,
  /** Target win rate: `targetMon` on Monday, falling linearly to `targetFri` from Friday on. */
  targetMon: 0.55,
  targetFri: 0.35,
  /** PI controller on log(level): window of recent quotes, gains per outcome, clamps. */
  window: 40,
  kp: 0.35,
  ki: 0.015,
  iMax: 14,
  levelMin: 0.8,
  levelMax: 1.35,
  /** Price-war day: today's win rate under `warRatio` × target after `warMin` quotes. Prices × `warCut` that day. */
  warRatio: 0.45,
  warMin: 15,
  warCut: 0.85,
  /** Trust premium: +`trustStep` per trust point, up to `trustCap`. */
  trustStep: 0.012,
  trustCap: 22,
  /** Friday premium on options whose deadline falls Friday from `friHour` on, or the weekend. */
  friPremium: 1.08,
  friHour: 15,
}
type P = typeof OWN & BaseParams

class Tide extends PricedStrategy<P> {
  private recent: number[] = []
  private integral = 0
  private logLevel = 0
  private warDay = -1

  private target(weekday: number): number {
    const p = this.params
    return p.targetMon + ((p.targetFri - p.targetMon) * Math.min(weekday, 4)) / 4
  }

  override onOutcome(outcome: Outcome, won: boolean): void {
    const p = this.params
    const day = Math.floor(outcome.request.arrivedAt / DAY)
    const target = this.target(day % 7)
    this.recent.push(won ? 1 : 0)
    if (this.recent.length > p.window) this.recent.shift()
    const today = this.t.byDay.get(day)
    const n = today ? today.won + today.lost : 0
    if (today && n >= p.warMin && today.won / n < p.warRatio * target) this.warDay = day
    if (day === this.warDay) return
    const rate = this.recent.reduce((a, b) => a + b, 0) / this.recent.length
    const err = rate - target
    this.integral = Math.max(-p.iMax, Math.min(p.iMax, this.integral + err))
    this.logLevel = p.kp * err + p.ki * this.integral
  }

  price(ctx: PriceCtx): number {
    const p = this.params
    const markup: Record<OptionKind, number> = { same_day: p.sameDay, next_day: p.nextDay, within_3_days: p.within3 }
    const schedule = [p.mon, p.tue, p.wed, p.thu, p.fri, p.wkd, p.wkd][ctx.weekday] ?? 1
    const level = Math.max(p.levelMin, Math.min(p.levelMax, Math.exp(this.logLevel)))
    const war = Math.floor(ctx.now / DAY) === this.warDay ? p.warCut : 1
    const trust = 1 + p.trustStep * Math.min(ctx.trust, p.trustCap)
    const dl = ctx.option.deadline
    const dlDay = Math.floor(dl / DAY) % 7
    const late = dlDay > 4 || (dlDay === 4 && (dl % DAY) / HOUR >= p.friHour) ? p.friPremium : 1
    return markup[ctx.option.kind] * schedule * level * war * trust * late
  }
}

export const tide = priced(OWN, Tide)
