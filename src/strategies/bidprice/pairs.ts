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
} from '../../../vendor/spread-typescript/spread.ts'
import { feeAt } from '../../models/fees/plan.ts'
import { HOUR, minutes } from '../../ops/index.ts'
import { MAX_SHARED_DRIVE } from '../../ops/gig.ts'
import { road } from '../../ops/map.ts'
import type { Books, Setup } from '../../strategy.ts'
import type { BidPriceParams } from './params.ts'

type PairParams = Pick<BidPriceParams, 'pairChains' | 'pairKm' | 'pairOpen' | 'pairSlackHours' | 'pairGiveUpHours'>

/** The orders a post carries. */
const ordersOf = (post: Pick<PostAction, 'stops'>): string[] => [...new Set(post.stops.map((stop) => stop.orderId))]

export class Pairs {
  readonly tally = { found: 0, posted: 0, booked: 0, split: 0, pairedPaid: 0, pairedTypical: 0 }

  readonly setup: Setup
  readonly params: PairParams

  constructor(setup: Setup, params: PairParams) {
    this.setup = setup
    this.params = params
  }

  /** Counts the pairs that drivers book, with their fee over the two cars' typical fees. */
  observe(event: DeskEvent, books: Books): void {
    if (event.kind !== 'gig_booked') return
    const post = books.posts.get(event.gigId)
    if (!post || ordersOf(post).length < 2) return
    this.tally.booked++
    this.tally.pairedPaid += event.feeCents
    for (const id of ordersOf(post)) this.tally.pairedTypical += books.requests.get(id)?.referenceFeeCents ?? 0
  }

  sent(action: Action, result: ActionResult, books: Books): void {
    if (!result.ok) return
    if (action.type === 'post' && ordersOf(action).length >= 2) this.tally.posted++
    if (action.type === 'withdraw') {
      const post = books.posts.get(action.gigId)
      if (post && ordersOf(post).length >= 2) this.tally.split++
    }
  }

  /** The tick's withdrawals of pairs that no longer pay their risk, then the new pairs. */
  tick(books: Books): Action[] {
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
        if (!a || !b || urgent || now >= this.latestStart(a, b) - this.params.pairGiveUpHours * HOUR)
          actions.push({ type: 'withdraw', gigId })
        continue
      }
      if (order.legs.length !== 1 || order.deliveredAt[0] != null || books.urgent.has(order.id)) continue
      singles.push({ order, gigId, post })
    }
    const used = new Set<string>()
    for (const a of singles) {
      if (used.has(a.order.id)) continue
      for (const b of singles) {
        if (b === a || used.has(b.order.id) || !this.fits(a.order, b.order, now)) continue
        used.add(a.order.id)
        used.add(b.order.id)
        this.tally.found++
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
            schedule: this.schedule(a.post.schedule, b.post.schedule, now),
          },
        )
        break
      }
    }
    return actions
  }

  summary(): string {
    const { found, posted, booked, split, pairedPaid, pairedTypical } = this.tally
    const ratio = pairedTypical > 0 ? (pairedPaid / pairedTypical).toFixed(2) : 'n/a'
    return `pairs found ${found}, posted ${posted}, booked ${booked} (${ratio} × typical), split ${split}`
  }

  /** Places within `pairKm`: by road, or the same place. */
  private near(from: string, to: string): boolean {
    return from === to || (road(this.setup.map, from, to)?.km ?? Infinity) <= this.params.pairKm
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
    if (!this.params.pairChains && !this.near(lb.delivery.placeId, la.pickup.placeId)) return false
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

  /** `pairOpen` × the sum of the two schedules from now on, never falling. */
  private schedule(a: FeeStep[], b: FeeStep[], now: number): FeeStep[] {
    const times = [now, ...[...a, ...b].map((step) => step.at).filter((at) => at > now)].sort((x, y) => x - y)
    const steps: FeeStep[] = []
    for (const at of [...new Set(times)]) {
      const feeCents = Math.round(this.params.pairOpen * (feeAt(a, at) + feeAt(b, at)))
      if (feeCents > (steps.at(-1)?.feeCents ?? 0)) steps.push({ at: Math.round(at), feeCents })
    }
    return this.setup.level === 1 ? steps.slice(-1) : steps.slice(0, 48)
  }
}
