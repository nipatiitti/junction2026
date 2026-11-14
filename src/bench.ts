/** The seed bench of the TypeScript system: plays each strategy on each seed at one level, `--jobs` weeks at once (1 by default),
 * saves every week, and prints a table and a CSV. It never plays a ranking run or a final. README.md has the options. */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { Client, type Score } from '../vendor/spread-typescript/spread.ts'
import { type Run, runFromSpec, UsageError } from './harness/params.ts'
import { deleteOnStop, parseLevel, parseSeeds, playOnNewWorld, runScript, stamp } from './harness/practice.ts'
import { euros, percent } from './harness/report.ts'

const USAGE =
  'Usage: pnpm bench [<strategy>[:<key>=<value>|<file.json>,...] ...] [--level 1-8] [--seeds spread-1..spread-5] [--jobs 1-8] [--key-env <NAME>] [--csv <file>]. Set SPREAD_URL and SPREAD_KEY first.'

type Result = { label: string; seed: string; worldId: string; score: Score }

/** One line of the table and the CSV: a week, or a strategy's mean over its weeks. */
type Line = Pick<Score, 'marginCents' | 'revenueCents' | 'wonOrders' | 'onTimeShare'> & {
  label: string
  seed: string
  worldId: string
  ranked: string
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
      jobs: { type: 'string', default: '1' },
      'key-env': { type: 'string' },
      csv: { type: 'string' },
    },
  })
  const level = parseLevel(args.level)
  const labels = positionals.length > 0 ? positionals : ['lean']
  if (new Set(labels).size !== labels.length) throw new UsageError('a strategy is named twice')
  const runs: [string, Run][] = labels.map((label) => [label, runFromSpec(label)])
  const seeds = parseSeeds(args.seeds)
  const keyEnv = args['key-env']
  if (keyEnv && !process.env[keyEnv]) throw new UsageError(`${keyEnv} is not set`)
  const client = new Client({ key: keyEnv ? process.env[keyEnv] : undefined })

  deleteOnStop()
  const jobs = Number(args.jobs)
  if (!Number.isInteger(jobs) || jobs < 1 || jobs > 8) throw new UsageError('--jobs must be 1 to 8')
  console.log(`Playing ${labels.length * seeds.length} practice weeks at level ${level}, ${jobs} at once.`)
  const results: Result[] = []
  // The weeks in order, taken by `jobs` workers: each plays one world at a time, so at most `jobs` practice slots
  // are held. A week that throws stops the others from starting a new one.
  const weeks = seeds.flatMap((seed) => runs.map(([label, run]) => ({ seed, label, run })))
  let failed = false
  const worker = async (): Promise<void> => {
    for (let week = weeks.shift(); week && !failed; week = weeks.shift()) {
      const { seed, label, run } = week
      try {
        const { worldId, score } = await playOnNewWorld(client, run, level, seed, label)
        results.push({ label, seed, worldId, score })
      } catch (error) {
        failed = true
        throw error
      }
    }
  }
  try {
    await Promise.all(Array.from({ length: jobs }, worker))
  } finally {
    // A week that throws keeps the table of the weeks before it; the error comes after.
    if (results.length > 0) writeResults(results, labels, level, args.csv)
  }
}

/** Prints the table of the weeks played and writes their CSV. */
function writeResults(results: Result[], labels: string[], level: number, csvFile: string | undefined): void {
  const played = labels.filter((label) => results.some((result) => result.label === label))
  console.log(`\n${table(results, played, level)}`)
  const file = csvFile ?? path.join('out', `bench-ts-${stamp()}.csv`)
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, csv(results, played, level))
  console.log(`\nWrote ${file}.`)
}

await runScript(main, USAGE)
