/** What the bench and the tuner share: seeds from the command line, one practice week on a new world, the worlds in
 * play that Ctrl-C deletes, and the way a command line script ends on an error. */
import { type Client, type Score, SpreadError, type World } from '../../vendor/spread-typescript/spread.ts'
import { type Run, UsageError } from './params.ts'
import { playPracticeWeek } from './week.ts'

export type Level = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8

/** A level from the command line. */
export function parseLevel(text: string): Level {
  const level = Number(text) as Level
  if (![1, 2, 3, 4, 5, 6, 7, 8].includes(level)) throw new UsageError('--level must be 1 to 8')
  return level
}

/** Seeds from a comma-separated list. An item is a seed, or a range of seeds that end in a number:
 * "spread-1..spread-5" or "spread-1..5". */
export function parseSeeds(text: string): string[] {
  const seeds = text.split(',').flatMap((item): string[] => {
    if (!item.includes('..')) return [item.trim()]
    const [first, last] = item.trim().split('..') as [string, string]
    const start = /^(.*?)(\d+)$/.exec(first)
    const end = /^(.*?)(\d+)$/.exec(last)
    if (!start || !end || !['', start[1]].includes(end[1]!)) throw new UsageError(`"${item}" is not a range of seeds`)
    const count = Number(end[2]) - Number(start[2]) + 1
    return Array.from({ length: Math.max(0, count) }, (_, i) => `${start[1]}${Number(start[2]) + i}`)
  })
  if (seeds.length === 0 || seeds.some((seed) => !seed) || new Set(seeds).size !== seeds.length)
    throw new UsageError(`"${text}" has no seed, an empty one or a repeated one`)
  return seeds
}

/** The date and time for a file name: 20261114-153000. */
export const stamp = (): string => new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')

/** The worlds in play, which Ctrl-C deletes. */
const playing = new Set<World>()

function remove(world: World): Promise<string> {
  return world.delete().then(
    () => `Practice world ${world.id} is deleted.`,
    () => `Practice world ${world.id} is not deleted: it holds one of your eight practice slots.`,
  )
}

/** Deletes every world in play, and says what it deleted. */
const removeAll = (): Promise<string[]> => Promise.all([...playing].map(remove))

/** On Ctrl-C, deletes every world in play and exits with `message` and what was deleted. */
export function deleteOnStop(message = 'Stopped.'): void {
  process.once('SIGINT', () => void removeAll().then((lines) => exit([message, ...lines].join(' '))))
}

/** Plays `run` on a new practice world of `seed`, saves the week and returns its world id and score. A week that
 * throws deletes its world, says so, and throws on. */
export async function playOnNewWorld(
  client: Client,
  run: Run,
  level: Level,
  seed: string,
  label: string,
): Promise<{ worldId: string; score: Score }> {
  const world = await client.create(level, { seed })
  playing.add(world)
  console.log(`Practice world ${world.id}, level ${level}: ${label} on ${seed}.`)
  try {
    const score = await playPracticeWeek(world, run, level, seed, 'practice').catch(async (error: unknown) => {
      console.error(`${label} on ${seed} stopped by the error below. ${await remove(world)}`)
      throw error
    })
    return { worldId: world.id, score }
  } finally {
    playing.delete(world)
  }
}

export function exit(message: string): never {
  console.error(message)
  process.exit(1)
}

/** Runs a script's `main`, and ends with the message and the usage on a known error. An error deletes the worlds
 * still in play first, as when two weeks run side by side and one of them throws. */
export async function runScript(main: () => Promise<void>, usage: string): Promise<void> {
  await main().catch(async (error: unknown) => {
    for (const line of await removeAll()) console.error(line)
    if (error instanceof SpreadError) exit(`spread: ${error.message}`)
    if (error instanceof UsageError) exit(`${error.message}. ${usage}`)
    if (error instanceof TypeError && 'code' in error && String(error.code).startsWith('ERR_PARSE_ARGS'))
      exit(`${error.message}. ${usage}`)
    throw error
  })
}
