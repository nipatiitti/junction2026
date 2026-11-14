/** Round trips (`pairs`): two of our one-car orders that no driver holds yet, where B's pickup is near A's delivery
 * and B's delivery near A's pickup, go as ONE gig with both legs in order, so a driver carries two cars without the
 * trip home in between (HANDBOOK "a return leg"). The tick withdraws the two single gigs and posts the pair at
 * `pairOpen` × the sum of their schedules; a pair that a driver has not booked `pairGiveUpHours` before its first
 * pickup must start, or whose order turns urgent, is withdrawn, and the desk's sweep posts the cars alone again.
 * State is read from the books (the posts the world accepted) and the counters from `observe` and `sent`. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  FeeStep,
  Order,
  PostAction,
  PriceRequest,
} from '../../../vendor/spread-typescript/spread.ts'
import { feeAt } from '../../models/fees/plan.ts'
import { MAX_SHARED_DRIVE } from '../../ops/gig.ts'
import { HOUR, minutes } from '../../ops/index.ts'
import { road } from '../../ops/map.ts'
import type { Books, Setup } from '../../strategy.ts'
import type { BidPriceParams } from './params.ts'

type PairParams = Pick<
  BidPriceParams,
  'pairChains' | 'pairChainOpen' | 'pairCostCut' | 'pairKm' | 'pairOpen' | 'pairSlackHours' | 'pairGiveUpHours'
>

/** The orders a post carries. */
export const ordersOf = (post: Pick<PostAction, 'stops'>): string[] => [
  ...new Set(post.stops.map((stop) => stop.orderId)),
]

/** The learners' id of a pair's second order: its share of the gig lives under the gig's id with this suffix. */
export const TWIN = '#pair'

/** Each order of a gig of several orders with its share of the fee, by typical fees; null for one order. */
export function sharesOf(
  stops: PostAction['stops'],
  typical: (orderId: string) => number,
): { orderId: string; share: number }[] | null {
  const ids = ordersOf({ stops })
  if (ids.length !== 2) return null
  const fees = ids.map((id) => Math.max(1, typical(id)))
  const total = fees[0]! + fees[1]!
  return ids.map((orderId, i) => ({ orderId, share: fees[i]! / total }))
}

export const scaled = (schedule: FeeStep[], k: number): FeeStep[] =>
  schedule.map((step) => ({ at: step.at, feeCents: Math.round(step.feeCents * k) }))

/** A gig event of a pair as the two orders' shares: the first under the gig's id, the second under its twin. */
export function splitEvent(event: DeskEvent, twins: Map<string, number>): DeskEvent[] {
  const gigId = 'gigId' in event ? event.gigId : undefined
  const share = gigId === undefined ? undefined : twins.get(gigId)
  if (gigId === undefined || share === undefined) return [event]
  const part = (k: number, id: string) =>
    ({ ...event, gigId: id, ...('feeCents' in event ? { feeCents: Math.round(event.feeCents * k) } : {}) }) as DeskEvent
  return [part(share, gigId), part(1 - share, gigId + TWIN)]
}

/** `k` × the sum of the schedules from now on, never falling. */
export function sumSchedules(list: FeeStep[][], now: number, k: number, level: number): FeeStep[] {
  const times = [
    now,
    ...list
      .flat()
      .map((step) => step.at)
      .filter((at) => at > now),
  ].sort((x, y) => x - y)
  const steps: FeeStep[] = []
  for (const at of [...new Set(times)]) {
    const feeCents = Math.round(k * list.reduce((sum, s) => sum + feeAt(s, at), 0))
    if (feeCents > (steps.at(-1)?.feeCents ?? 0)) steps.push({ at: Math.round(at), feeCents })
  }
  return level === 1 ? steps.slice(-1) : steps.slice(0, 48)
}

export class Pairs {
  readonly tally = {
    found: 0,
    chains: 0,
    posted: 0,
    booked: 0,
    split: 0,
    pairedPaid: 0,
    pairedTypical: 0,
    cut: 0,
    cutWon: 0,
    cutPaired: 0,
  }
  /** The requests quoted with the pair cut. */
  readonly cutIds = new Set<string>()

  readonly setup: Setup
  readonly params: PairParams

  constructor(setup: Setup, params: PairParams) {
    this.setup = setup
    this.params = params
  }

  /** Counts the pairs that drivers book, with their fee over the two cars' typical fees. */
  observe(event: DeskEvent, books: Books): void {
    if (event.kind === 'order_won' && this.cutIds.has(event.order.id)) this.tally.cutWon++
    if (event.kind !== 'gig_booked') return
    const post = books.posts.get(event.gigId)
    if (!post || ordersOf(post).length < 2) return
    this.tally.booked++
    this.tally.pairedPaid += event.feeCents
    for (const id of ordersOf(post)) this.tally.pairedTypical += books.requests.get(id)?.referenceFeeCents ?? 0
  }

  sent(action: Action, result: ActionResult, books: Books): void {
    if (!result.ok) return
    if (action.type === 'quote' && this.cutIds.has(action.requestId)) this.tally.cut++
    if (action.type === 'post' && ordersOf(action).length >= 2) {
      this.tally.posted++
      this.tally.cutPaired += ordersOf(action).filter((id) => this.cutIds.has(id)).length
    }
    if (action.type === 'withdraw') {
      const post = books.posts.get(action.gigId)
      if (post && ordersOf(post).length >= 2) this.tally.split++
    }
  }

  /** The tick's withdrawals of pairs that no longer pay their risk, then the new pairs. */
  tick(books: Books, stale: (gigId: string) => boolean = () => false): Action[] {
    const actions: Action[] = []
    const now = books.now
    const singles: { order: Order; gigId: string; post: PostAction }[] = []
    const seen = new Set<string>()
    for (const order of books.orders.values()) {
      const gigs = books.gigsOf(order.id)
      if (gigs.length !== 1) continue
      const gigId = gigs[0]!
      const post = books.posts.get(gigId)
      if (!post || books.booked.has(gigId) || seen.has(gigId)) continue
      seen.add(gigId)
      const ids = ordersOf(post)
      if (ids.length >= 2) {
        const [a, b] = ids.map((id) => books.orders.get(id))
        const urgent = ids.some((id) => books.urgent.has(id))
        if (!a || !b || urgent || stale(gigId) || now >= this.latestStart(a, b) - this.params.pairGiveUpHours * HOUR)
          actions.push({ type: 'withdraw', gigId })
        continue
      }
      if (order.legs.length !== 1 || order.deliveredAt[0] != null || books.urgent.has(order.id)) continue
      singles.push({ order, gigId, post })
    }
    // Every pair that fits, the round trips first and then the shortest empty drive: each order goes once.
    const fits = singles.flatMap((a) =>
      singles.flatMap((b) => {
        if (b === a || !this.fits(a.order, b.order, now)) return []
        return [{ a, b, round: this.round(a.order, b.order), empty: this.emptyKm(a.order, b.order) }]
      }),
    )
    fits.sort((x, y) => Number(y.round) - Number(x.round) || x.empty - y.empty)
    const used = new Set<string>()
    for (const { a, b, round } of fits) {
      if (used.has(a.order.id) || used.has(b.order.id)) continue
      used.add(a.order.id)
      used.add(b.order.id)
      this.tally.found++
      if (!round) this.tally.chains++
      actions.push(
        { type: 'withdraw', gigId: a.gigId },
        { type: 'withdraw', gigId: b.gigId },
        {
          type: 'post',
          stops: [...a.post.stops, ...b.post.stops],
          audience: {
            experienced: a.post.audience.experienced || b.post.audience.experienced,
            manualLicence: a.post.audience.manualLicence || b.post.audience.manualLicence,
          },
          schedule: this.schedule(a.post.schedule, b.post.schedule, now, round),
        },
      )
    }
    return actions
  }

  /** The quote side: 1 − `pairCostCut` for a one-car request that would make a round trip (a chain too with
   * `pairChains`) after one of our open one-car orders that no driver holds, by places and the 12-hour rule; 1
   * otherwise. */
  costFactor(request: PriceRequest, books: Books): number {
    const cut = this.params.pairCostCut
    const lr = request.legs[0]
    if (cut <= 0 || request.legs.length !== 1 || !lr) return 1
    const map = this.setup.map
    const now = books.now
    const driveR = minutes(map, lr.pickup.placeId, lr.delivery.placeId)
    for (const order of books.orders.values()) {
      const lo = order.legs[0]
      const gigs = books.gigsOf(order.id)
      if (!lo || order.legs.length !== 1 || gigs.length !== 1 || books.booked.has(gigs[0]!)) continue
      if (books.urgent.has(order.id) || order.deliveredAt[0] != null) continue
      if (order.lastPickupAt < now + (this.params.pairGiveUpHours + 2) * HOUR) continue
      if (!this.near(lo.delivery.placeId, lr.pickup.placeId)) continue
      if (!this.params.pairChains && !this.near(lr.delivery.placeId, lo.pickup.placeId)) continue
      const driveO = minutes(map, lo.pickup.placeId, lo.delivery.placeId)
      if (driveO + minutes(map, lo.delivery.placeId, lr.pickup.placeId) + driveR > MAX_SHARED_DRIVE) continue
      this.cutIds.add(request.id)
      return 1 - cut
    }
    return 1
  }

  summary(): string {
    const { found, chains, posted, booked, split, pairedPaid, pairedTypical } = this.tally
    const ratio = pairedTypical > 0 ? (pairedPaid / pairedTypical).toFixed(2) : 'n/a'
    const { cut, cutWon, cutPaired } = this.tally
    return `pairs found ${found} (${chains} chains), posted ${posted}, booked ${booked} (${ratio} × typical), split ${split}, cut quotes ${cut}, won ${cutWon}, paired ${cutPaired}`
  }

  /** Places within `pairKm`: by road, or the same place. */
  private near(from: string, to: string): boolean {
    return from === to || (road(this.setup.map, from, to)?.km ?? Infinity) <= this.params.pairKm
  }

  /** A round trip: B ends near where A starts, so the driver is home after the second car. */
  private round(a: Order, b: Order): boolean {
    return this.near(b.legs[0]?.delivery.placeId ?? '', a.legs[0]?.pickup.placeId ?? '')
  }

  /** The drive without a car between A's delivery and B's pickup, in km. */
  private emptyKm(a: Order, b: Order): number {
    const from = a.legs[0]?.delivery.placeId ?? ''
    const to = b.legs[0]?.pickup.placeId ?? ''
    return from === to ? 0 : (road(this.setup.map, from, to)?.km ?? Infinity)
  }

  /** The latest minute the driver can start at A and still reach B's last pickup. */
  private latestStart(a: Order, b: Order): number {
    const la = a.legs[0]!
    const lb = b.legs[0]!
    const drive = minutes(this.setup.map, la.pickup.placeId, la.delivery.placeId)
    const between = minutes(this.setup.map, la.delivery.placeId, lb.pickup.placeId)
    return Math.min(a.lastPickupAt, b.lastPickupAt - drive - between)
  }

  /** A round trip (or a chain with `pairChains`) that one driver can drive with `pairSlackHours` to spare on both
   * deadlines, inside both pickup windows, under the 12-hour rule, and with time left before giving up. */
  private fits(a: Order, b: Order, now: number): boolean {
    const la = a.legs[0]!
    const lb = b.legs[0]!
    if (!this.near(la.delivery.placeId, lb.pickup.placeId)) return false
    if (!this.params.pairChains && !this.round(a, b)) return false
    const map = this.setup.map
    const driveA = minutes(map, la.pickup.placeId, la.delivery.placeId)
    const between = minutes(map, la.delivery.placeId, lb.pickup.placeId)
    const driveB = minutes(map, lb.pickup.placeId, lb.delivery.placeId)
    if (driveA + between + driveB > MAX_SHARED_DRIVE) return false
    const slack = this.params.pairSlackHours * HOUR
    // The driver needs a few hours to book and reach the first pickup.
    const startA = Math.max(now + 2 * HOUR, la.pickup.window.from)
    if (startA > la.pickup.window.to) return false
    const doneA = startA + driveA
    if (doneA + slack > a.deadline) return false
    const startB = Math.max(doneA + between, lb.pickup.window.from)
    if (startB > lb.pickup.window.to) return false
    if (startB + driveB + slack > b.deadline) return false
    return now + (this.params.pairGiveUpHours + 2) * HOUR < this.latestStart(a, b)
  }

  /** `pairOpen` × the sum of the two schedules from now on (`pairChainOpen` × for a chain that is no round trip),
   * never falling. */
  private schedule(a: FeeStep[], b: FeeStep[], now: number, round: boolean): FeeStep[] {
    const open = round ? this.params.pairOpen : this.params.pairChainOpen
    return sumSchedules([a, b], now, open, this.setup.level)
  }
}
