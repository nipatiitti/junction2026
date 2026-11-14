/** Rollout: lookahead in the offline simulator while the live week runs (the param `rollout`).
 *
 * Lean's charge for one more order (`taxLoad`, index.ts) sets how many orders a week wins, and it is the same in
 * every world. The rollout scales it for this world (× 1, 1.5 or 2.5). At four decision points (before Monday, and on the evenings of
 * Monday to Wednesday at 18:30, for the day after) it:
 *
 * 1. picks the recorded simulator weeks that look most like the live week so far (`match`): the number of drivers,
 *    the requests so far, the price level that the quotes' wins and losses show, and the fee that bookings paid;
 * 2. plays lean on each of them, a whole week, once for each candidate scale: with the scales that the live week
 *    has used until now, and the candidate from the next morning on (rollout_worker.ts, rollout_play.ts);
 * 3. keeps the scale in force unless a candidate earns clearly more on those weeks (`choose`).
 *
 * The chosen scale holds from 06:00 of the next day. The simulated weeks run in worker threads, so the live week
 * goes on while they play; a tick waits for them up to `TICK_WAIT_MS`, and the first event after 06:00 waits until
 * they are done, so a choice always starts at the same minute. Nothing here can reach the Spread server: the
 * workers play the simulator in memory, without the client.
 *
 * A rebuilt strategy gets the same choices: what a decision sees is rebuilt from the events and the journal, the
 * simulated weeks are deterministic, and each decision's result is saved in the journal folder under the hash of
 * its inputs (`rollout/<hash>.json`), so a rebuild reads it instead of playing the weeks again.
 *
 * This file does not load the simulator: only the workers do, and only when `rollout` is over 0. */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { availableParallelism } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Worker } from 'node:worker_threads'
import type { Action, ActionResult, DeskEvent, DriverProfile } from '../../../vendor/spread-typescript/spread.ts'
import type { Books, Setup } from '../../strategy.ts'
import { DAY, WEEKDAYS } from '../../time.ts'
import type { LeanParams } from './index.ts'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..', '..', '..')
/** The journal's folder (src/harness/journal.ts), where the decisions are saved. */
const SAVED = path.join(path.resolve(process.env.SPREAD_JOURNAL_DIR || path.join(ROOT, 'out', 'journal')), 'rollout')
/** Lean's week on every recorded simulator seed with the default settings (rollout_fit.ts writes it). */
const WEEKS_FILE = path.join(HERE, 'rollout_weeks.json')
/** Changes when the simulated weeks or the choice change, so that saved decisions of an older version are not read. */
const VERSION = 1

/** The scales of the charge that a decision compares. They differ a lot, because the simulator tells two settings
 * apart only when they are over about €500 a week apart (sim/README.md): on 67 recorded weeks, 1.5 won 36 orders
 * fewer than 1 and 2.5 won 90 fewer. None is under 1: a scale of 0.5 won 41 orders more and made €750 a week less
 * even on the simulator, which is too gentle on a week with too many orders. */
export const CANDIDATES = [1, 1.5, 2.5]
/** The decisions: number `d` is made for the day `d` (0 is Monday), from what the week showed at `seenAt`, and its
 * scale holds from `appliesAt`. */
const DECISIONS = 4
const seenAt = (d: number): number => (d === 0 ? 0 : (d - 1) * DAY + 18 * 60 + 30)
const appliesAt = (d: number): number => d * DAY + 6 * 60
/** The minutes of the week at which the weeks are compared: the decisions after Monday's. */
export const MARK_AT = Array.from({ length: DECISIONS - 1 }, (_, i) => seenAt(i + 1))
/** `rollout` × this many matched weeks for each candidate. */
const WEEKS_PER_UNIT = 8
/** A tick waits this long for the simulated weeks (its budget is 3 seconds), an event after `appliesAt` this long. */
const TICK_WAIT_MS = 2000
const LAST_WAIT_MS = 180_000

/** The choice (`choose`). A candidate must earn `GAIN` euros a week more than the scale in force, on the mean of the
 * matched weeks, × the share of the week's five days that it still sets, and no less than `LEAST_GAIN`; twice that
 * when its charge is under the default's, because it then wins more orders than the default, and the simulator is
 * too gentle on a week with too many orders. The gain must also be `CLEAR` standard errors of that mean over zero:
 * one matched week differs from the next by about €1,000 in what a scale earns. It must stay over `ON_TIME` in each
 * matched week, or over the worst week of the scale in force. Each order over `FULL_LOAD` orders per driver costs a
 * simulated week `OVER_EUROS`: on the server a week at 0.7 orders per driver made €4,800 less than one at 0.6,
 * which the simulator does not show. */
const GAIN = 500
const LEAST_GAIN = 200
const CLEAR = 2
const ON_TIME = 0.92
const FULL_LOAD = 0.6
const OVER_EUROS = 50

/** The logistic scale, in log price, of the fit of the price level (`level`): the request's own noise and the
 * dealers' and places' effects together. */
const LEVEL_SCALE = 0.15
const LEVEL_LOW = Math.log(0.9)
const LEVEL_HIGH = Math.log(2.5)
/** A quote over this multiple of the list price is a decline, and says nothing of the price level. */
const DECLINED = 3
/** What a week weighs in the match, for each standard deviation of difference. */
const WEIGHTS = { drivers: 1, requests: 0.5, level: 1, feeRatio: 1 }

/** What a week looked like at a minute: the requests so far, the multiple of the list price at which half of the
 * quotes win (fitted to every quote's win or loss, so that it does not depend on how high we quoted), and what the
 * bookings paid × typical. */
export type Marks = { at: number; requests: number; level: number; feeRatio: number }
/** One simulated week: its margin in cents, its orders and its share on time. */
export type Week = { margin: number; orders: number; onTime: number }
/** A recorded simulator week under the default settings. */
type Recorded = { seed: string; drivers: number; roster: string; marks: Marks[] } & Week
/** One week for a worker to play: the simulator seed and the scales by minute (the param `rolloutPlan`). */
export type Job = { seed: string; plan: string }
/** A scale and the minute from which it holds. */
type Step = { from: number; scale: number }

const mean = (values: number[]): number => values.reduce((sum, value) => sum + value, 0) / (values.length || 1)
const spread = (values: number[]): number => {
  const middle = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - middle) ** 2))) || 1
}

/** The scales of a plan: "minute:scale;minute:scale". */
export function parsePlan(text: string): Step[] {
  return text
    .split(';')
    .filter(Boolean)
    .map((item) => {
      const [from, scale] = item.split(':').map(Number)
      if (!Number.isFinite(from) || !Number.isFinite(scale)) throw new Error(`"${item}" is not minute:scale`)
      return { from: from!, scale: scale! }
    })
}
const planText = (plan: Step[]): string => plan.map((step) => `${step.from}:${step.scale}`).join(';')
const scaleAt = (plan: Step[], minute: number): number => plan.findLast((step) => step.from <= minute)?.scale ?? 1

/** What a week shows of its world, from its events and our quotes alone, so that a live week and a simulated one
 * are read the same way. It takes a mark at the first event at or after each minute of `at`. */
export class Features {
  readonly marks: Marks[] = []
  private requests = 0
  private fees = 0
  private typical = 0
  /** Request id -> the prices we sent. */
  private readonly quoted = new Map<string, Record<string, number>>()
  /** Each quoted option that the dealer answered: the log of its multiple of the list price, and whether it won. */
  private readonly outcomes: [number, boolean][] = []
  readonly drivers: number
  private readonly at: number[]

  constructor(drivers: number, at: number[] = MARK_AT) {
    this.drivers = drivers
    this.at = at
  }

  /** The driver list as one short text: two worlds with the same drivers are the same recorded week. */
  static print(roster: readonly DriverProfile[]): string {
    const text = roster.map((driver) => `${driver.id}@${driver.homePlaceId}`).join(',')
    return createHash('sha1').update(text).digest('hex').slice(0, 16)
  }

  observe(event: DeskEvent, books: Books): void {
    const minute = 'at' in event ? event.at : books.now
    while (this.marks.length < this.at.length && minute >= this.at[this.marks.length]!) this.marks.push(this.mark())
    if (event.kind === 'price_request') this.requests++
    else if (event.kind === 'order_won') this.outcome(event.order.id, event.order.option, books)
    else if (event.kind === 'order_lost') this.outcome(event.requestId, null, books)
    else if (event.kind === 'gig_booked') {
      let typical = 0
      for (const stop of books.posts.get(event.gigId)?.stops ?? []) {
        const request = stop.kind === 'pickup' ? books.requests.get(stop.orderId) : undefined
        if (request) typical += request.referenceFeeCents / request.legs.length
      }
      if (!(typical > 0)) return
      this.fees += event.feeCents
      this.typical += typical
    }
  }

  sent(action: Action, result: ActionResult): void {
    if (result.ok && action.type === 'quote') this.quoted.set(action.requestId, action.prices)
  }

  private outcome(requestId: string, won: string | null, books: Books): void {
    const prices = this.quoted.get(requestId)
    this.quoted.delete(requestId)
    for (const option of books.requests.get(requestId)?.options ?? []) {
      const cents = prices?.[option.kind]
      if (cents === undefined || (won && option.kind !== won)) continue
      const multiple = cents / option.listPriceCents
      if (multiple > 0 && multiple < DECLINED) this.outcomes.push([Math.log(multiple), won !== null])
    }
  }

  /** The week as it looks now. */
  mark(): Marks {
    const at = this.at[this.marks.length] ?? Infinity
    const feeRatio = this.typical > 0 ? this.fees / this.typical : 0
    return { at, requests: this.requests, level: this.level(), feeRatio: Math.round(feeRatio * 1e4) / 1e4 }
  }

  /** The multiple of the list price at which half of the quotes win: the one logistic curve of scale `LEVEL_SCALE`
   * that expects as many wins as the quotes had. 0 without an answered quote. */
  private level(): number {
    if (this.outcomes.length === 0) return 0
    const wins = this.outcomes.filter(([, won]) => won).length
    const expected = (mu: number) =>
      this.outcomes.reduce((sum, [x]) => sum + 1 / (1 + Math.exp((x - mu) / LEVEL_SCALE)), 0)
    let low = LEVEL_LOW
    let high = LEVEL_HIGH
    for (let i = 0; i < 30; i++) {
      const middle = (low + high) / 2
      if (expected(middle) < wins) low = middle
      else high = middle
    }
    return Math.round(Math.exp((low + high) / 2) * 1e4) / 1e4
  }
}

/** The `count` recorded weeks nearest to a live week of `drivers` drivers that showed `mark` at decision `d` (none
 * before Monday), without the weeks of the live world's own driver list: those would be the answer key. */
function match(weeks: Recorded[], d: number, drivers: number, mark: Marks | undefined, own: string, count: number) {
  const others = weeks.filter((week) => week.roster !== own)
  const of = (week: Recorded) => week.marks[d - 1]
  const sd = {
    drivers: spread(others.map((week) => week.drivers)),
    requests: spread(others.map((week) => of(week)?.requests ?? 0)),
    level: spread(others.map((week) => of(week)?.level ?? 0)),
    feeRatio: spread(others.map((week) => of(week)?.feeRatio ?? 0)),
  }
  const distance = (week: Recorded): number => {
    let sum = WEIGHTS.drivers * ((week.drivers - drivers) / sd.drivers) ** 2
    const theirs = of(week)
    if (!mark || !theirs) return sum
    sum += WEIGHTS.requests * ((theirs.requests - mark.requests) / sd.requests) ** 2
    // A week without an answered quote or a booking so far says nothing of its level or its fees.
    if (mark.level > 0 && theirs.level > 0) sum += WEIGHTS.level * ((theirs.level - mark.level) / sd.level) ** 2
    if (mark.feeRatio > 0 && theirs.feeRatio > 0)
      sum += WEIGHTS.feeRatio * ((theirs.feeRatio - mark.feeRatio) / sd.feeRatio) ** 2
    return sum
  }
  return others
    .map((week) => ({ week, far: distance(week) }))
    .sort((a, b) => a.far - b.far || (a.week.seed < b.week.seed ? -1 : 1))
    .slice(0, count)
    .map(({ week }) => week)
}

/** What a simulated week is worth, in euros: its margin, less `OVER_EUROS` for each order over `FULL_LOAD` a driver. */
const worth = (week: Week, drivers: number): number =>
  week.margin / 100 - OVER_EUROS * Math.max(0, week.orders - FULL_LOAD * drivers)

/** The candidate to play on with, as an index of `CANDIDATES`, and the mean gain in euros of each candidate over the
 * one in force (`current`). `played[c][s]` is the week of candidate `c` on the matched week `s`. */
export function choose(
  played: Week[][],
  drivers: number[],
  current: number,
  d: number,
): { pick: number; gains: number[] } {
  const base = played[current]!
  const need = Math.max(LEAST_GAIN, (GAIN * (5 - d)) / 5)
  const worst = (weeks: Week[]) => Math.min(...weeks.map((week) => week.onTime))
  const gains = played.map((weeks) =>
    mean(weeks.map((week, s) => worth(week, drivers[s]!) - worth(base[s]!, drivers[s]!))),
  )
  let pick = current
  played.forEach((weeks, c) => {
    if (c === current) return
    const error = spread(weeks.map((week, s) => worth(week, drivers[s]!) - worth(base[s]!, drivers[s]!)))
    const clear = gains[c]! >= (CLEAR * error) / Math.sqrt(Math.max(1, weeks.length - 1))
    const onTime = worst(weeks) >= Math.min(ON_TIME, worst(base))
    const enough = gains[c]! >= need * (CANDIDATES[c]! < 1 ? 2 : 1)
    if (enough && clear && onTime && gains[c]! > gains[pick]!) pick = c
  })
  return { pick, gains }
}

/** A decision whose simulated weeks are playing. */
type Pending = {
  d: number
  key: string
  seeds: string[]
  drivers: number[]
  current: number
  /** [0] the workers that have finished, [1] the workers that failed, then margin, orders and on time × 10,000 of
   * each job, candidate by candidate. */
  cells: Int32Array
  workers: Worker[]
  startedAt: number
}

export class Rollout {
  /** The scales in force, by minute: the param `rolloutPlan`, then each decision's. */
  private readonly plan: Step[]
  private readonly features: Features | undefined
  private readonly weeks: Recorded[] = []
  private readonly own: string
  private readonly count: number
  private readonly params: LeanParams
  private next = 0
  private pending: Pending | undefined
  private readonly said: string[] = []
  private spentMs = 0

  constructor(setup: Setup, params: LeanParams) {
    this.params = params
    this.plan = parsePlan(params.rolloutPlan)
    this.count = Math.round(WEEKS_PER_UNIT * params.rollout)
    this.own = Features.print(setup.roster)
    // A fixed plan, a level that the simulator does not play, or a build without a driver list: no decisions.
    if (this.count < 1 || setup.level !== 8 || setup.roster.length === 0) return
    this.weeks = JSON.parse(readFileSync(WEEKS_FILE, 'utf-8')) as Recorded[]
    this.features = new Features(setup.roster.length)
  }

  /** The scale of the charge at `minute`. */
  scale(minute: number): number {
    return scaleAt(this.plan, minute)
  }

  observe(event: DeskEvent, books: Books): void {
    if (!this.features) return
    const minute = 'at' in event ? event.at : books.now
    this.features.observe(event, books)
    this.advance(minute)
  }

  sent(action: Action, result: ActionResult): void {
    this.features?.sent(action, result)
  }

  /** Waits a moment for the simulated weeks, so that a practice week, whose clock stands still while we compute,
   * has the choice by the morning. */
  tick(minute: number): void {
    if (!this.features) return
    // Only an event ends a decision that is due (`observe`): a tick that waited that long would lose its actions.
    if (!this.pending) this.advance(minute)
    if (this.pending) this.wait(TICK_WAIT_MS)
  }

  /** Starts each decision that is due at `minute`, and ends the one whose scale should hold by now. */
  private advance(minute: number): void {
    while (true) {
      if (this.pending && minute >= appliesAt(this.pending.d)) this.wait(LAST_WAIT_MS, true)
      // Monday's decision needs the driver list only; a later one starts when the week's mark for it is taken.
      if (this.pending || this.next >= DECISIONS || this.features!.marks.length < this.next) return
      this.begin(this.next++)
    }
  }

  /** Decision `d`: matches the weeks and plays them, or reads the saved result. */
  private begin(d: number): void {
    const features = this.features!
    const matched = match(this.weeks, d, features.drivers, features.marks[d - 1], this.own, this.count)
    const current = CANDIDATES.indexOf(this.scale(appliesAt(d)))
    if (matched.length === 0 || current < 0) return // no week to play, or a plan by hand with a scale of its own
    const seeds = matched.map((week) => week.seed)
    const plans = CANDIDATES.map((scale, c) =>
      planText(c === current ? this.plan : [...this.plan, { from: appliesAt(d), scale }]),
    )
    const { rollout: _, rolloutPlan: __, ...settings } = this.params
    const key = createHash('sha1')
      .update(JSON.stringify([VERSION, d, plans, seeds, settings]))
      .digest('hex')
      .slice(0, 20)
    const cells = new Int32Array(new SharedArrayBuffer(4 * (2 + 3 * CANDIDATES.length * seeds.length)))
    const pending: Pending = {
      d,
      key,
      seeds,
      drivers: matched.map((w) => w.drivers),
      current,
      cells,
      workers: [],
      startedAt: performance.now(),
    }
    this.pending = pending
    const saved = path.join(SAVED, `${key}.json`)
    if (existsSync(saved)) {
      try {
        this.decide(pending, (JSON.parse(readFileSync(saved, 'utf-8')) as { played: Week[][] }).played, true)
        return
      } catch {} // a file cut off by a crash: the weeks are played again
    }
    const jobs = plans.flatMap((plan, c) =>
      seeds.map((seed, s) => ({ seed, plan, cell: 2 + 3 * (c * seeds.length + s) })),
    )
    const threads = Math.min(jobs.length, Math.max(1, availableParallelism()))
    for (let t = 0; t < threads; t++) {
      const worker = new Worker(new URL('./rollout_worker.ts', import.meta.url), {
        workerData: { cells: cells.buffer, jobs: jobs.filter((_job, i) => i % threads === t), params: settings },
      })
      worker.on('error', () => {}) // a worker that failed has said so in the cells, or is waited out
      worker.unref()
      pending.workers.push(worker)
    }
  }

  /** Waits up to `ms` for the workers; when they are done, or with `last` when they are not, ends the decision. */
  private wait(ms: number, last = false): void {
    const pending = this.pending!
    const { cells, workers } = pending
    const until = performance.now() + ms
    while (Atomics.load(cells, 0) < workers.length) {
      const left = until - performance.now()
      if (left <= 0) break
      Atomics.wait(cells, 0, Atomics.load(cells, 0), left)
    }
    const done = Atomics.load(cells, 0) >= workers.length
    if (!done && !last) return
    if (!done || Atomics.load(cells, 1) > 0) {
      for (const worker of workers) void worker.terminate()
      this.end(
        pending,
        `${WEEKDAYS[pending.d]}: the simulated weeks ${done ? 'failed' : 'took too long'}, the scale stays`,
      )
      return
    }
    const played = CANDIDATES.map((_scale, c) =>
      pending.seeds.map((_seed, s) => {
        const cell = 2 + 3 * (c * pending.seeds.length + s)
        return { margin: cells[cell]!, orders: cells[cell + 1]!, onTime: cells[cell + 2]! / 1e4 }
      }),
    )
    this.decide(pending, played, false)
  }

  /** Takes the choice from the simulated weeks, and saves them for a rebuild. */
  private decide(pending: Pending, played: Week[][], saved: boolean): void {
    const { d, key, seeds, drivers, current } = pending
    const { pick, gains } = choose(played, drivers, current, d)
    const scale = CANDIDATES[pick]!
    if (pick !== current) this.plan.push({ from: appliesAt(d), scale })
    if (!saved) {
      try {
        mkdirSync(SAVED, { recursive: true })
        writeFileSync(
          path.join(SAVED, `${key}.json`),
          `${JSON.stringify({ d, seeds, candidates: CANDIDATES, current, pick, gains, played })}\n`,
        )
      } catch {} // without the file a rebuild plays the weeks again, and gets the same
    }
    const euros = gains.map((gain, c) => `${CANDIDATES[c]} ${gain >= 0 ? '+' : '−'}€${Math.abs(Math.round(gain))}`)
    this.end(
      pending,
      `${WEEKDAYS[d]}: scale ${scale} (${euros.join(', ')} on ${seeds.join(' ')}${saved ? ', saved' : ''})`,
    )
  }

  private end(pending: Pending, line: string): void {
    this.spentMs += performance.now() - pending.startedAt
    this.pending = undefined
    this.said.push(line)
    console.log(`lean rollout, ${line}.`)
  }

  /** The week's decisions, for the summary line. */
  summary(): string {
    if (!this.features) return this.plan.length > 0 ? ` Charge scale ${planText(this.plan)}.` : ''
    const scales = Array.from({ length: this.next }, (_, d) => this.scale(appliesAt(d)))
    return ` Rollout: scale ${scales.join(', ')} from Monday on, ${Math.round(this.spentMs / 1000)} s of simulated weeks.`
  }
}
