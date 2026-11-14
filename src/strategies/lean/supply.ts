/** The drivers' side, learned while the week runs: what a booking costs over its typical fee, as a sum of effects
 * (the world, the pickup place, the delivery place, whether the car must be collected today). A driver who lives
 * where a gig ends takes it cheaply, and a town without drivers needs every raise, so the places differ more than
 * the orders do. Each booking moves every effect of its cars by its share of what the sum got wrong. */

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
    return Math.min(2, Math.max(0.5, sum))
  }

  /** A car booked at `ratio` × its typical fee. An effect with few bookings moves little: it starts as if it had
   * seen 10 bookings at the mean (3 for the world). */
  learn(keys: string[], ratio: number): void {
    const miss = ratio - this.ratio(keys)
    for (const key of keys) {
      const effect = this.effects.get(key) ?? { mean: 0, count: key === 'world' ? 3 : 10 }
      this.effects.set(key, effect)
      effect.count = Math.min(effect.count + 1, 40) // the week moves: old bookings fade
      effect.mean += miss / effect.count / keys.length
    }
  }
}
