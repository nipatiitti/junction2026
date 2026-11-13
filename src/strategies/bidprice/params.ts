/** The bidprice strategy's params: flat, so `--set key=value` reaches each one, with the flags of the brief's "Flags"
 * section at the brief's design. They pass through to the models' own params. */
import { type FeeParams, feeParams } from '../../models/fees/index.ts'
import { type QuoteParams, quoteParams } from '../../models/quote/index.ts'
import { HOUR } from '../../time.ts'

export type BidPriceParams = {
  /** `profit`: the price that maximises the expected profit; `median`: the price that wins half the time. */
  pricing: string
  /** Count each dealer's trust in the win chance, and value the trust a win adds. */
  trust: boolean
  /** Price each option on its own rung of the option ladder. */
  ladder: boolean
  /** Learn a level for lanes by the drivers who live near the delivery place. */
  lane: boolean
  /** On a price war day: `follow` the level down, or `decline` until 18:00. */
  war: string
  /** Plan fees with the fee model's solver; false: the ramp that dispatch.py is on time with (`openFee`, `topFee`). */
  feeSolver: boolean
  /** Scale fees by the learned multiplier of each gig feature. */
  feeExtras: boolean
  /** Scale the cost `c` by the learned capacity multiplier `lambda`. */
  capacity: boolean
  /** Scale the lateness cost by the learned on-time multiplier `mu`. */
  onTime: boolean
  /** Every prior neutral: the models learn the world from nothing. */
  cold: boolean
  /** Decline a request whose best expected profit, trust included, is under this. */
  minValueCents: number
  /** Scales the value of the trust a win adds; 0 turns it off. */
  trustValue: number
  /** A late order halves the dealer's trust: its lateness cost is scaled by 1 + lateTrust × the dealer's share of the
   * requests, over the same for an average dealer. 0 turns it off. */
  lateTrust: number
  /** The learning rates of `lambda` and `mu`, and the late share that `mu` aims at. */
  etaLambda: number
  etaMu: number
  lateTarget: number
  /** Admission: offer an option only with this many hours to spare (more as `tightening` falls); with none that
   * comfortable, only the slowest option we can serve. */
  comfortHours: number
  /** The ramp: open at `openFee` × typical, raise early, and reach `topFee` × typical `topLeadHours` before the last
   * pickup. */
  openFee: number
  topFee: number
  topLeadHours: number
  /** The solver's caution: its lowest fee over the expected fee, and its fee due `topLeadHours` before the pickup. */
  feeFloor: number
  topRatio: number
  /** After the deadline warning: `topRatio` × typical at once, rising to `urgentTop` × typical in two hours. */
  urgentTop: number
  /** The tick reprices a gig of ours that no driver holds: one dropped since its schedule was set, at once, to the
   * ramp from now and at least `dropStep` × typical above the dropped fee; one whose schedule ended `staleHours` ago,
   * climbing `climbStep` × typical an hour up to `climbTop` × typical. At most `repriceMax` a tick, the nearest last
   * pickup first. */
  staleHours: number
  dropStep: number
  climbStep: number
  climbTop: number
  repriceMax: number
}

export const DEFAULTS: BidPriceParams = {
  pricing: 'profit',
  trust: true,
  ladder: true,
  lane: true,
  war: 'follow',
  feeSolver: false,
  feeExtras: true,
  capacity: true,
  onTime: true,
  cold: false,
  minValueCents: 200,
  trustValue: 1,
  lateTrust: 5,
  etaLambda: 0.1,
  etaMu: 0.02,
  lateTarget: 0.05,
  comfortHours: 9,
  openFee: 0.9,
  topFee: 2.5,
  topLeadHours: 8,
  // The fee model is optimistic about flat low fees (it expects 95-99% booked where 77-89% were), a gig that drivers
  // have viewed rarely books after a raise, and a late order costs about €60. The solver opens at its floor on
  // nearly every gig, so the floor is the opening fee: start at dispatch.py's 1.0 (97% on time), and reach the top
  // earlier than the model's 6 hours.
  feeFloor: 1,
  topRatio: 1.5,
  urgentTop: 2.5,
  staleHours: 2,
  dropStep: 0.15,
  climbStep: 0.1,
  climbTop: 3,
  repriceMax: 10,
}

/** The quote models' params from the strategy's. */
export function quoteParamsOf(p: BidPriceParams): QuoteParams {
  return quoteParams({
    cold: p.cold,
    flags: {
      pricing: p.pricing === 'median' ? 'median' : 'profit',
      trust: p.trust,
      ladder: p.ladder,
      lane: p.lane,
      war: p.war === 'decline' ? 'decline' : 'follow',
    },
    minValueCents: p.minValueCents,
    trustValue: p.trustValue,
  })
}

/** The fee models' params from the strategy's, for one level. */
export function feeParamsOf(p: BidPriceParams, level: number): FeeParams {
  const base = feeParams(level, {
    solver: p.feeSolver,
    extras: p.feeExtras,
    capacity: p.capacity,
    onTime: p.onTime,
    cold: p.cold,
  })
  return {
    ...base,
    plan: {
      ...base.plan,
      fees: { ...base.plan.fees, from: p.feeFloor },
      topRatio: p.topRatio,
      topLeadMinutes: p.topLeadHours * HOUR,
    },
    learn: { ...base.learn, etaLambda: p.etaLambda, etaMu: p.etaMu, lateTarget: p.lateTarget },
  }
}
