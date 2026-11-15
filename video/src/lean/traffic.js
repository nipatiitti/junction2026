// Traffic on the diagram's roads, as formulas of time: a vehicle drives a route at its speed, waits at its stops,
// and never runs into the one ahead of it (it waits behind it instead). Nothing is stepped, so any frame can be
// drawn on its own.

/** A route through points [[x, z], ...]: its length, and where a distance along it lies and which way it points. */
export function polyline(points) {
  const marks = [0]
  for (let i = 1; i < points.length; i++)
    marks.push(marks[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]))
  const length = marks.at(-1)
  return {
    points,
    length,
    /** [x, z, heading] at distance d; heading is the angle from +x towards +z. */
    at(d) {
      const s = Math.min(Math.max(d, 0), length)
      let i = 1
      while (i < points.length - 1 && marks[i] < s) i++
      const a = points[i - 1]
      const b = points[i]
      const span = marks[i] - marks[i - 1] || 1
      const k = (s - marks[i - 1]) / span
      return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, Math.atan2(b[1] - a[1], b[0] - a[0])]
    },
    /** The distance along the route of the point nearest to p. */
    distanceOf(p) {
      let best = Infinity
      let found = 0
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1]
        const b = points[i]
        const dx = b[0] - a[0]
        const dz = b[1] - a[1]
        const span = dx * dx + dz * dz || 1
        const k = Math.min(1, Math.max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / span))
        const gap = Math.hypot(a[0] + dx * k - p[0], a[1] + dz * k - p[1])
        if (gap < best) {
          best = gap
          found = marks[i - 1] + k * Math.sqrt(span)
        }
      }
      return found
    },
  }
}

/** The points of roads one after another, without repeating the point where one ends and the next begins. */
export function joined(roads) {
  const points = []
  for (const road of roads)
    for (const p of road.points) {
      const last = points.at(-1)
      if (!last || last[0] !== p[0] || last[1] !== p[1]) points.push(p)
    }
  return points
}

/**
 * Where a vehicle that sets off at `start` at `speed` would be at time t on its own, with stops [{ d, wait }] in
 * order of distance: the distance along its route, or -1 before it starts.
 */
function alone(t, { start, speed, stops = [] }) {
  if (t < start) return -1
  let clock = start
  let at = 0
  for (const stop of stops) {
    const arrive = clock + (stop.d - at) / speed
    if (t < arrive) return at + (t - clock) * speed
    if (t < arrive + stop.wait) return stop.d
    clock = arrive + stop.wait
    at = stop.d
  }
  return at + (t - clock) * speed
}

/**
 * A queue of vehicles on one route, in the order they set off. Each keeps `gap` behind the one before it. Returns
 * the distance of each at time t (-1 for one that has not started, Infinity for one that has left the route).
 */
export function queue(route, vehicles, t) {
  const out = []
  let ahead = Infinity
  for (const v of vehicles) {
    let d = alone(t, v)
    if (d >= 0 && Number.isFinite(ahead)) d = Math.min(d, ahead - (v.gap ?? 4.5))
    if (d >= 0 && d < 0.001 && t < v.start + 0.001) d = 0
    out.push(d > route.length ? Infinity : d)
    ahead = d < 0 ? ahead : d
  }
  return out
}

/** The time at which a vehicle alone would reach distance d (before any stops beyond it). */
export function reaches(d, { start, speed, stops = [] }) {
  let clock = start
  let at = 0
  for (const stop of stops) {
    if (stop.d >= d) break
    clock += (stop.d - at) / speed + stop.wait
    at = stop.d
  }
  return clock + (d - at) / speed
}
