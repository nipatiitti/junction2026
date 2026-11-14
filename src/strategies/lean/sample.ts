/** The draws of Thompson sampling on the win model (demand.ts, `Demand.sampled`): a standard normal number for a
 * text seed. The same seed gives the same number, so a strategy rebuilt after a restart quotes the same prices. */

/** No draw is further than this many standard deviations from the mean: with every prior summed (0.22 in log
 * price) the widest draw moves a price by 55%. Not measured. */
const WIDEST = 2

/** A whole number for a text (FNV-1a, then a murmur finish so that ids that differ in one digit give far numbers). */
function hash(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193)
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b)
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35)
  return (h ^ (h >>> 16)) >>> 0
}

/** A number in (0, 1) from a whole number (one step of mulberry32). */
function uniform(seed: number): number {
  const a = (seed + 0x6d2b79f5) | 0
  let t = Math.imul(a ^ (a >>> 15), 1 | a)
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
  return (((t ^ (t >>> 14)) >>> 0) + 0.5) / 4294967296
}

/** A standard normal number for `seed` (Box-Muller), kept within `WIDEST`. */
export function normal(seed: string): number {
  const h = hash(seed)
  const z = Math.sqrt(-2 * Math.log(uniform(h))) * Math.cos(2 * Math.PI * uniform(h ^ 0x9e3779b9))
  return Math.max(-WIDEST, Math.min(WIDEST, z))
}
