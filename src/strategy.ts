/** A strategy is a whole policy of the TypeScript dispatch system, in its own folder under src/strategies/. The
 * harness (src/harness/) plays the week, keeps the books and does the order mechanics; the strategy only decides.
 * README.md says how to write one. */
import type {
  Action,
  ActionResult,
  DeskEvent,
  DriverProfile,
  Order,
  PostAction,
  PriceRequest,
  QuoteAction,
  VisitFailedEvent,
  WorldMap,
} from '../vendor/spread-typescript/spread.ts'

/** What the harness loads once, when the week starts. */
export type Setup = { roster: DriverProfile[]; map: WorldMap; level: number }

/** A strategy's tuned values: flat JSON, so `--params <file>` and `--set key=value` can override each one. */
export type Params = Record<string, number | string | boolean>

/** The books that the harness keeps, read-only, and the clock. Rebuilt from the snapshot and the event log on a restart. */
export interface Books {
  /** The minute: in a replay on a rebuild, the minute of the event or journal line replayed. */
  readonly now: number
  readonly endsAt: number
  /** Every request of the week, by id. A quote that has not won by the request's `respondBy` has lost. */
  readonly requests: ReadonlyMap<string, PriceRequest>
  /** The orders won and not cancelled. */
  readonly orders: ReadonlyMap<string, Order>
  /** Gig id -> the post that made it. After a rebuild, also every finished gig of the snapshot. */
  readonly posts: ReadonlyMap<string, PostAction>
  /** Order id -> leg -> the gig that carries the leg, for the legs not delivered. */
  readonly legGigs: ReadonlyMap<string, ReadonlyMap<number, string>>
  /** The gigs that a driver holds now. */
  readonly booked: ReadonlySet<string>
  /** The orders whose deadline warning has come. */
  readonly urgent: ReadonlySet<string>
  /** The gigs that carry the order's undelivered legs. */
  gigsOf(orderId: string): string[]
}

/** A price for each option offered. */
export type Prices = QuoteAction['prices']

/** Why the harness needs a gig for some legs of an order. */
export type GigWhy =
  | 'won' // the order is new
  | 'changed' // the dealer changed the order, and its gigs were withdrawn
  | 'split' // a trade-in refused as one gig goes as one gig per car
  | 'retry' // a visit failed: see `failed`
  | 'repost' // one of the gig's windows ended before a driver booked it: see `previous`
  | 'urgent' // the deadline warning came: only the schedule counts, as a reprice of `previous`
  | 'lost' // no gig carries the legs, and none waits: after a refused post, or a change to another order of a combined gig

export type GigNeed = {
  why: GigWhy
  order: Order
  /** The legs of `order` that the gig carries. */
  legs: number[]
  /** For a retry: why the visit failed. */
  failed?: VisitFailedEvent['reason']
  /** For a repost or an urgent reprice: the post that made the gig. */
  previous?: PostAction
}

/** A gig to post: its stops, audience and fee schedule. */
export type GigPlan = Omit<PostAction, 'type'>

/** The base of every strategy. It is built from the setup and its params; every call gets the books. The harness
 * runs each call within a time budget and takes a safe action when one throws or answers late, so a strategy may
 * throw. Its state must be rebuildable from `observe` over the event log and `sent` over the journal: after a restart
 * the harness builds a new strategy and feeds it both, merged in order, before it asks anything. */
export abstract class Strategy<P extends Params = Params> {
  readonly setup: Setup
  readonly params: P
  /** Minutes between two calls of `tick`; null for no tick. */
  readonly every: number | null = null

  constructor(setup: Setup, params: P) {
    this.setup = setup
    this.params = params
  }

  /** Learns from one event of the week, also one that needs no answer. Called before the harness acts on it. */
  observe(_event: DeskEvent, _books: Books): void {}

  /** The answer to a price request: a price for each option offered, or null to decline. */
  abstract quote(request: PriceRequest, books: Books): Prices | null

  /** The gig for some legs of an order, or several gigs that share them. The harness posts every plan, and posts
   * any leg of `need.legs` that no plan carries with the starter's plan. */
  abstract gig(need: GigNeed, books: Books): GigPlan | GigPlan[]

  /** Whether to wait with the gig for these legs instead of posting it now, as when the cars may join a gig with
   * cars still to come. The harness asks again on every sweep, and the legs have no gig until the answer is false or
   * a tick action posts them. */
  hold(_need: GigNeed, _books: Books): boolean {
    return false
  }

  /** Learns what became of one action the harness sent for the strategy (quote, post, reprice, withdraw, offer): the
   * action as it went out, also when the harness sent the safe one instead, and the world's answer (`ok` with the gig
   * id, or the refusal). Called once for each action, and again in order on a rebuild, from the journal. */
  sent(_action: Action, _result: ActionResult, _books: Books): void {}

  /** Any actions, every `every` minutes: reprice, withdraw, direct offers, combined gigs. The harness keeps the
   * books of the posts and withdrawals it sends. */
  tick(_books: Books): Action[] {
    return []
  }

  /** One line on the strategy's week, printed at the end; empty for none. */
  summary(): string {
    return ''
  }
}

/** A strategy as the registry knows it: its default params, and how to build it. */
export type StrategyKind<P extends Params = Params> = {
  defaults: P
  build(setup: Setup, params: P): Strategy<P>
}
