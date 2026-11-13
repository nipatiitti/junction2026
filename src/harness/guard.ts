/** Runs strategy calls so that no strategy can stop the week: an error or a late answer gives the safe answer. */

/** The time budget of each call, in milliseconds. A final gives 4.5 real seconds for a quote. */
export const BUDGET_MS = { build: 5000, observe: 1500, quote: 1500, gig: 1500, tick: 3000, summary: 1500 }
export type Call = keyof typeof BUDGET_MS

export class Guard {
  /** "quote error", "gig late" and so on -> how many times. */
  readonly faults = new Map<string, number>()

  /** The strategy's answer, or undefined when the call throws or takes longer than its budget: the caller then takes
   * the safe action. A call cannot be stopped midway, so a late answer is dropped once it comes. */
  run<T>(call: Call, decide: () => T): T | undefined {
    const started = performance.now()
    try {
      const answer = decide()
      if (performance.now() - started <= BUDGET_MS[call]) return answer
      this.fault(`${call} late`)
    } catch (error) {
      this.fault(`${call} error`, error)
    }
    return undefined
  }

  /** Counts a fault, and prints the first of each kind. */
  fault(kind: string, error?: unknown): void {
    const count = (this.faults.get(kind) ?? 0) + 1
    this.faults.set(kind, count)
    const why = error === undefined ? '' : `: ${error instanceof Error ? error.message : String(error)}`
    if (count === 1) console.error(`strategy ${kind}${why}. The harness takes the safe action.`)
  }
}

/** The value with every number rounded. The API takes whole minutes and cents only, and the client refuses a whole
 * batch for one fraction. */
export function whole<T>(value: T): T {
  if (typeof value === 'number') return Math.round(value) as T
  if (Array.isArray(value)) return value.map(whole) as T
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, whole(item)])) as T
  return value
}
