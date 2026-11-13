/** Our TypeScript dispatch system: plays one week with one strategy on the harness in src/harness/. Run it with
 * `pnpm dispatch --strategy starter --level 8 --seed spread-1`; README.md has the options. */
import { parseArgs } from 'node:util'
import { Client, SpreadError, Unreachable, type World } from '../vendor/spread-typescript/spread.ts'
import { type Run, runOf, UsageError } from './harness/params.ts'
import { finish, playFinalWeek, playPracticeWeek } from './harness/week.ts'
import { Recorder } from './record.ts'

const USAGE =
  'Usage: pnpm dispatch [--strategy <name>] [--params <file>] [--set key=value] [--level 1-8] [--seed <text>] [--board] [--final]. Set SPREAD_URL and SPREAD_KEY first.'

/** Your copy of the final that is set or runs now. Waits while none is set and while the last one has ended:
 * the organisers set a test final 15 minutes before its start, and the final 30 minutes before. */
async function nextFinal(client: Client): Promise<World> {
  for (let said = false; ; said = true) {
    const set = await client.final().catch((error: unknown) => {
      if (error instanceof SpreadError && error.status === 404) return null
      throw error
    })
    const world = set ? client.world(set.worldId) : null
    if (world) {
      const snapshot = await world.snapshot()
      if (snapshot.now < snapshot.endsAt) return world
    }
    if (!said)
      console.log(
        'No final is set. Waiting for it: the organisers set a test final 15 minutes before its start, and the final 30 minutes before.',
      )
    await new Promise((done) => setTimeout(done, 10_000))
  }
}

/** Plays the final, and after a server restart, which drops every connection, rebuilds from the server and goes on. */
async function playFinal(client: Client, run: Run): Promise<void> {
  process.once('SIGINT', () =>
    exit('Stopped. The final world keeps running without your system; start it again with --final.'),
  )
  let world: World | undefined
  let recorder: Recorder | undefined // saves the week to data/scrape/runs once it has ended
  while (true) {
    try {
      if (!world) {
        world = await nextFinal(client)
        console.log(`Final world ${world.id}.`)
      }
      const id = world.id
      const level = (await client.worlds()).find((summary) => summary.worldId === id)?.level ?? 8
      recorder ??= await Recorder.start(world, level, undefined, 'final', run)
      const desk = await playFinalWeek(world, run, level)
      finish(await world.score(), desk)
      await recorder.save()
      return
    } catch (error) {
      if (!(error instanceof Unreachable)) throw error
      console.error(`spread: ${error.message}. Trying again in 5 seconds.`)
      await new Promise((done) => setTimeout(done, 5000))
    }
  }
}

/** Plays a practice week, or a ranking run with `board`. Ctrl-C or an error deletes a practice world. */
async function playPractice(client: Client, run: Run, level: number, seed: string | undefined, board: boolean) {
  const world = await client.create(level as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8, { seed, board })
  // A ranking run that a team deletes plays to its end without the team's system, and counts.
  const name = `${board ? 'Ranking run' : 'Practice world'} ${world.id}`
  const afterStop = (deleted: boolean) =>
    board
      ? `${name} plays to its end without your system, and counts.`
      : deleted
        ? `${name} is deleted.`
        : `${name} is not deleted: it holds one of your eight practice slots.`
  console.log(
    `${name}, level ${level}, strategy ${run.name}. ${board ? 'Ctrl-C or an error stops your system: the run then plays to its end without it, and counts.' : 'Ctrl-C or an error stops the run and deletes the world.'}`,
  )
  const remove = () =>
    world.delete().then(
      () => true,
      () => false,
    )
  process.once('SIGINT', () => void remove().then((deleted) => exit(`Stopped. ${afterStop(deleted)}`)))
  // A world left behind holds one of the team's eight practice slots.
  await playPracticeWeek(world, run, level, seed, board ? 'board' : 'practice').catch(async (error: unknown) => {
    console.error(`Stopped by the error below. ${afterStop(await remove())}`)
    throw error
  })
}

async function main(): Promise<void> {
  const { values: args } = parseArgs({
    options: {
      strategy: { type: 'string', default: 'starter' },
      params: { type: 'string', multiple: true },
      set: { type: 'string', multiple: true },
      level: { type: 'string', default: '8' },
      seed: { type: 'string' },
      board: { type: 'boolean' },
      final: { type: 'boolean' },
    },
  })
  const level = Number(args.level)
  if (![1, 2, 3, 4, 5, 6, 7, 8].includes(level)) throw new SpreadError(0, `--level must be 1 to 8. ${USAGE}`)
  const run = runOf(args.strategy, args.params, args.set)
  const client = new Client()
  if (args.final) await playFinal(client, run)
  else await playPractice(client, run, level, args.seed, args.board ?? false)
}

function exit(message: string): never {
  console.error(message)
  process.exit(1)
}

await main().catch((error: unknown) => {
  if (error instanceof SpreadError) exit(`spread: ${error.message}`)
  if (error instanceof TypeError && 'code' in error && String(error.code).startsWith('ERR_PARSE_ARGS'))
    exit(`${error.message}. ${USAGE}`)
  if (error instanceof UsageError) exit(`${error.message}. ${USAGE}`)
  throw error
})
