/** trustRush: build the big dealers' trust fast. Trust rises by one per order delivered on time (capped at 25) and a
 * late order halves it, so for a dealer that sends at least `rushShare` of the requests so far and whose count is
 * under `rushUntil`, the fastest option we serve is priced to win (its cost lowered by the trust a win pays back) and
 * the order is protected from lateness (stricter admission slack, higher opening fee). All state comes from
 * `observe` and `sent`, so a rebuild holds the same counts. */
import type { DeliveryOption, DeskEvent, FeeStep } from '../../../vendor/spread-typescript/spread.ts'

const WEEK = 7 * 1440
const DAY = 1440

export type RushParams = {
  trustRush: boolean
  rushShare: number
  rushUntil: number
  rushValueCents: number
  rushComfortHours: number
  rushFee: number
}

export type RushState = {
  requests: Map<string, number>
  total: number
  trust: Map<string, number>
  orders: Map<string, { dealer: string; deadline: number; left: number }>
  rushIds: Set<string>
  sent: number
  won: number
  /** Each dealer's count at the end of Monday, Tuesday and Wednesday. */
  ends: Map<string, number>[]
}

export function newRush(): RushState {
  return {
    requests: new Map(),
    total: 0,
    trust: new Map(),
    orders: new Map(),
    rushIds: new Set(),
    sent: 0,
    won: 0,
    ends: [],
  }
}

export function observeRush(s: RushState, e: DeskEvent): void {
  while (s.ends.length < 3 && e.at >= (s.ends.length + 1) * DAY) s.ends.push(new Map(s.trust))
  if (e.kind === 'price_request') {
    s.total++
    s.requests.set(e.request.dealerId, (s.requests.get(e.request.dealerId) ?? 0) + 1)
  } else if (e.kind === 'order_won') {
    const o = e.order
    s.orders.set(o.id, { dealer: o.dealerId, deadline: o.deadline, left: o.legs.length })
    if (s.rushIds.has(o.id)) s.won++
  } else if (e.kind === 'order_changed') {
    const o = s.orders.get(e.order.id)
    if (o) o.deadline = e.order.deadline
  } else if (e.kind === 'delivered') {
    const o = s.orders.get(e.orderId)
    if (o && --o.left === 0) {
      const t = s.trust.get(o.dealer) ?? 0
      s.trust.set(o.dealer, e.at > o.deadline ? t / 2 : Math.min(25, t + 1))
    }
  }
}

/** Whether this dealer's quotes and orders are rushed now. */
export function isRush(s: RushState, p: RushParams, dealer: string): boolean {
  if (!p.trustRush || s.total < 20) return false
  const share = (s.requests.get(dealer) ?? 0) / s.total
  return share >= p.rushShare && (s.trust.get(dealer) ?? 0) < p.rushUntil
}

/** The cost cut on the fastest option for a rushed dealer: `rushValueCents` x remaining-week share x the dealer's
 * share, at most a quarter of the cost, so the price stays above the cost. */
export function rushCut(
  s: RushState,
  p: RushParams,
  dealer: string,
  option: DeliveryOption,
  options: DeliveryOption[],
  now: number,
  cost: number,
): number {
  if (!isRush(s, p, dealer) || options[0]?.kind !== option.kind) return 0
  const share = (s.requests.get(dealer) ?? 0) / s.total
  const left = Math.max(0, 1 - now / WEEK)
  return Math.min(0.25 * Math.max(0, cost), p.rushValueCents * left * share)
}

/** The opening fee raised by `rushFee` for a rushed dealer's order: a step at the first fee times the factor. */
export function rushOpen(schedule: FeeStep[], p: RushParams): FeeStep[] {
  const first = schedule[0]
  if (!first || p.rushFee <= 1) return schedule
  const top = Math.round(first.feeCents * p.rushFee)
  return schedule.map((step) => (step.feeCents < top ? { ...step, feeCents: top } : step))
}

export function rushSummary(s: RushState): string {
  const big = [...s.requests.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
  const days = big.map(([d]) => `${d} ${s.ends.map((m) => (m.get(d) ?? 0).toFixed(0)).join('/')}`).join(' ')
  return `rush quotes ${s.sent} won ${s.won}, trust Mon/Tue/Wed ${days}`
}
