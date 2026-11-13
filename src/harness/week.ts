/** Plays one week with one strategy: builds the strategy, the desk and the loop, and prints the end. */
import type { Score, World } from '../../vendor/spread-typescript/spread.ts'
import { allEvents, Recorder } from '../record.ts'
import { STRATEGIES } from '../strategies/index.ts'
import { starterGig } from '../strategies/starter/gig.ts'
import { type Books, type GigNeed, type GigPlan, Strategy } from '../strategy.ts'
import { Desk } from './desk.ts'
import { Guard } from './guard.ts'
import { playLive, playPractice } from './loops.ts'
import type { Run } from './params.ts'
import { counts, report } from './report.ts'

/** A practice week or a ranking run, from its first minute to its end. Saves the week and returns its score. */
export async function playPracticeWeek(
  world: World,
  run: Run,
  level: number,
  seed: string | undefined,
  kind: 'practice' | 'board',
): Promise<Score> {
  const recorder = await Recorder.start(world, level, seed, kind, run)
  const guard = new Guard()
  const strategy = await build(world, run, level, guard)
  const desk = new Desk(world, strategy, guard, await world.snapshot())
  await playPractice(world, desk)
  const score = await world.score()
  finish(score, desk)
  await recorder.save()
  return score
}

/** Our copy of a final from where it is now: rebuilds the books and a new strategy from the world and its event log,
 * then answers the stream. Called again after a dropped connection. Returns the desk, or null when the world has ended. */
export async function playFinalWeek(world: World, run: Run, level: number): Promise<Desk | null> {
  const history = await allEvents(world)
  const snapshot = await world.snapshot()
  if (snapshot.now >= snapshot.endsAt) return null
  const guard = new Guard()
  const desk = new Desk(world, await build(world, run, level, guard), guard, snapshot)
  await desk.rejoin(snapshot, history)
  await playLive(world, desk, history.at(-1)?.seq ?? -1)
  return desk
}

/** What the harness plays when a strategy fails to build: it declines every request. */
class Declines extends Strategy {
  quote(): null {
    return null
  }

  gig(need: GigNeed, books: Books): GigPlan {
    return starterGig(need, books, this.setup.level)
  }
}

/** The strategy, from the driver list, the map and the level. */
async function build(world: World, run: Run, level: number, guard: Guard): Promise<Strategy> {
  const setup = { roster: await world.roster(), map: await world.client.map(), level }
  return guard.run('build', () => STRATEGIES[run.name]!.build(setup, run.params)) ?? new Declines(setup, {})
}

/** The end of a week: the score, whether it is ranked, and the strategy's line, faults and refused actions. */
export function finish(score: Score, desk: Desk | null): void {
  report('End', score)
  console.log(
    score.ranked
      ? 'Ranked.'
      : score.wonOrders === 0
        ? 'Not ranked: no order won.'
        : 'Not ranked: the delivery minimum is 90% of the orders on time.',
  )
  if (!desk) return
  const summary = desk.guard.run('summary', () => desk.strategy.summary())
  if (summary) console.log(summary)
  if (desk.guard.faults.size > 0) console.log(`Strategy faults: ${counts(desk.guard.faults)}.`)
  if (desk.refused.size > 0) console.log(`Refused actions: ${counts(desk.refused)}.`)
}
