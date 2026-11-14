/** The drivers' side, learned while the week runs: what a booking costs over its typical fee, as a sum of effects
 * (the world, the pickup place, the delivery place, whether the car must be collected today). A driver who lives
 * where a gig ends takes it cheaply, and a town without drivers needs every raise, so the places differ more than
 * the orders do. Each booking moves every effect of its cars by its share of what the sum got wrong. The strategy
 * feeds it each booking over what the order model expected of the car (index.ts), so an effect holds only what
 * that model does not already say. */

/** An effect starts as if it had seen this many bookings at the mean (the world: WORLD_SEEN, so that it follows the
 * first bookings), and forgets beyond MEMORY bookings, because the week moves: the first ten bookings of a week pay
 * 0.73 × typical and those after the 240th 1.03. The sum stays inside LOW and HIGH. The five are not measured. */
const SEEN = 10
const WORLD_SEEN = 3
const MEMORY = 40
const LOW = 0.5
const HIGH = 2

export class Supply {
  private readonly effects = new Map<string, { mean: number; count: number }>()
  private readonly base: number

  /** `base`: what a booking costs × typical before the week's bookings say. */
  constructor(base: number) {
    this.base = base
  }

  keys(from: string | undefined, to: string | undefined, today: boolean): string[] {
    return ['world', `from:${from}`, `to:${to}`, ...(today ? ['today'] : [])]
  }

  /** What a booking with these effects costs × typical. */
  ratio(keys: string[]): number {
    let sum = this.base
    for (const key of keys) sum += this.effects.get(key)?.mean ?? 0
    return Math.min(HIGH, Math.max(LOW, sum))
  }

  /** A car booked at `ratio` × its typical fee. An effect with few bookings moves little: it starts as if it had
   * seen 10 bookings at the mean (3 for the world). */
  learn(keys: string[], ratio: number): void {
    const miss = ratio - this.ratio(keys)
    for (const key of keys) {
      const effect = this.effects.get(key) ?? { mean: 0, count: key === 'world' ? WORLD_SEEN : SEEN }
      this.effects.set(key, effect)
      effect.count = Math.min(effect.count + 1, MEMORY)
      effect.mean += miss / effect.count / keys.length
    }
  }
}
