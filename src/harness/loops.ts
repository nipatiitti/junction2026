/** The two ways to play a week, behind one desk: the practice loop steps the world with `advance`, the live loop
 * answers the event stream of a final. The strategy cannot tell them apart. */
import type { DeskEventKind, World } from '../../vendor/spread-typescript/spread.ts'
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

/** A way to play a desk to the end of its world. `after` is the last event the desk has seen. */
export type Loop = (world: World, desk: Desk, after: number) => Promise<void>

/** Steps the world from one event that needs an answer to the next, and stops at each midnight for a report and
 * when the strategy's tick is due. */
export async function playPractice(world: World, desk: Desk): Promise<void> {
  while (desk.now < desk.endsAt) {
    const day = Math.floor(desk.now / DAY)
    const midnight = (day + 1) * DAY
    // One request a step: the advance applies the outbox, then moves the clock.
    const actions = desk.outbox.splice(0)
    const max = Math.min(desk.endsAt, midnight, desk.nextTick)
    const step = await world.advance({ untilEvent: WAKE_ON, max, actions })
    desk.readResults(actions, step.results)
    desk.now = step.now
    for (const event of step.events) await desk.handle(event)
    desk.tick()
    if (Math.floor(desk.now / DAY) > day) report(WEEKDAYS[day % 7]!, await world.score())
  }
}

/** Answers events as they come. After a second without an event, it reads the clock. */
export async function playLive(world: World, desk: Desk, after: number): Promise<void> {
  if (desk.now >= desk.endsAt) return
  await desk.send()
  for await (const event of world.stream({ after, idleMs: 1000 })) {
    const day = Math.floor(desk.now / DAY)
    desk.now = event === null ? (await world.client.final()).now : Math.max(desk.now, event.at)
    if (event !== null) await desk.handle(event)
    desk.tick()
    await desk.send()
    if (Math.floor(desk.now / DAY) > day) report(WEEKDAYS[day % 7]!, await world.score())
    if (desk.now >= desk.endsAt) return
  }
}
