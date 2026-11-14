/** Plays one lean week on the offline simulator (sim/world.ts) in this process, for the rollout (rollout.ts): the
 * harness's own desk and practice loop, on a world object that calls the simulator's functions instead of a server.
 * Nothing here builds the Spread client or opens a connection: the only world this code can reach is the simulator
 * in memory. Import it from the rollout's worker or a script only: it loads the simulator. */
import * as sim from '../../../sim/world.ts'
import type { Action, Score, World } from '../../../vendor/spread-typescript/spread.ts'
import { Desk } from '../../harness/desk.ts'
import { Guard } from '../../harness/guard.ts'
import type { Journal } from '../../harness/journal.ts'
import { playPractice } from '../../harness/loops.ts'
import { DEFAULTS, type LeanParams, lean } from './index.ts'
import { Features, type Marks } from './rollout.ts'

/** A copy, as the server's JSON would be: the simulator keeps and changes the objects it hands out. */
const copy = <T>(value: T): T => (value === undefined ? value : JSON.parse(JSON.stringify(value)))

/** The simulator's world behind the calls that the desk and the practice loop make. It has no client but `map`. */
function simWorld(seed: string): World {
  const W = sim.createWorld(seed, 8)
  const world = {
    id: W.worldId,
    client: { map: async () => sim.MAP },
    snapshot: async () => copy(sim.snapshot(W)),
    roster: async () => copy(sim.roster(W)),
    score: async () => copy(sim.score(W)),
    events: async (after = -1, limit?: number) => copy(sim.events(W, after, limit)),
    act: async (actions: readonly Action[]) => copy(sim.act(W, copy(actions) as Action[])),
    advance: async (body: Record<string, unknown>) => {
      const step = copy(sim.advance(W, copy(body)))
      return { results: [], ...step }
    },
  }
  return world as unknown as World
}

/** A journal that keeps nothing: a simulated week is never rebuilt. */
const NO_JOURNAL = { file: '', read: () => [], write: () => {} } as unknown as Journal

export type Played = { score: Score; marks: Marks[]; drivers: number; roster: string }

/** Lean's week on the simulator's `seed` with `params` (the defaults, overridden), and what the week looked like at
 * each minute of `at` (rollout.ts, `Marks`). The lines that the practice loop prints each midnight are dropped. */
export async function playWeek(seed: string, params: Partial<LeanParams>, at: number[] = []): Promise<Played> {
  const world = simWorld(seed)
  const roster = await world.roster()
  const setup = { roster, map: await world.client.map(), level: 8 }
  const strategy = lean.build(setup, { ...DEFAULTS, ...params, rollout: 0 })
  const features = new Features(roster.length, at)
  const observe = strategy.observe.bind(strategy)
  const sent = strategy.sent.bind(strategy)
  strategy.observe = (event, books) => {
    features.observe(event, books)
    observe(event, books)
  }
  strategy.sent = (action, result, books) => {
    features.sent(action, result)
    sent(action, result, books)
  }
  const snapshot = await world.snapshot()
  const desk = new Desk(world, strategy, new Guard(), snapshot, NO_JOURNAL)
  const log = console.log
  const error = console.error
  console.log = () => {}
  console.error = () => {}
  try {
    await desk.rejoin(snapshot, [])
    await playPractice(world, desk)
    await desk.settle()
  } finally {
    console.log = log
    console.error = error
  }
  return { score: await world.score(), marks: features.marks, drivers: roster.length, roster: Features.print(roster) }
}
