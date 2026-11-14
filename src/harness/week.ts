/** Plays one week with one strategy: builds the strategy, the desk and the loop, and prints the end. */
import { type Client, type Score, SpreadError, Unreachable, type World } from '../../vendor/spread-typescript/spread.ts'
import { allEvents, Recorder } from '../record.ts'
import { STRATEGIES } from '../strategies/index.ts'
import { starterGig } from '../strategies/starter/gig.ts'
import { type Books, type GigNeed, type GigPlan, Strategy } from '../strategy.ts'
import { Desk } from './desk.ts'
import { Guard } from './guard.ts'
import { type Loop, playLive, playPractice } from './loops.ts'
import type { Run } from './params.ts'
import { counts, report } from './report.ts'

/** Runs `task` until the server answers it. An unreachable server is waited out for as long as it takes: the week
 * goes on without us, so we come back the second the server does. With `stubborn`, for the final, so is any other
 * error, once it is printed: a final that stops plays on without us. The pause keeps a crash that repeats from eating
 * the read budget. */
export async function reachable<T>(task: () => Promise<T>, stubborn = false): Promise<T> {
  while (true) {
    try {
      return await task()
    } catch (error) {
      if (!(error instanceof Unreachable) && !stubborn) throw error
      const why = error instanceof SpreadError ? `spread: ${error.message}` : ((error as Error)?.stack ?? String(error))
      console.error(`${why}. Rebuilding in a second.`)
      await new Promise((done) => setTimeout(done, RETRY_MS))
    }
  }
}
const RETRY_MS = 1000

/** Plays the world from where it is now to its end, and returns its score. There is one way in, for the first start,
 * our own restart, a server that went away and a stream that broke alike: rebuild the books and a new strategy from
 * the world, its event log and our journal, then run the loop. */
async function play(world: World, run: Run, level: number, loop: Loop, stubborn = false): Promise<Score> {
  return reachable(async () => {
    const history = await allEvents(world)
    const snapshot = await world.snapshot()
    const guard = new Guard()
    const desk = new Desk(world, await build(world, run, level, guard), guard, snapshot)
    try {
      await desk.rejoin(snapshot, history)
      await loop(world, desk)
    } finally {
      await desk.settle() // so the journal holds every answer before a rebuild reads it
    }
    const score = await world.score()
    finish(score, desk)
    return score
  }, stubborn)
}

/** A practice week or a ranking run. Saves the week and returns its score. */
export async function playPracticeWeek(
  world: World,
  run: Run,
  level: number,
  seed: string | undefined,
  kind: 'practice' | 'board',
): Promise<Score> {
  const recorder = await Recorder.start(world, level, seed, kind, run)
  const score = await play(world, run, level, playPractice)
  await recorder.save()
  return score
}

/** Our copy of a final, from where it is now. Saves the week and returns its score. */
export async function playFinalWeek(world: World, run: Run, level: number): Promise<Score> {
  const recorder = await Recorder.start(world, level, undefined, 'final', run)
  const score = await play(world, run, level, playLive, true)
  await recorder.save()
  return score
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

/** Builds the strategy once, outside the guard, so that its error stops a week that plays only once (a ranking run
 * or a final) before it starts. Without a world, as before a ranking run, with an empty driver list. */
export async function tryBuild(client: Client, run: Run, level: number, world?: World): Promise<void> {
  const setup = { roster: world ? await world.roster() : [], map: await client.map(), level }
  STRATEGIES[run.name]!.build(setup, run.params)
}

/** The strategy, from the driver list, the map and the level; the decliner when it fails to build. */
async function build(world: World, run: Run, level: number, guard: Guard): Promise<Strategy> {
  const setup = { roster: await world.roster(), map: await world.client.map(), level }
  return guard.run('build', () => STRATEGIES[run.name]!.build(setup, run.params)) ?? new Declines(setup, {})
}

/** The end of a week: the score, whether it is ranked, and the strategy's line, faults and refused actions. */
function finish(score: Score, desk: Desk): void {
  report('End', score)
  console.log(
    score.ranked
      ? 'Ranked.'
      : score.wonOrders === 0
        ? 'Not ranked: no order won.'
        : 'Not ranked: the delivery minimum is 90% of the orders on time.',
  )
  if (desk.strategy instanceof Declines)
    console.log(
      `The strategy did not build (${desk.guard.messages.get('build error') || 'too slow'}): the harness declined every request.`,
    )
  const summary = desk.guard.run('summary', () => desk.strategy.summary())
  if (summary) console.log(summary)
  if (desk.guard.faults.size > 0) console.log(`Strategy faults: ${counts(desk.guard.faults)}.`)
  const slowest = [...desk.guard.slowest].map(([call, ms]) => `${call} ${Math.round(ms)} ms`)
  if (slowest.length > 0) console.log(`Slowest calls: ${slowest.join(', ')}.`)
  if (desk.refused.size > 0) console.log(`Refused actions: ${counts(desk.refused)}.`)
}
