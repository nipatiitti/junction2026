/** Writes rollout_weeks.json, the weeks that the rollout matches a live week against (rollout.ts): lean with its
 * default settings on every recorded seed of the offline simulator, with what each week looked like at the decision
 * minutes and how it ended. Offline: it plays the simulator in memory, in worker threads. Run it again when lean's
 * defaults or the simulator change: `node src/strategies/lean/rollout_fit.ts [seed ...]`. */
import { readdirSync, writeFileSync } from 'node:fs'
import { availableParallelism } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Worker } from 'node:worker_threads'
import { MARK_AT } from './rollout.ts'
import type { Played } from './rollout_play.ts'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PACKS = path.resolve(HERE, '..', '..', '..', 'sim', 'data', 'L8')
const named = process.argv.slice(2)
const seeds = named.length > 0 ? named : readdirSync(PACKS).map((file) => file.replace('.json.gz', ''))
seeds.sort()
const threads = Math.min(seeds.length, availableParallelism())
const weeks: (Played & { seed: string })[] = []
await Promise.all(
  Array.from({ length: threads }, (_, t) => {
    const jobs = seeds.filter((_seed, i) => i % threads === t).map((seed) => ({ seed, plan: '' }))
    const worker = new Worker(new URL('./rollout_worker.ts', import.meta.url), {
      workerData: { jobs, params: {}, at: MARK_AT },
    })
    worker.on('message', (week: Played & { seed: string }) => {
      weeks.push(week)
      if (weeks.length % 20 === 0) console.log(`${weeks.length} of ${seeds.length} weeks.`)
    })
    return new Promise<void>((done, fail) => worker.once('error', fail).once('exit', () => done()))
  }),
)
weeks.sort((a, b) => (a.seed < b.seed ? -1 : 1))
const rows = weeks.map(({ seed, drivers, roster, marks, score }) =>
  JSON.stringify({
    seed,
    drivers,
    roster,
    marks,
    margin: score.marginCents,
    orders: score.wonOrders,
    onTime: Math.round(score.onTimeShare * 1e4) / 1e4,
  }),
)
const file = path.join(HERE, named.length > 0 ? 'rollout_weeks.part.json' : 'rollout_weeks.json')
writeFileSync(file, `[\n${rows.join(',\n')}\n]\n`)
console.log(`${weeks.length} weeks in ${file}.`)
