/** The competitor's outage (HANDBOOK.md, level 6): on one working day, from 08:00 to 18:00, dealers within 80 km of
 * one town turn to a backup about 30% dearer. The saved weeks show it on the pickup side (the dealer's yard): our
 * quotes at 1.4 × list and above win 74-94% there against 26-39% in the same region on other days.
 *
 * The watch keeps, per candidate centre town, today's surprise since 08:00: the sum of (won − chance) over our
 * answered quotes with the pickup within 80 km, and its variance. A region whose z passes `outageProbeZ` gets its
 * next quotes priced with the lift (a probe); one whose z passes `outageZ` is out until 18:00. Quotes priced with the
 * lift are kept out of the win model, so they move neither the world nor the day level. On the day the price war is
 * seen there is no outage, and on an outage day the war is not followed. State comes from `observe` and `sent` only. */
import type { DeskEvent, PriceRequest, WorldMap } from '../../../vendor/spread-typescript/types.ts'
import { inWar, type Option, type QuoteParams, type QuoteState, winProb } from '../../models/quote/index.ts'

const DAY = 24 * 60
const OPEN = 8 * 60
const CLOSE = 18 * 60
const RADIUS_KM = 80
const DECLINED = 5

export type OutageParams = { outageLift: number; outageZ: number; outageProbeZ: number }

type Seen = { s: number; v: number; n: number }
type Sent = { place: string; chance: number; day: number; respondBy: number; lifted: boolean }

function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180
  const x = (b.lon - a.lon) * rad * Math.cos(((a.lat + b.lat) / 2) * rad)
  const y = (b.lat - a.lat) * rad
  return 6371 * Math.hypot(x, y)
}

export class OutageWatch {
  /** The candidate centres whose region holds each place. */
  readonly centresOf: Record<string, string[]> = {}
  private day = -1
  private seen: Record<string, Seen> = {}
  private sentQuotes: Record<string, Sent> = {}
  private warDay = -1
  out: { day: number; centre: string; at: number } | null = null
  readonly tally = { lifted: 0, liftedWon: 0, probes: 0 }

  readonly params: OutageParams

  constructor(map: WorldMap, params: OutageParams) {
    this.params = params
    for (const p of map.places) this.centresOf[p.id] = []
    for (const c of map.places) for (const p of map.places) if (km(c, p) <= RADIUS_KM) this.centresOf[p.id]?.push(c.id)
  }

  /** Whether the outage is on for this request now: its pickup is in today's out region, before 18:00. */
  active(request: PriceRequest, now: number): boolean {
    const out = this.out
    if (!out || out.day !== Math.floor(now / DAY) || now % DAY >= CLOSE) return false
    return this.centresOf[pickupOf(request)]?.includes(out.centre) ?? false
  }

  /** Whether today is the outage day (so no price war today). */
  outToday(now: number): boolean {
    return this.out?.day === Math.floor(now / DAY)
  }

  /** Whether to price this request with the lift: the region is out, or (no outage found yet this week) a region
   * of its pickup is already surprising enough to probe. */
  lifts(request: PriceRequest, now: number): boolean {
    if (this.active(request, now)) return true
    if (!this.open(now) || this.out) return false
    return (this.centresOf[pickupOf(request)] ?? []).some((c) => {
      const s = this.seen[c]
      return s !== undefined && s.n >= 2 && z(s) >= this.params.outageProbeZ
    })
  }

  /** The request as the win curve shifted up by the lift sees it: each list price times the lift. */
  lifted(request: PriceRequest): PriceRequest {
    const lift = this.params.outageLift
    return { ...request, options: request.options.map((o) => ({ ...o, listPriceCents: o.listPriceCents * lift })) }
  }

  /** A quote sent. Returns true when the watch keeps it (priced with the lift), so the win model must not. */
  sent(
    request: PriceRequest,
    prices: Partial<Record<Option, number>>,
    now: number,
    state: QuoteState,
    params: QuoteParams,
  ): boolean {
    let chance = 0
    let real = false
    for (const o of request.options) {
      const price = prices[o.kind]
      if (price === undefined || price >= DECLINED * o.listPriceCents) continue
      real = true
      chance = Math.max(chance, winProb(price, o.kind, request, state, params))
    }
    const lifted = this.lifts(request, now)
    if (!real) return lifted
    if (lifted) {
      this.tally.lifted++
      if (!this.active(request, now)) this.tally.probes++
    }
    this.sentQuotes[request.id] = {
      place: pickupOf(request),
      chance,
      day: Math.floor(now / DAY),
      respondBy: request.respondBy,
      lifted,
    }
    return lifted
  }

  /** Every event, before the win model sees it. */
  observe(event: DeskEvent, state: QuoteState, params: QuoteParams): void {
    const now = event.at
    const day = Math.floor(now / DAY)
    if (day !== this.day) {
      this.day = day
      this.seen = {}
    }
    if (!this.outToday(now) && inWar(state, now, { ...params, flags: { ...params.flags, war: 'decline' } }))
      this.warDay = day
    for (const [id, q] of Object.entries(this.sentQuotes)) if (q.respondBy < now) this.answer(id, false, now, state)
    if (event.kind === 'order_won') this.answer(event.order.id, true, now, state)
    else if (event.kind === 'order_lost') this.answer(event.requestId, false, now, state)
  }

  summary(): string {
    const { lifted, liftedWon, probes } = this.tally
    const out = this.out
    const found = out
      ? `day ${out.day} ${out.centre} at ${String(Math.floor((out.at % DAY) / 60)).padStart(2, '0')}:${String(out.at % 60).padStart(2, '0')}`
      : 'none'
    return `outage ${found}, lifted ${lifted} (${probes} probes) won ${liftedWon}`
  }

  private open(now: number): boolean {
    const minute = now % DAY
    const day = Math.floor(now / DAY)
    return day % 7 < 5 && minute >= OPEN && minute < CLOSE && day !== this.warDay
  }

  private answer(id: string, won: boolean, now: number, state: QuoteState): void {
    const q = this.sentQuotes[id]
    if (!q) return
    delete this.sentQuotes[id]
    if (q.lifted && won) this.tally.liftedWon++
    if (q.day !== this.day || !this.open(now) || this.out) return
    let best: { centre: string; z: number } | null = null
    for (const c of this.centresOf[q.place] ?? []) {
      const s = this.seen[c] ?? { s: 0, v: 0, n: 0 }
      s.s += (won ? 1 : 0) - q.chance
      s.v += q.chance * (1 - q.chance)
      s.n += 1
      this.seen[c] = s
      const zc = z(s)
      if (s.n >= 3 && zc >= this.params.outageZ && (!best || zc > best.z)) best = { centre: c, z: zc }
    }
    if (!best) return
    this.out = { day: this.day, centre: best.centre, at: now }
    // The region's quotes still waiting for an answer leave the win model too.
    for (const [rid, p] of Object.entries(state.pending)) {
      const sent = this.sentQuotes[rid]
      if (p.day === this.day && sent && this.centresOf[sent.place]?.includes(best.centre)) delete state.pending[rid]
    }
  }
}

function z(s: Seen): number {
  return s.s / Math.sqrt(s.v + 0.25)
}

function pickupOf(request: PriceRequest): string {
  return request.legs[0]?.pickup.placeId ?? ''
}
