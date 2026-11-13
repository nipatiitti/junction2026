/** The quote models' parameters: the priors measured on the saved weeks (src/params/quote.json, written by
 * `uv run python -m analysis.priors_quote`), the knobs, and the flags that turn each idea off for the bench. */
import { readFileSync } from 'node:fs'
import type { DeliveryOption } from '../../../vendor/spread-typescript/types.ts'

export type Option = DeliveryOption['kind']
/** Every delivery option, fastest first. */
export const OPTIONS: readonly Option[] = ['same_day', 'next_day', 'within_3_days']

/** What src/params/quote.json holds. Nothing in it is keyed to a seed, a dealer, a driver or a place. */
export type QuotePriors = {
  /** Cumulative probabilities of the quantile grids below. */
  probs: number[]
  /** Probed flips as price / list at trust 0, pooled over worlds and days (finding 3). For reading only. */
  flipRatio: number[]
  /** A flip over its world-day level, ladder and lane: the request's own scatter, median about 1. */
  flipResidual: number[]
  /** The flip level of `next_day` on a lane with the usual drivers near its delivery place. */
  startLevel: number
  /** How far worlds and their days move the level, as standard deviations of its log. */
  worldSd: number
  daySd: number
  /** Each option's flip over the `next_day` flip, both over their own list prices (finding 4). */
  ladder: Record<Option, number>
  /** The log level per doubling of the drivers who live near the delivery place, around `laneCenter` doublings. */
  laneSlope: number
  laneCenter: number
  /** The log level that each order on time adds at the dealer, up to `trustCap` orders. */
  trustPerOrder: number
  trustCap: number
  /** The share of wins where the dealer takes the fastest option, by its premium over the cheapest. */
  choicePremium: number[]
  choiceFastest: number[]
  requestsPerWeek: number
  dealers: number
}

export type QuoteFlags = {
  /** `profit`: the price that maximises the expected profit. `median`: the price that wins half the time, the
   * rule of strategies/pricing/model.py. */
  pricing: 'profit' | 'median'
  /** Count each dealer's trust in the level, and value the trust that a win adds. */
  trust: boolean
  /** Price each option on its own rung of the ladder; off, every option sits at the same level. */
  ladder: boolean
  /** Learn an offset for lanes by the drivers who live near the delivery place. */
  lane: boolean
  /** On a day whose level falls `warDrop` under the world's, `follow` it down or `decline` until 18:00. */
  war: 'follow' | 'decline'
}

export type QuoteParams = QuotePriors & {
  flags: QuoteFlags
  /** Prior standard deviations (log) of the parts the data fixes only loosely. */
  laneSd: number
  ladderSd: number
  trustSd: number
  /** Variance added to the day's level at each answer, so the day keeps up with a change inside it. */
  dayDrift: number
  warDrop: number
  /** Decline when the best expected profit of a request, trust included, is under this. */
  minValueCents: number
  /** Scales the value of the trust that a win adds; 0 turns it off. */
  trustValue: number
  /** A decline quotes this multiple of the list price, which loses at no cost. */
  declineFactor: number
  /** The price grid, as price / list, and its step in log. */
  gridFrom: number
  gridTo: number
  gridStep: number
  /** The highest premium of a faster option over a slower one that the search tries. */
  maxPremium: number
}

const DEFAULT_FLAGS: QuoteFlags = { pricing: 'profit', trust: true, ladder: true, lane: true, war: 'follow' }

const KNOBS = {
  laneSd: 0.05,
  ladderSd: 0.05,
  trustSd: 0.004,
  dayDrift: 0.0002,
  warDrop: 0.15,
  minValueCents: 200,
  trustValue: 1,
  declineFactor: 10,
  gridFrom: 0.8,
  gridTo: 2.2,
  gridStep: 0.01,
  maxPremium: 0.6,
}

export function readPriors(file: URL = new URL('../../params/quote.json', import.meta.url)): QuotePriors {
  return JSON.parse(readFileSync(file, 'utf8')) as QuotePriors
}

export type QuoteOptions = Partial<Omit<QuoteParams, 'flags'>> & { flags?: Partial<QuoteFlags>; cold?: boolean }

/** The parameters: the priors of src/params/quote.json, or neutral ones with `cold: true`, then any overrides. */
export function quoteParams(options: QuoteOptions = {}, priors: QuotePriors = readPriors()): QuoteParams {
  const { cold, flags, ...overrides } = options
  const base = { ...priors, ...KNOBS, flags: { ...DEFAULT_FLAGS, ...flags } }
  return { ...(cold ? neutral(base) : base), ...overrides }
}

/** Every prior set to neutral: level 1 with a wide spread, no ladder, lane or trust effect, and a dealer who pays
 * nothing for speed. Each part still learns from the week. */
export function neutral(params: QuoteParams): QuoteParams {
  const spread = 0.2 // a logistic scale: the log flip has a standard deviation of 0.36
  return {
    ...params,
    flipResidual: params.probs.map((p) => Math.exp(spread * Math.log(p / (1 - p)))),
    startLevel: 1,
    worldSd: 0.3,
    daySd: 0.15,
    ladder: { same_day: 1, next_day: 1, within_3_days: 1 },
    ladderSd: 0.1,
    laneSlope: 0,
    laneSd: 0.1,
    trustPerOrder: 0,
    trustSd: 0.01,
    choiceFastest: params.choicePremium.map((premium) => (premium <= 0 ? 1 : 0)),
  }
}
