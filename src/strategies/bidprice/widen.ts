/** `quoteAll` and `allOptions`: quote instead of declining for a value reason, and offer every servable option.
 * - quoteAll: a request bidprice declines because its value is under `minValueCents` or no grid price covers the
 *   inflated cost, with an option it may offer (canServe, lateness, comfort), gets the profit-maximising quote with
 *   the honest cost (`quoteAllCostScale` in place of `costScale`), never under cost × (1 + `quoteAllMargin`), on the
 *   first `quoteAllDays` days of the week.
 * - allOptions: each offered option a quote leaves out gets its own profit-maximising price; a faster option is
 *   never cheaper than a slower one.
 * The counters are for the summary only. */
import type { PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { bestQuote, inWar, type Option } from '../../models/quote/index.ts'
import { OPTIONS } from '../../models/quote/params.ts'
import type { Prices } from '../../strategy.ts'
import { DAY } from '../../time.ts'
import type { BidPrice } from './index.ts'

type Decision = ReturnType<BidPrice['decide']>
type Day = { qa: number; qaWon: number; added: number; addedTaken: number }

export class Widen {
  readonly days: Day[] = Array.from({ length: 7 }, () => ({ qa: 0, qaWon: 0, added: 0, addedTaken: 0 }))
  private readonly qa = new Set<string>()
  private readonly added = new Map<string, Option[]>()

  private readonly bp: BidPrice

  constructor(bp: BidPrice) {
    this.bp = bp
  }

  /** The prices to send for a request, given bidprice's decision: null is a decline. */
  prices(request: PriceRequest, now: number, decision: Decision): Prices | null {
    const p = this.bp.params
    const day = Math.min(6, Math.floor(now / DAY))
    let prices: Partial<Record<Option, number>> | null = decision.decline ? null : { ...decision.prices }
    let scale = p.costScale
    if (!prices && p.quoteAll && day < p.quoteAllDays) {
      const offered = this.bp.offered(request, now)
      if (offered.length > 0 && !inWar(this.bp.quotes, now, this.bp.quoteParams)) {
        scale = p.quoteAllCostScale
        const costs = this.costs(request, now, scale)
        const loose = bestQuote(request, costs, this.bp.quotes, { ...this.bp.quoteParams, minValueCents: -1e18 }, now)
        if (!loose.decline) {
          prices = { ...loose.prices }
          for (const kind of Object.keys(prices) as Option[]) {
            const floor = Math.round((costs[kind] ?? 0) * (1 + p.quoteAllMargin))
            prices[kind] = Math.max(prices[kind] ?? 0, floor)
          }
          this.qa.add(request.id)
          this.days[day].qa++
        }
      }
    }
    if (!prices) return null
    if (p.allOptions) {
      const costs = this.costs(request, now, scale)
      const extra: Option[] = []
      for (const kind of Object.keys(costs) as Option[]) {
        if (prices[kind] !== undefined) continue
        const solo = bestQuote(
          request,
          { [kind]: costs[kind] },
          this.bp.quotes,
          { ...this.bp.quoteParams, minValueCents: -1e18 },
          now,
        )
        const price = solo.prices[kind]
        if (solo.decline || price === undefined) continue
        prices[kind] = price
        extra.push(kind)
      }
      if (extra.length > 0) {
        // A faster option never cheaper than a slower one: from the slowest up.
        let floor = 0
        for (const kind of [...OPTIONS].reverse()) {
          const price = prices[kind]
          if (price === undefined) continue
          if (price < floor) prices[kind] = floor
          floor = Math.max(floor, prices[kind] ?? 0)
        }
        this.added.set(request.id, extra)
        this.days[day].added += extra.length
      }
    }
    return prices
  }

  /** The cost of each option bidprice may offer, with the fee and late parts times `scale`. */
  private costs(request: PriceRequest, now: number, scale: number): Partial<Record<Option, number>> {
    const p = this.bp.params
    return Object.fromEntries(
      this.bp.offered(request, now).map((option) => {
        const { fee, late } = this.bp.costParts(request, option, now)
        const risk = p.lateRisk ? this.bp.riskOf(request, option, now) * p.lateRiskCents : 0
        return [option.kind, (fee + late) * scale + risk]
      }),
    )
  }

  /** An order won: count it for quoteAll, and for allOptions when the option taken was one it added. */
  won(orderId: string, option: Option, at: number): void {
    const day = Math.min(6, Math.floor(at / DAY))
    if (this.qa.has(orderId)) this.days[day].qaWon++
    if (this.added.get(orderId)?.includes(option)) this.days[day].addedTaken++
  }

  summary(): string {
    const by = (f: (d: Day) => string) => this.days.map(f).join(' ')
    const sum = (k: keyof Day) => this.days.reduce((s, d) => s + d[k], 0)
    return `widen: quoteAll ${sum('qa')} won ${sum('qaWon')} [${by((d) => `${d.qa}/${d.qaWon}`)}], allOptions added ${sum('added')} taken ${sum('addedTaken')} [${by((d) => `${d.added}/${d.addedTaken}`)}]`
  }
}
