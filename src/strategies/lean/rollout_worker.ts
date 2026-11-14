/** A worker thread of the rollout (rollout.ts): plays its share of the simulated weeks and writes each week's margin,
 * orders and share on time into the shared cells, or posts the whole weeks back to rollout_fit.ts. It plays the
 * simulator in memory only: before anything loads, it drops the live run's server address and key from its own copy
 * of the environment, so that no code in this thread could build a client for the Spread server. */
import { parentPort, workerData } from 'node:worker_threads'
import type { LeanParams } from './index.ts'
import type { Job } from './rollout.ts'

delete process.env.SPREAD_URL
delete process.env.SPREAD_KEY
delete process.env.SPREAD_RESTART_AT // the practice loop's restart check is for the live week only

type Task = {
  /** The shared cells: [0] counts the workers done, [1] the workers that failed; `cell` of a job is its first of three. */
  cells?: SharedArrayBuffer
  jobs: (Job & { cell?: number })[]
  params: Partial<LeanParams>
  /** The minutes at which to take the week's marks, for rollout_fit.ts. */
  at?: number[]
}
const task = workerData as Task
const cells = task.cells ? new Int32Array(task.cells) : undefined
try {
  const { playWeek } = await import('./rollout_play.ts')
  for (const job of task.jobs) {
    const week = await playWeek(job.seed, { ...task.params, rolloutPlan: job.plan }, task.at)
    if (cells && job.cell !== undefined) {
      cells[job.cell] = week.score.marginCents
      cells[job.cell + 1] = week.score.wonOrders
      cells[job.cell + 2] = Math.round(week.score.onTimeShare * 1e4)
    } else parentPort?.postMessage({ seed: job.seed, ...week })
  }
} catch (error) {
  if (cells) Atomics.add(cells, 1, 1)
  else throw error
} finally {
  if (cells) {
    Atomics.add(cells, 0, 1)
    Atomics.notify(cells, 0)
  }
}
