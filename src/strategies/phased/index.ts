/** phased: bidprice with one set of params until `phaseHour` (hours from Monday 00:00) and another from then on. A
 * practice world is deterministic, so a week played with params A until the switch is the same week as plain A up to
 * that minute: the two differ only by what B decides afterwards. That is a fork of A's week at the switch without
 * copying a world, and it shows when in the week a change earns or loses its money (analysis/phases.py).
 *
 * The params are bidprice's, for the first phase, plus `phaseFile`, a JSON file of the params that change at the
 * switch. Both phases hear every event and every action sent, so the second starts with what the week has taught. */
import { readFileSync } from 'node:fs'
import type { Action, ActionResult, DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import {
  type Books,
  type GigNeed,
  type GigPlan,
  type Prices,
  type Setup,
  Strategy,
  type StrategyKind,
} from '../../strategy.ts'
import { BidPrice } from '../bidprice/index.ts'
import { type BidPriceParams, DEFAULTS } from '../bidprice/params.ts'

export type PhasedParams = BidPriceParams & { phaseFile: string; phaseHour: number }

export class Phased extends Strategy<PhasedParams> {
  override readonly every = 30
  readonly first: BidPrice
  readonly second: BidPrice

  constructor(setup: Setup, params: PhasedParams) {
    super(setup, params)
    const { phaseFile, phaseHour: _hour, ...base } = params
    const later = phaseFile ? (JSON.parse(readFileSync(phaseFile, 'utf8')) as Partial<BidPriceParams>) : {}
    for (const key of Object.keys(later))
      if (!Object.hasOwn(DEFAULTS, key)) throw new Error(`${phaseFile}: bidprice has no param "${key}"`)
    this.first = new BidPrice(setup, base)
    this.second = new BidPrice(setup, { ...base, ...later })
  }

  private active(now: number): BidPrice {
    return now < this.params.phaseHour * 60 ? this.first : this.second
  }

  override observe(event: DeskEvent, books: Books): void {
    this.first.observe(event, books)
    this.second.observe(event, books)
  }

  override sent(action: Action, result: ActionResult, books: Books): void {
    this.first.sent(action, result, books)
    this.second.sent(action, result, books)
  }

  quote(request: PriceRequest, books: Books): Prices | null {
    return this.active(books.now).quote(request, books)
  }

  gig(need: GigNeed, books: Books): GigPlan[] {
    return this.active(books.now).gig(need, books)
  }

  override tick(books: Books): Action[] {
    return this.active(books.now).tick(books)
  }

  override summary(): string {
    return `phased at hour ${this.params.phaseHour} to ${this.params.phaseFile || 'the same params'}: ${this.second.summary()}`
  }
}

export const phased: StrategyKind<PhasedParams> = {
  defaults: { ...DEFAULTS, phaseFile: '', phaseHour: 0 },
  build: (setup, params) => new Phased(setup, params),
}
