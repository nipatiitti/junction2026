/** The tuner: a search over a strategy's params by successive halving on practice weeks. Every candidate plays the
 * first seed, the best share plays the next, and the last few play the rest. It plays each week as `pnpm bench` does,
 * one world at a time for each key, and keeps its state in a file so that a stopped search goes on. README.md has
 * the options. It never plays a ranking run or a final. */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { parseArgs } from 'node:util'
import { Client, SpreadError } from '../vendor/spread-typescript/spread.ts'
import { type Run, runOf, UsageError } from './harness/params.ts'
import {
  deleteOnStop,
  type Level,
  parseLevel,
  parseSeeds,
  playOnNewWorld,
  runScript,
  stamp,
} from './harness/practice.ts'
import { euros, percent } from './harness/report.ts'
import type { Params } from './strategy.ts'

const USAGE =
  'Usage: pnpm tune <strategy> --space <file.json> [--candidates 24] [--seeds spread-1..spread-5] [--holdout spread-6..spread-10] [--level 8] [--keys SPREAD_KEY,SPREAD_KEY_2] [--keep 0.34] [--finalists 3] [--min-on-time 0.93] [--resume <file>] [--dry]. Set SPREAD_URL and the keys first.'

/** A param's values: a list to pick from, or a range, drawn evenly or on a log scale, of whole numbers with `int`. */
type Range = { min: number; max: number; log?: boolean; int?: boolean }
type Space = Record<string, (number | string | boolean)[] | Range>

/** One week of the search. A week that threw has `error` and puts its candidate out. */
type Week = {
  candidate: number
  seed: string
  worldId?: string
  marginCents?: number
  onTimeShare?: number
  ranked?: boolean
  error?: string
}

/** Everything the search needs to go on: the settings, the candidates and every week played. */
type State = {
  strategy: string
  level: Level
  seeds: string[]
  holdout: string[]
  keep: number
  finalists: number
  minOnTime: number
  space: Space
  candidates: Params[]
  weeks: Week[]
}

/** The cost of a week under the on-time minimum: no margin makes up for it, so such a candidate never wins. */
const PENALTY_CENTS = 1e10
/** The seed of the random draw, so the same space gives the same candidates. */
const DRAW_SEED = 1

/** A random number generator with a fixed seed (mulberry32). */
function random(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** One value of a param from its list or range. A drawn number keeps three significant digits. */
function draw(values: Space[string], next: () => number): number | string | boolean {
  if (Array.isArray(values)) return values[Math.floor(next() * values.length)]!
  const { min, max, log, int } = values
  const value = log ? Math.exp(Math.log(min) + next() * (Math.log(max) - Math.log(min))) : min + next() * (max - min)
  return int ? Math.round(value) : Number(value.toPrecision(3))
}

/** Checks the space: each param a list of values or a range, against the strategy's params and their types. */
function checkSpace(strategy: string, space: Space): void {
  if (Object.keys(space).length === 0) throw new UsageError('the space names no param')
  for (const [key, values] of Object.entries(space)) {
    if (Array.isArray(values)) {
      if (values.length === 0) throw new UsageError(`param ${key} has an empty list`)
      for (const value of values) runOf(strategy, [], [`${key}=${JSON.stringify(value)}`])
      continue
    }
    const { min, max, log } = values ?? {}
    if (typeof min !== 'number' || typeof max !== 'number' || min > max)
      throw new UsageError(`param ${key} is neither a list nor {"min": <number>, "max": <number>} with min <= max`)
    if (log && min <= 0) throw new UsageError(`param ${key} is on a log scale, so its min must be above 0`)
    runOf(strategy, [], [`${key}=${min}`])
  }
}

/** The candidates: the strategy's defaults first, then distinct draws from the space. */
function candidatesOf(strategy: string, space: Space, count: number): Params[] {
  const defaults = runOf(strategy).params
  const candidates = [defaults]
  const seen = new Set([JSON.stringify(defaults)])
  const next = random(DRAW_SEED)
  for (let tries = 0; candidates.length < count && tries < 100 * count; tries++) {
    const pairs = Object.entries(space).map(([key, values]) => `${key}=${JSON.stringify(draw(values, next))}`)
    const { params } = runOf(strategy, [], pairs)
    const text = JSON.stringify(params)
    if (seen.has(text)) continue
    seen.add(text)
    candidates.push(params)
  }
  return candidates
}

/** The rounds: how many candidates play which seeds. One new seed a round, each round with the best `keep` share of
 * the one before, until `finalists` are left: they play every seed that is left. */
function planOf(count: number, seeds: string[], keep: number, finalists: number): { count: number; seeds: string[] }[] {
  const plan = []
  for (let i = 0; i < seeds.length; ) {
    const these = count <= finalists ? seeds.slice(i) : [seeds[i]!]
    plan.push({ count, seeds: these })
    i += these.length
    count = Math.max(Math.min(finalists, count), Math.ceil(count * keep))
  }
  return plan
}

/** A candidate's standing on the seeds it played among `seeds`. */
type Standing = {
  candidate: number
  played: number
  marginCents: number
  onTimeShare: number
  under: number
  score: number
  out: boolean
}

function standing(state: State, candidate: number, seeds: string[]): Standing {
  const weeks = state.weeks.filter((week) => week.candidate === candidate && seeds.includes(week.seed))
  const scored = weeks.filter((week) => week.error === undefined)
  const mean = (values: number[]) => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0)
  const marginCents = mean(scored.map((week) => week.marginCents!))
  const under = scored.filter((week) => week.ranked === false || week.onTimeShare! < state.minOnTime).length
  return {
    candidate,
    played: scored.length,
    marginCents,
    onTimeShare: mean(scored.map((week) => week.onTimeShare!)),
    under,
    score: marginCents - PENALTY_CENTS * under,
    out: scored.length < weeks.length,
  }
}

/** Best first: the candidates in play before those out, then by score, then the earlier candidate. */
const ranked = (standings: Standing[]): Standing[] =>
  [...standings].sort((a, b) => Number(a.out) - Number(b.out) || b.score - a.score || a.candidate - b.candidate)

const signed = (cents: number): string => `${cents < 0 ? '-' : ''}€${euros(Math.abs(Math.round(cents)))}`

/** The params that differ from the defaults, as `key=value`. */
function changes(state: State, candidate: number): string {
  const defaults = state.candidates[0]!
  const params = state.candidates[candidate]!
  const pairs = Object.keys(params).filter((key) => params[key] !== defaults[key])
  return pairs.length ? pairs.map((key) => `${key}=${params[key]}`).join(' ') : '(defaults)'
}

function table(state: State, standings: Standing[]): string {
  const header = ['#', 'Seeds', 'Margin', 'On time', 'Under', 'Params']
  const rows = standings.map((s) => [
    String(s.candidate),
    s.out ? 'out' : String(s.played),
    signed(s.marginCents),
    percent(s.onTimeShare),
    String(s.under),
    changes(state, s.candidate),
  ])
  const widths = header.map((_, i) => Math.max(...[header, ...rows].map((row) => row[i]!.length)))
  const format = (row: string[]) => row.map((cell, i) => (i < 5 ? cell.padStart(widths[i]!) : cell)).join('  ')
  return [format(header), ...rows.map(format)].join('\n')
}

/** Plays every week of `queue` that the state does not hold yet, one world at a time for each client, and saves the
 * state after every week. A week that throws is saved with its error. */
async function playAll(state: State, queue: Week[], clients: Client[], file: string): Promise<void> {
  const todo = queue.filter((w) => !state.weeks.some((week) => week.candidate === w.candidate && week.seed === w.seed))
  const worker = async (client: Client) => {
    for (let week = todo.shift(); week; week = todo.shift()) {
      const run: Run = { name: state.strategy, params: state.candidates[week.candidate]! }
      const label = `${state.strategy} #${week.candidate}`
      try {
        const { worldId, score } = await playOnNewWorld(client, run, state.level, week.seed, label)
        state.weeks.push({
          ...week,
          worldId,
          marginCents: score.marginCents,
          onTimeShare: score.onTimeShare,
          ranked: score.ranked,
        })
      } catch (error) {
        // A refused key, a full set of practice slots or the rate limit stops the search, not the candidate.
        if (error instanceof SpreadError && [401, 403, 409, 429].includes(error.status)) throw error
        console.error((error as Error)?.stack ?? String(error))
        console.error(`${label} is out.`)
        state.weeks.push({ ...week, error: String((error as Error)?.message ?? error) })
      }
      save(state, file)
    }
  }
  await Promise.all(clients.map(worker))
}

function save(state: State, file: string): void {
  mkdirSync(path.dirname(file), { recursive: true })
  writeFileSync(file, `${JSON.stringify(state, null, 2)}\n`)
}

/** The state of a new search, from the command line. */
function newState(strategy: string | undefined, args: Record<string, string | boolean | undefined>): State {
  if (!strategy) throw new UsageError('name the strategy to tune')
  if (typeof args.space !== 'string') throw new UsageError('--space names the file of the params to search')
  runOf(strategy)
  const space = JSON.parse(readFileSync(args.space, 'utf-8')) as Space
  checkSpace(strategy, space)
  const count = Number(args.candidates)
  const keep = Number(args.keep)
  const finalists = Number(args.finalists)
  const minOnTime = Number(args['min-on-time'])
  if (!Number.isInteger(count) || count < 1) throw new UsageError('--candidates must be a whole number of at least 1')
  if (!(keep > 0 && keep < 1)) throw new UsageError('--keep must be above 0 and below 1')
  if (!Number.isInteger(finalists) || finalists < 1)
    throw new UsageError('--finalists must be a whole number of at least 1')
  if (!(minOnTime >= 0 && minOnTime <= 1)) throw new UsageError('--min-on-time must be from 0 to 1')
  const seeds = parseSeeds(String(args.seeds))
  const holdout = typeof args.holdout === 'string' ? parseSeeds(args.holdout) : []
  if (holdout.some((seed) => seeds.includes(seed))) throw new UsageError('a holdout seed is also a tuning seed')
  const candidates = candidatesOf(strategy, space, count)
  if (candidates.length < count) console.log(`The space holds only ${candidates.length} distinct candidates.`)
  const level = parseLevel(String(args.level))
  return { strategy, level, seeds, holdout, keep, finalists, minOnTime, space, candidates, weeks: [] }
}

async function main(): Promise<void> {
  const { values: args, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      space: { type: 'string' },
      candidates: { type: 'string', default: '24' },
      seeds: { type: 'string', default: 'spread-1..spread-5' },
      holdout: { type: 'string' },
      level: { type: 'string', default: '8' },
      keys: { type: 'string', default: 'SPREAD_KEY' },
      keep: { type: 'string', default: '0.34' },
      finalists: { type: 'string', default: '3' },
      'min-on-time': { type: 'string', default: '0.93' },
      resume: { type: 'string' },
      dry: { type: 'boolean', default: false },
    },
  })
  if (positionals.length > 1) throw new UsageError('name one strategy')
  const file = args.resume ?? path.join('out', `tune-${stamp()}.json`)
  if (args.resume && !existsSync(args.resume)) throw new UsageError(`${args.resume} does not exist`)
  const state: State = args.resume
    ? (JSON.parse(readFileSync(args.resume, 'utf-8')) as State)
    : newState(positionals[0], args)
  const plan = planOf(state.candidates.length, state.seeds, state.keep, state.finalists)

  console.log(`Tuning ${state.strategy} at level ${state.level} on ${state.seeds.join(', ')}. The candidates:`)
  const width = String(state.candidates.length - 1).length
  for (const [i] of state.candidates.entries()) console.log(`  #${String(i).padEnd(width)}  ${changes(state, i)}`)
  console.log('The rounds:')
  for (const [i, round] of plan.entries())
    console.log(
      `  ${i + 1}. ${round.count} candidates on ${round.seeds.join(', ')}: ${round.count * round.seeds.length} weeks`,
    )
  const tuning = plan.reduce((sum, round) => sum + round.count * round.seeds.length, 0)
  const holdout = 2 * state.holdout.length
  console.log(
    `${tuning} tuning weeks${holdout ? ` and up to ${holdout} holdout weeks (the best and the defaults)` : ''}, at most; a candidate that throws plays no more.`,
  )
  if (args.dry) return

  const names = args.keys.split(',').map((name) => name.trim())
  for (const name of names) if (!process.env[name]) throw new UsageError(`${name} is not set`)
  const clients = names.map((name) => new Client({ key: process.env[name] }))
  deleteOnStop(`Stopped. Go on with: pnpm tune --resume ${file}`)
  console.log(`Playing on ${clients.length} key${clients.length > 1 ? 's' : ''}; the state is in ${file}.`)
  save(state, file)

  let alive = state.candidates.map((_, i) => i)
  const played: string[] = []
  for (const [i, round] of plan.entries()) {
    alive = alive.slice(0, round.count)
    await playAll(
      state,
      alive.flatMap((candidate) => round.seeds.map((seed) => ({ candidate, seed }))),
      clients,
      file,
    )
    played.push(...round.seeds)
    const standings = ranked(alive.map((candidate) => standing(state, candidate, played)))
    console.log(`\nRound ${i + 1} of ${plan.length}, on ${played.join(', ')}:\n${table(state, standings)}`)
    alive = standings.filter((s) => !s.out).map((s) => s.candidate)
  }
  if (alive.length === 0) throw new Error('every candidate threw: no params to report')

  const best = alive[0]!
  const bestFile = file.replace(/\.json$/, '-best.json')
  writeFileSync(bestFile, `${JSON.stringify(state.candidates[best], null, 2)}\n`)
  const line = (s: Standing, on: string) =>
    `${on}: mean margin ${signed(s.marginCents)}, on time ${percent(s.onTimeShare)}, ${s.under} of ${s.played} weeks under ${percent(state.minOnTime)}.`
  console.log(`\nThe best is #${best} (${changes(state, best)}), in ${bestFile}.`)
  console.log(line(standing(state, best, state.seeds), 'Tuning seeds'))
  if (state.holdout.length > 0) {
    const both = best === 0 ? [0] : [best, 0]
    await playAll(
      state,
      both.flatMap((candidate) => state.holdout.map((seed) => ({ candidate, seed }))),
      clients,
      file,
    )
    console.log(
      `\nOn the holdout seeds, ${state.holdout.join(', ')}:\n${table(
        state,
        both.map((c) => standing(state, c, state.holdout)),
      )}`,
    )
  }
  console.log(`\nPlay it with: pnpm dispatch --strategy ${state.strategy} --params ${bestFile}`)
}

await runScript(main, USAGE)
