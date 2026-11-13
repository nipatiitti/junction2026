/** Saves every week that src/dispatch.ts plays on the server as a scraped week, like record.py does for dispatch.py:
 * the week's folder under data/scrape/runs/L<level>/<seed>/<world id>/, in scrape.py's format. `uv run db.py` then
 * adds it to the database out/spread.sqlite. README.md says what is saved.
 *
 * SPREAD_RUNS_DIR changes where the weeks go, and SPREAD_RECORD=0 saves nothing. */
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, rename, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import type { DeskEvent, DriverProfile } from '../vendor/spread-typescript/spread.ts'
import { SpreadError, type World } from '../vendor/spread-typescript/spread.ts'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const RUNS = path.resolve(process.env.SPREAD_RUNS_DIR || path.join(ROOT, 'data', 'scrape', 'runs'))
const ENABLED = (process.env.SPREAD_RECORD ?? '1') !== '0'
const POLICY = 'dispatch' // the policy of a saved run, next to scrape.py's passive, starter and explore
const REVEAL_TRIES = 6 // the reveal of a final opens when the final has ended: try for half a minute

export type Kind = 'practice' | 'board' | 'final'

const safeName = (seed: string): string => seed.replace(/[^A-Za-z0-9._-]/g, '_')
const sleep = (ms: number) => new Promise((done) => setTimeout(done, ms))

/** Every event of the world, oldest first, in pages in case the server caps an answer. */
async function allEvents(world: World): Promise<DeskEvent[]> {
  let events: DeskEvent[] = []
  while (true) {
    const page = await world.events(events.at(-1)?.seq ?? -1)
    if (page.length === 0) return events
    events = events.concat(page) // a page can hold a whole week: too many arguments for push(...page)
  }
}

/** Gzipped compact JSON for a .gz name, else indented JSON, as record.py writes them. */
async function writeJson(file: string, data: unknown): Promise<void> {
  await writeFile(file, file.endsWith('.gz') ? gzipSync(JSON.stringify(data)) : `${JSON.stringify(data, null, 2)}\n`)
}

/** The commit of this checkout, with "-dirty" when tracked files have changed; null outside git. */
function gitVersion(): string | null {
  const git = (...args: string[]) =>
    execFileSync('git', args, { cwd: ROOT, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  try {
    return git('rev-parse', 'HEAD') + (git('status', '--porcelain', '--untracked-files=no') ? '-dirty' : '')
  } catch {
    return null
  }
}

/** The path from the working folder when it is below it, else in full. */
function shown(file: string): string {
  const relative = path.relative(process.cwd(), file)
  return relative && !relative.startsWith('..') && !path.isAbsolute(relative) ? relative : file
}

/** Notes the start of a week played online, and saves the week once it has ended. `kind` is practice, board (a
 * ranking run) or final. Saving never stops the run: a failure prints a warning. */
export class Recorder {
  readonly world: World
  readonly level: number
  readonly seed: string
  readonly kind: Kind
  readonly version = gitVersion()
  readonly started = performance.now()
  drivers: DriverProfile[] = []

  private constructor(world: World, level: number, seed: string | undefined, kind: Kind) {
    this.world = world
    this.level = level
    this.kind = kind
    this.seed = seed ?? (kind === 'practice' ? 'random' : kind)
  }

  /** A recorder for a week that starts now, with the driver list at the start, as scrape.py saves it. */
  static async start(world: World, level: number, seed: string | undefined, kind: Kind): Promise<Recorder> {
    const recorder = new Recorder(world, level, seed, kind)
    if (ENABLED) {
      try {
        recorder.drivers = await world.roster()
      } catch (error) {
        if (!(error instanceof SpreadError)) throw error
        console.error(`Could not read the driver list to save with the week: ${error.message}`)
      }
    }
    return recorder
  }

  /** The world's reveal, or null where the server gives none: never for a ranking run, and in a final only once
   * the final has ended. */
  async reveal(): Promise<object | null> {
    for (let i = 0; i < REVEAL_TRIES; i++) {
      try {
        return await this.world.reveal()
      } catch (error) {
        if (!(error instanceof SpreadError) || error.status !== 409) return null // 403: a ranking run, or a final that has not ended
      }
      await sleep(5000)
    }
    return null
  }

  /** Saves the ended week to its folder under RUNS. A week saved before is skipped. */
  async save(): Promise<void> {
    if (!ENABLED) return
    const target = path.join(RUNS, `L${this.level}`, safeName(this.seed), this.world.id)
    try {
      if (existsSync(path.join(target, 'meta.json'))) return
      const reveal = await this.reveal()
      const events = await allEvents(this.world)
      const score = await this.world.score()
      const files: Record<string, unknown> = {
        'reveal.json.gz': reveal ?? {},
        'snapshot.json.gz': await this.world.snapshot(),
        'drivers.json.gz': this.drivers,
        'score.json': score,
      }
      const meta = {
        seed: this.seed,
        level: this.level,
        policy: POLICY,
        kind: this.kind,
        worldId: this.world.id,
        version: this.version,
        revealed: reveal !== null,
        recorded: false, // no actions, rosters or positions, which scrape.py records
        quoteRange: null,
        feeRange: null,
        events: events.length,
        score,
        seconds: Math.round((performance.now() - this.started) / 100) / 10,
      }
      // Written to a temporary folder, then renamed, so a folder with meta.json is always complete.
      const partial = `${target}.partial`
      await rm(partial, { recursive: true, force: true })
      await mkdir(partial, { recursive: true })
      await writeFile(
        path.join(partial, 'events.jsonl.gz'),
        gzipSync(events.map((event) => `${JSON.stringify(event)}\n`).join('')),
      )
      for (const [name, data] of Object.entries(files)) await writeJson(path.join(partial, name), data)
      await writeJson(path.join(partial, 'meta.json'), meta)
      await rm(target, { recursive: true, force: true })
      await rename(partial, target)
      await this.saveMap()
    } catch (error) {
      // The run has ended and scored: only the saving failed.
      console.error(`Could not save the week to ${shown(target)}: ${(error as Error).message ?? error}`)
      return
    }
    console.log(`Saved the week to ${shown(target)}. uv run db.py adds it to out/spread.sqlite.`)
  }

  /** The map, once for every run, as scrape.py saves it next to its weeks. Runs that save at the same time each
   * write their own file and rename it. */
  async saveMap(): Promise<void> {
    const file = path.join(RUNS, 'map.json')
    if (existsSync(file)) return
    const partial = `${file}.${process.pid}`
    await writeJson(partial, await this.world.client.map())
    await rename(partial, file)
  }
}
