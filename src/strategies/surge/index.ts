/** surge: driver capacity is the scarce good, so price it like ride-hailing surge pricing. The price multiple rises
 * smoothly with the open load of the pickup day and with the late share, and falls below the base when capacity is
 * idle, so the hard brake almost never fires. Tight orders carry a premium, orders with days of slack sell lower, and
 * trusting dealers pay more. See README.md. */
import { type BaseParams, type OptionKind, type PriceCtx, PricedStrategy, priced } from '../base/index.ts'

const OWN = {
  /** Base multiples of the list price at the target utilisation. */
  sameDay: 1.48,
  nextDay: 1.42,
  within3: 1.36,
  /** Soft capacity: open load per pickup day where utilisation is 1. */
  capacity: 14,
  /** Utilisation at which the surge is neutral (×1). */
  target: 0.5,
  /** Surge slope: multiple = exp(surgeK × (u − target)), clamped to [idleFloor, surgeCap]. */
  surgeK: 0.35,
  idleFloor: 0.9,
  surgeCap: 1.5,
  /** Late surge: × (1 + lateK × lateShare). */
  lateK: 3,
  /** Slack: + tightPremium at zero slack, decaying with `tightHours`; − slackDiscount per day of slack past a day. */
  tightPremium: 0.08,
  tightHours: 12,
  slackDiscount: 0.02,
  slackDiscountMax: 0.05,
  /** Trust premium per trust point (each on-time order raises the dealer's threshold about 1%). */
  trustStep: 0.011,
  /** Backstop brake: far above the surge's working range, and a high markup instead of a decline. */
  maxOpenPerDay: 40,
  brakeMarkup: 1.25,
}

type P = typeof OWN & BaseParams

class Surge extends PricedStrategy<P> {
  price(ctx: PriceCtx): number {
    const p = this.params
    const base: Record<OptionKind, number> = {
      same_day: p.sameDay,
      next_day: p.nextDay,
      within_3_days: p.within3,
    }
    const u = ctx.load / p.capacity
    const surge = Math.min(p.surgeCap, Math.max(p.idleFloor, Math.exp(p.surgeK * (u - p.target))))
    const late = 1 + p.lateK * ctx.lateShare
    const slackH = Math.max(0, ctx.slack / 60)
    const tight = p.tightPremium * Math.exp(-slackH / p.tightHours)
    const loose = Math.min(p.slackDiscountMax, p.slackDiscount * Math.max(0, slackH / 24 - 1))
    const trust = 1 + p.trustStep * ctx.trust
    return base[ctx.option.kind] * surge * late * (1 + tight - loose) * trust
  }
}

export const surge = priced(OWN, Surge)
