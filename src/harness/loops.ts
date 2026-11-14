/** The two ways to play a week, behind one desk: the practice loop steps the world with `advance`, the live loop
 * answers the event stream of a final. The strategy cannot tell them apart. */
import { type DeskEventKind, Unreachable, type World } from '../../vendor/spread-typescript/spread.ts'
import { DAY, WEEKDAYS } from '../time.ts'
import type { Desk } from './desk.ts'
import { report } from './report.ts'

/** The events that need an answer. Views and account lines arrive with the next event that needs an answer. */
const WAKE_ON: DeskEventKind[] = [
  'price_request',
  'order_won',
  'order_changed',
  'order_cancelled',
  'visit_failed',
  'gig_expired',
  'deadline_close',
]

/** A way to play a desk to the end of its world, from the last event that the desk has seen. */
export type Loop = (world: World, desk: Desk) => Promise<void>

/** While dealers ask for prices (weekdays, 08:00 to 18:15) the world moves in steps of this many minutes: a request
 * waits 15 minutes for its quote, so every one is answered in time, and a week takes a few hundred requests to the
 * server instead of one for each event. */
const STEP = 10
const OPENS = 8 * 60 - STEP
const CLOSES = 18 * 60 + 20
/** Outside those hours the world runs to the next event that needs an answer, and stops at least this often. */
const QUIET_STEP = 60

/** Whether a price request can be open at `minute`. */
const dealersAsk = (minute: number): boolean =>
  Math.floor(minute / DAY) % 7 < 5 && minute % DAY >= OPENS && minute % DAY < CLOSES

/** Plays a practice world to its end, one request to the server a step: the advance carries the actions decided on
 * the step before, then moves the clock, and its answer holds the new events. It stops at each midnight for a report. */
export async function playPractice(world: World, desk: Desk): Promise<void> {
  while (desk.now < desk.endsAt) {
    const day = Math.floor(desk.now / DAY)
    const midnight = (day + 1) * DAY
    await desk.settle()
    const actions = desk.outbox.splice(0)
    const asking = dealersAsk(desk.now)
    const max = Math.min(desk.endsAt, midnight, desk.now + (asking ? STEP : QUIET_STEP))
    const step = await world.advance(asking ? { to: max, actions } : { untilEvent: WAKE_ON, max, actions })
    desk.readResults(actions, step.results)
    desk.now = step.now
    for (const event of step.events) await desk.handle(event)
    await desk.tick()
    if (Math.floor(desk.now / DAY) > day) report(WEEKDAYS[day % 7]!, await world.score())
  }
}

/** Answers events as they come, while the desk sends in the background: one request in flight, and the quotes first.
 * After a second without an event it reads the clock, sweeps, and checks the stream. A stream that holds back an
 * event the server had a second before, or that ends before the week, throws Unreachable: the week is rebuilt. */
export async function playLive(world: World, desk: Desk): Promise<void> {
  if (desk.now >= desk.endsAt) return
  desk.live = true
  desk.pump()
  let missed = -Infinity // the first event that the server had and the stream had not given, at the last idle second
  for await (const event of world.stream({ after: desk.seen, idleMs: 1000 })) {
    if (desk.now >= desk.endsAt) break
    const day = Math.floor(desk.now / DAY)
    if (event !== null) await desk.handle(event)
    else {
      desk.now = Math.max(desk.now, (await world.client.final()).now)
      const [next] = await world.events(desk.seen, 1)
      if (next && next.seq <= missed) throw new Unreachable(0, `The event stream has held back event ${next.seq}`)
      missed = next?.seq ?? -Infinity
      await desk.sweep()
    }
    await desk.tick()
    desk.pump()
    if (Math.floor(desk.now / DAY) > day) report(WEEKDAYS[day % 7]!, await world.score())
    if (desk.now >= desk.endsAt) break
  }
  await desk.send()
  if (desk.now < desk.endsAt && (await world.snapshot()).now < desk.endsAt)
    throw new Unreachable(0, 'The event stream closed before the end of the week')
}
