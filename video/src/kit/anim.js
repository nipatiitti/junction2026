// Time helpers. Every view sets its whole picture from the time t alone.

export const clamp = (x, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x))
export const lerp = (a, b, k) => a + (b - a) * k
/** 0 before t0, 1 after t1, linear between. */
export const progress = (t, t0, t1) => clamp((t - t0) / (t1 - t0))

export const ease = {
  linear: (k) => k,
  inQuad: (k) => k * k,
  outQuad: (k) => 1 - (1 - k) * (1 - k),
  inOutQuad: (k) => (k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2),
  inCubic: (k) => k ** 3,
  outCubic: (k) => 1 - (1 - k) ** 3,
  inOutCubic: (k) => (k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2),
  outBack: (k) => 1 + 2.70158 * (k - 1) ** 3 + 1.70158 * (k - 1) ** 2,
  outElastic: (k) => (k <= 0 || k >= 1 ? k : 2 ** (-10 * k) * Math.sin((k * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1),
  outBounce: (k) => {
    const n = 7.5625
    const d = 2.75
    if (k < 1 / d) return n * k * k
    if (k < 2 / d) return n * (k - 1.5 / d) ** 2 + 0.75
    if (k < 2.5 / d) return n * (k - 2.25 / d) ** 2 + 0.9375
    return n * (k - 2.625 / d) ** 2 + 0.984375
  },
}

/**
 * Keyframes: track(t, [[t0, v0], [t1, v1, 'outCubic'], ...]) gives the value at t.
 * A value is a number or an array of numbers; the easing named on a key shapes the move into that key.
 */
export function track(t, keys) {
  if (t <= keys[0][0]) return keys[0][1]
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1, name] = keys[i]
    if (t <= t1) {
      const [t0, v0] = keys[i - 1]
      const k = (ease[name] ?? ease.inOutQuad)(t1 === t0 ? 1 : (t - t0) / (t1 - t0))
      return Array.isArray(v0) ? v0.map((x, j) => lerp(x, v1[j], k)) : lerp(v0, v1, k)
    }
  }
  return keys[keys.length - 1][1]
}

/** A scale for popping in at t0: 0 before, overshoots, settles at 1. */
export const pop = (t, t0, duration = 0.25) => (t < t0 ? 0 : ease.outBack(progress(t, t0, t0 + duration)))

/** Slow motion: between t0 and t1 the clock runs at `rate`. Returns the warped time, continuous at both ends. */
export function slowmo(t, t0, t1, rate) {
  if (t <= t0) return t
  if (t <= t1) return t0 + (t - t0) * rate
  return t0 + (t1 - t0) * rate + (t - t1)
}
