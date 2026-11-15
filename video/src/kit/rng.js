// Seeded random numbers, so every render of a frame is the same.

/** mulberry32: the same seed gives the same numbers. rand() is in [0, 1). */
export function rng(seed) {
  let a = seed >>> 0
  const rand = () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  rand.range = (lo, hi) => lo + (hi - lo) * rand()
  rand.pick = (list) => list[Math.floor(rand() * list.length)]
  return rand
}

/** Smooth 1D value noise in [-1, 1], for camera shake and wobble. */
export function noise(x, seed = 0) {
  const hash = (n) => {
    const s = Math.sin(n * 127.1 + seed * 311.7) * 43758.5453
    return (s - Math.floor(s)) * 2 - 1
  }
  const i = Math.floor(x)
  const f = x - i
  const u = f * f * (3 - 2 * f)
  return hash(i) * (1 - u) + hash(i + 1) * u
}
