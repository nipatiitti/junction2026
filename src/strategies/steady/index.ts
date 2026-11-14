/** steady: one price per option as a fixed multiple of list that does not rise with trust, so trust turns into
 * volume rather than margin. Big dealers (share >= `bigShare`) get more slack and a higher opening fee, to keep
 * their orders on time. Everything else comes from the shared base (src/strategies/base/). */
import type { FeeStep } from '../../../vendor/spread-typescript/spread.ts'
import { DAY } from '../../ops/index.ts'
import {
  type BaseParams,
  type FeeCtx,
  type OptionKind,
  type Outcome,
  type PriceCtx,
  PricedStrategy,
  priced,
} from '../base/index.ts'

const OWN = {
  sameDay: 1.4,
  nextDay: 1.3,
  within3: 1.22,
  trustStep: 0,
  mondayDiscount: 0.08,
  bigShare: 0.05,
  bigFee: 1.1,
  bigComfort: 12,
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

class Steady extends PricedStrategy<typeof OWN & BaseParams> {
  /** Trust of the dealer when each request was quoted, and per weekday: wins, quotes, trust summed. */
  private readonly trustAt = new Map<string, number>()
  private readonly days = DAYS.map(() => ({ won: 0, quoted: 0, trust: 0 }))

  /** A big dealer: at least `bigShare` of the requests so far, once 20 requests are in. */
  private big(dealerId: string): boolean {
    const requests = this.t.requests.get(dealerId) ?? 0
    return this.t.total >= 20 && requests / this.t.total >= this.params.bigShare
  }

  price(ctx: PriceCtx): number | null {
    const p = this.params
    if (this.big(ctx.dealerId) && ctx.slack < p.bigComfort * 60) return null
    const markup: Record<OptionKind, number> = { same_day: p.sameDay, next_day: p.nextDay, within_3_days: p.within3 }
    this.trustAt.set(ctx.request.id, ctx.trust)
    const monday = ctx.weekday === 0 ? 1 - p.mondayDiscount : 1
    return markup[ctx.option.kind] * (1 + p.trustStep * ctx.trust) * monday
  }

  /** Big dealers' gigs open at `bigFee` × the base's opening fee, and never step below it. */
  override feePlan(ctx: FeeCtx): FeeStep[] {
    const plan = super.feePlan(ctx)
    if (ctx.urgent || plan.length === 0 || this.params.bigFee === 1 || !this.big(ctx.order.dealerId)) return plan
    const open = Math.round(plan[0].feeCents * this.params.bigFee)
    return plan.map((s, i) => ({ at: s.at, feeCents: i === 0 ? open : Math.max(s.feeCents, open) }))
  }

  override onOutcome(outcome: Outcome, won: boolean): void {
    const day = this.days[Math.floor(outcome.request.arrivedAt / DAY) % 7]
    day.quoted++
    if (won) day.won++
    day.trust += this.trustAt.get(outcome.request.id) ?? 0
  }

  override summary(): string {
    const byDay = this.days
      .map((d, i) =>
        d.quoted > 0 ? `${DAYS[i]} ${((100 * d.won) / d.quoted).toFixed(0)}%/t${(d.trust / d.quoted).toFixed(1)}` : '',
      )
      .filter(Boolean)
      .join(' ')
    return `${super.summary()} | steady win%/trust by day: ${byDay}`
  }
}

export const steady = priced(OWN, Steady)
