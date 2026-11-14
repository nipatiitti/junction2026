/** Re-quoting (RULES: "A new quote for the same request replaces the earlier one"; the dealer decides at the response
 * deadline, on the last quote). The first quote goes out at once as before; `requoteLeadMinutes` before the deadline
 * the request is priced again with the belief of then, and the new quote goes out when a price moves by
 * `requoteMinChange` or the options offered change. Every request is re-quoted at most once.
 *
 * State is rebuilt from `sent` (the quotes, in order: the last one is the one the quote learner holds) and `observe`
 * (the requests and the wins). */
import type { Action, DeskEvent, PriceRequest } from '../../../vendor/spread-typescript/spread.ts'
import type { Prices } from '../../strategy.ts'

type Open = { request: PriceRequest; first: Prices; requoted: boolean }

export class Requoter {
  /** The requests with a quote whose deadline has not passed. */
  readonly open = new Map<string, Open>()
  /** Request id -> 'up' | 'down' | 'same' for re-quoted; 'none' for quoted once. */
  readonly kind = new Map<string, 'up' | 'down' | 'same' | 'none'>()
  readonly won = new Set<string>()
  readonly lead: number
  readonly minChange: number
  readonly budget: number
  readonly declined: number

  constructor(lead: number, minChange: number, budget: number, declined: number) {
    this.lead = lead
    this.minChange = minChange
    this.budget = budget
    this.declined = declined
  }

  observe(event: DeskEvent): void {
    if (event.kind === 'order_won') this.won.add(event.order.id)
  }

  /** A quote the desk sent. The first one opens the request; a later one is its re-quote. */
  sent(request: PriceRequest | undefined, prices: Prices): void {
    if (!request) return
    const open = this.open.get(request.id)
    if (!open) {
      if (!this.kind.has(request.id)) {
        this.open.set(request.id, { request, first: prices, requoted: false })
        this.kind.set(request.id, 'none')
      }
      return
    }
    open.requoted = true
    this.kind.set(request.id, this.direction(request, open.first, prices))
  }

  /** The earliest minute a request still waits for its re-quote. */
  wakeAt(now: number): number {
    let at = Number.POSITIVE_INFINITY
    for (const [id, open] of this.open) {
      if (open.request.respondBy <= now) this.open.delete(id)
      else if (!open.requoted) at = Math.min(at, Math.max(now, open.request.respondBy - this.lead))
    }
    return at
  }

  /** The re-quotes due now: `price` is the strategy's answer with the belief of now (null: decline). */
  due(now: number, price: (request: PriceRequest) => Prices | null): Action[] {
    const actions: Action[] = []
    const ready = [...this.open.values()]
      .filter((o) => !o.requoted && o.request.respondBy - this.lead <= now && now < o.request.respondBy)
      .sort((a, b) => a.request.respondBy - b.request.respondBy)
    for (const open of ready) {
      if (actions.length >= this.budget) break
      open.requoted = true // asked once, sent or not
      const request = open.request
      const fresh = price(request) ?? this.decline(request)
      if (!this.differs(request, open.first, fresh)) continue
      actions.push({ type: 'quote', requestId: request.id, prices: fresh })
    }
    return actions
  }

  private decline(request: PriceRequest): Prices {
    const first = request.options[0]!
    return { [first.kind]: first.listPriceCents * this.declined }
  }

  private offered(request: PriceRequest, prices: Prices): string[] {
    return request.options
      .filter((o) => (prices[o.kind] ?? Number.POSITIVE_INFINITY) < this.declined * o.listPriceCents)
      .map((o) => o.kind)
  }

  private differs(request: PriceRequest, a: Prices, b: Prices): boolean {
    const offA = this.offered(request, a)
    const offB = this.offered(request, b)
    if (offA.join() !== offB.join()) return true
    return offA.some((k) => {
      const pa = a[k as keyof Prices] ?? 0
      const pb = b[k as keyof Prices] ?? 0
      return Math.abs(pb - pa) >= this.minChange * pa
    })
  }

  private direction(request: PriceRequest, a: Prices, b: Prices): 'up' | 'down' | 'same' {
    const offA = this.offered(request, a)
    const offB = this.offered(request, b)
    if (offB.length < offA.length) return 'up'
    if (offB.length > offA.length) return 'down'
    let delta = 0
    for (const k of offA) delta += (b[k as keyof Prices] ?? 0) - (a[k as keyof Prices] ?? 0)
    return delta > 0 ? 'up' : delta < 0 ? 'down' : 'same'
  }

  summary(): string {
    let up = 0
    let down = 0
    let same = 0
    let rq = 0
    let rqWon = 0
    let once = 0
    let onceWon = 0
    for (const [id, kind] of this.kind) {
      const won = this.won.has(id)
      if (kind === 'none') {
        once++
        if (won) onceWon++
        continue
      }
      rq++
      if (won) rqWon++
      if (kind === 'up') up++
      else if (kind === 'down') down++
      else same++
    }
    const pct = (a: number, b: number) => (b > 0 ? `${((100 * a) / b).toFixed(0)}%` : 'n/a')
    return `requoted ${rq} (up ${up}, down ${down}, same ${same}), won ${pct(rqWon, rq)} of requoted against ${pct(onceWon, once)} of quoted once`
  }
}
