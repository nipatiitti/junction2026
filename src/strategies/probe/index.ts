/** probe: recall run for information, not margin. Every remembered option of a recognised week is quoted at the price
 * that halves its bracket (README.md), never under cost, until `probeWinsPerDay` probes have won that day; then it is
 * recall. What recall declines stays declined, so the week can still be served. */
import type { DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import { type Option, OPTIONS, trustOf } from '../../models/quote/index.ts'
import type { Books, Prices, Setup, Strategy, StrategyKind } from '../../strategy.ts'
import { DEFAULTS as RECALL, ordered, Recall, type RecallParams } from '../recall/index.ts'

export type ProbeParams = RecallParams & {
  /** A one-sided bracket is probed this far beyond its known side (win × (1 + step), loss × (1 − step)). */
  probeStep: number
  /** Probes won per day before it falls back to recall's prices. */
  probeWinsPerDay: number
  /** A probe is at least cost × (1 + this). */
  probeMargin: number
}

export const DEFAULTS: ProbeParams = { ...RECALL, probeStep: 0.08, probeWinsPerDay: 45, probeMargin: 0 }

const DAY = 1440

class Probe extends Recall<ProbeParams> {
  /** Probe prices sent, by dealer and price, to count the ones that win. */
  readonly sentProbes = new Set<string>()
  readonly wonByDay = new Map<number, number>()
  readonly probeTally = { probed: 0, won: 0, capped: 0 }

  override observe(event: DeskEvent): void {
    super.observe(event)
    if (event.kind !== 'order_won') return
    const key = `${event.order.dealerId}|${event.order.priceCents}`
    if (!this.sentProbes.has(key)) return
    this.sentProbes.delete(key)
    const day = Math.floor(event.at / DAY)
    this.wonByDay.set(day, (this.wonByDay.get(day) ?? 0) + 1)
    this.probeTally.won++
  }

  override quote(request: PriceRequest, books: Books): Prices | null {
    const base = super.quote(request, books)
    const memory = this.recognised()
    if (!base || !memory || memory.sig[request.id] === undefined) return base
    const { probeStep, probeWinsPerDay, probeMargin } = this.rp
    if ((this.wonByDay.get(Math.floor(books.now / DAY)) ?? 0) >= probeWinsPerDay) {
      this.probeTally.capped++
      return base
    }
    const costs = this.costs(request, books.now)
    const k = 1 + trustOf(this.quotes, request.dealerId, this.quoteParams) / 100
    const out: Partial<Record<Option, number>> = { ...base }
    let probed = false
    for (const kind of OPTIONS) {
      if (base[kind] === undefined) continue
      const option = request.options.find((o) => o.kind === kind)
      const [w, l] = memory.opts[`${request.id}/${kind}`] ?? [null, null]
      if (!option || (w === null && l === null)) continue
      const ratio =
        w !== null && l !== null ? (w + l) / 2 : w !== null ? w * (1 + probeStep) : (l ?? 0) * (1 - probeStep)
      const price = Math.round(option.listPriceCents * k * ratio)
      if (price < (costs[kind] ?? Number.POSITIVE_INFINITY) * (1 + probeMargin)) continue
      out[kind] = price
      this.sentProbes.add(`${request.dealerId}|${price}`)
      probed = true
    }
    if (probed) this.probeTally.probed++
    return ordered(out)
  }

  override summary(): string {
    const { probed, won, capped } = this.probeTally
    return `${super.summary()}; probe: ${probed} requests probed, ${won} probes won, ${capped} past the daily cap`
  }
}

export const probe: StrategyKind<ProbeParams> = {
  defaults: DEFAULTS,
  build: (setup, params) => new Probe(setup, params) as unknown as Strategy<ProbeParams>,
}
