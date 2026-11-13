/** The seed bench of the TypeScript system: plays each strategy on each seed at one level, one week after another,
 * saves every week, and prints a table and a CSV. It never plays a ranking run or a final. README.md has the options. */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { Client, type Score, SpreadError, type World } from '../vendor/spread-typescript/spread.ts'
import { type Run, runFromSpec, UsageError } from './harness/params.ts'
import { euros, percent } from './harness/report.ts'
import { playPracticeWeek } from './harness/week.ts'

const USAGE =
  'Usage: pnpm bench [<strategy>[:<key>=<value>|<file.json>,...] ...] [--level 1-8] [--seeds spread-1..spread-5] [--key-env <NAME>] [--csv <file>]. Set SPREAD_URL and SPREAD_KEY first.'

type Result = { label: string; seed: string; worldId: string; score: Score }

/** One line of the table and the CSV: a week, or a strategy's mean over its weeks. */
type Line = Pick<Score, 'marginCents' | 'revenueCents' | 'wonOrders' | 'onTimeShare'> & {
  label: string
  seed: string
  worldId: string
  ranked: string
}

/** Seeds from a comma-separated list. An item is a seed, or a range of seeds that end in a number:
 * "spread-1..spread-5" or "spread-1..5". */
function parseSeeds(text: string): string[] {
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

const signed = (cents: number): string => `${cents < 0 ? '-' : ''}€${euros(Math.abs(Math.round(cents)))}`
const mean = (values: number[]): number => values.reduce((sum, value) => sum + value, 0) / values.length
const orders = (count: number): string => (Number.isInteger(count) ? String(count) : count.toFixed(1))

function lines(results: Result[], labels: string[]): Line[] {
  const weeks = results.map(({ label, seed, worldId, score }) => ({
    ...score,
    label,
    seed,
    worldId,
    ranked: score.ranked ? 'yes' : 'no',
  }))
  const means = labels.map((label) => {
    const scores = results.filter((result) => result.label === label).map((result) => result.score)
    const of = (key: 'marginCents' | 'revenueCents' | 'wonOrders' | 'onTimeShare') =>
      mean(scores.map((score) => score[key]))
    const ranked = scores.filter((score) => score.ranked).length
    return {
      label,
      seed: 'mean',
      worldId: '',
      marginCents: of('marginCents'),
      revenueCents: of('revenueCents'),
      wonOrders: of('wonOrders'),
      onTimeShare: of('onTimeShare'),
      ranked: `${ranked} of ${scores.length}`,
    }
  })
  return [...weeks, ...means]
}

function table(results: Result[], labels: string[], level: number): string {
  const header = ['Strategy', 'Seed', 'Margin', 'Revenue', 'Orders', 'On time', 'Ranked']
  const rows = lines(results, labels).map((line) => [
    line.label,
    line.seed,
    signed(line.marginCents),
    signed(line.revenueCents),
    orders(line.wonOrders),
    percent(line.onTimeShare),
    line.ranked,
  ])
  const widths = header.map((_, i) => Math.max(...[header, ...rows].map((row) => row[i]!.length)))
  const format = (row: string[]) =>
    row.map((cell, i) => (i >= 2 ? cell.padStart(widths[i]!) : cell.padEnd(widths[i]!))).join('  ')
  return [`Level ${level}.`, '', format(header), ...rows.map(format)].join('\n')
}

function csv(results: Result[], labels: string[], level: number): string {
  const quoted = (value: string) => (/[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value)
  const header = 'strategy,seed,level,world_id,margin_eur,revenue_eur,won_orders,on_time_share,ranked'
  const rows = lines(results, labels).map((line) =>
    [
      line.label,
      line.seed,
      String(level),
      line.worldId,
      (line.marginCents / 100).toFixed(2),
      (line.revenueCents / 100).toFixed(2),
      orders(line.wonOrders),
      line.onTimeShare.toFixed(4),
      line.ranked,
    ]
      .map(quoted)
      .join(','),
  )
  return `${[header, ...rows].join('\n')}\n`
}

async function main(): Promise<void> {
  const { values: args, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      level: { type: 'string', default: '8' },
      seeds: { type: 'string', default: 'spread-1..spread-5' },
      'key-env': { type: 'string' },
      csv: { type: 'string' },
    },
  })
  const level = Number(args.level) as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8
  if (![1, 2, 3, 4, 5, 6, 7, 8].includes(level)) throw new UsageError('--level must be 1 to 8')
  const labels = positionals.length > 0 ? positionals : ['starter']
  if (new Set(labels).size !== labels.length) throw new UsageError('a strategy is named twice')
  const runs: [string, Run][] = labels.map((label) => [label, runFromSpec(label)])
  const seeds = parseSeeds(args.seeds)
  const keyEnv = args['key-env']
  if (keyEnv && !process.env[keyEnv]) throw new UsageError(`${keyEnv} is not set`)
  const client = new Client({ key: keyEnv ? process.env[keyEnv] : undefined })

  let playing: World | undefined // the world of the week in play
  const remove = (world: World) =>
    world.delete().then(
      () => `Practice world ${world.id} is deleted.`,
      () => `Practice world ${world.id} is not deleted: it holds one of your eight practice slots.`,
    )
  process.once('SIGINT', () => {
    if (!playing) exit('Stopped.')
    void remove(playing).then((said) => exit(`Stopped. ${said}`))
  })
  console.log(`Playing ${labels.length * seeds.length} practice weeks at level ${level}, one after another.`)
  const results: Result[] = []
  for (const seed of seeds)
    for (const [label, run] of runs) {
      const world = await client.create(level, { seed })
      playing = world
      console.log(`Practice world ${world.id}, level ${level}: ${label} on ${seed}.`)
      const score = await playPracticeWeek(world, run, level, seed, 'practice').catch(async (error: unknown) => {
        console.error(`Stopped by the error below. ${await remove(world)}`)
        throw error
      })
      playing = undefined
      results.push({ label, seed, worldId: world.id, score })
    }

  console.log(`\n${table(results, labels, level)}`)
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')
  const file = args.csv ?? path.join('out', `bench-ts-${stamp}.csv`)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, csv(results, labels, level))
  console.log(`\nWrote ${file}.`)
}

function exit(message: string): never {
  console.error(message)
  process.exit(1)
}

await main().catch((error: unknown) => {
  if (error instanceof SpreadError) exit(`spread: ${error.message}`)
  if (error instanceof UsageError) exit(`${error.message}. ${USAGE}`)
  if (error instanceof TypeError && 'code' in error && String(error.code).startsWith('ERR_PARSE_ARGS'))
    exit(`${error.message}. ${USAGE}`)
  throw error
})
