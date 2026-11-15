import { clamp, ease, lerp, progress } from '../kit/anim.js'
import { MONO } from './ui.js'

// The cards that explain a decision while the camera shows its blocks: the fee steps, the chains, and the win curve
// learning. A card holds two graphs, each under the name of the function it shows, and no other words or numbers:
// the voice says them. It sits in a third of the picture inside the title-safe frame (the camera leaves that third to
// it), comes in at 0.6 s, builds up with the voice, and goes out over the last 0.3 s of its segment. Everything in it
// keeps one margin, PAD, from the card's edges and between its two parts. The shapes follow the code's defaults and
// src/strategies/lean/README.md: the fee's steps, up to four cars a chain, the share of chains that book (53% before
// bookChance(), 71% with it), the win curve's middle, and Supply's ratio (0.84 to 0.97). The beats are the local
// seconds of the card's segment in timeline.js, where the voice lines are.

const PANEL = 'rgba(11, 17, 30, 0.95)'
const GRID = '#1e293b'
const AXIS = '#475569'
const NAME = '#f8fafc'
const GREEN = '#4ade80'
const RED = '#f87171'
const ORANGE = '#f59e0b'
const PAD = 44
const BAR = 8 // the coloured edge at the top
const HEADING = 40 // the line of a part's name
const UNDER = 26 // between a name and its graph

/**
 * The card's frame, in its decision's colour. Returns its two parts, { name: the y of the name's middle, box: the
 * graph's box }, the first `split` of the height above the second, or null while the card is not on.
 */
function card(g, t, duration, { x, y, w, h }, colour, split) {
  const k = ease.outCubic(progress(t, 0.6, 1.0)) * (1 - progress(t, duration - 0.3, duration))
  if (k <= 0) return null
  g.globalAlpha = k
  g.translate(-30 * (1 - k), 0)
  g.beginPath()
  g.roundRect(x, y, w, h, 20)
  g.fillStyle = PANEL
  g.fill()
  g.save()
  g.clip()
  g.fillStyle = colour
  g.fillRect(x, y, w, BAR)
  g.restore()
  const inner = { x: x + PAD, y: y + BAR + PAD, w: w - 2 * PAD, h: h - BAR - 2 * PAD }
  const first = Math.round((inner.h - PAD) * split)
  const part = (top, height) => ({
    name: top + HEADING / 2,
    box: { x: inner.x, y: top + HEADING + UNDER, w: inner.w, h: height - HEADING - UNDER },
  })
  return [part(inner.y, first), part(inner.y + first + PAD, inner.h - first - PAD)]
}

/** A part's name, the function's name in the monospace font, fading in from `at`. */
function heading(g, t, text, { name, box }, at) {
  const a = clamp((t - at) / 0.3)
  if (a <= 0) return
  g.save()
  g.globalAlpha *= a
  g.fillStyle = NAME
  g.font = `700 34px ${MONO}`
  g.textAlign = 'left'
  g.textBaseline = 'middle'
  g.fillText(text, box.x, name)
  g.restore()
}

/** Faint lines across a graph's box, and its two axes. */
function axes(g, { x, y, w, h }, rows = 4) {
  g.strokeStyle = GRID
  g.lineWidth = 2
  for (let i = 0; i < rows; i++) {
    const v = y + (h * i) / rows
    g.beginPath()
    g.moveTo(x, v)
    g.lineTo(x + w, v)
    g.stroke()
  }
  g.strokeStyle = AXIS
  g.lineWidth = 3
  g.beginPath()
  g.moveTo(x, y)
  g.lineTo(x, y + h)
  g.lineTo(x + w, y + h)
  g.stroke()
}

/** A polyline through [x, y] points, drawn as far as `shown` (0 to the number of segments). */
function trace(g, points, shown, colour, width, dash = []) {
  if (shown <= 0) return
  g.strokeStyle = colour
  g.lineWidth = width
  g.lineJoin = 'round'
  g.lineCap = 'round'
  g.setLineDash(dash)
  g.beginPath()
  g.moveTo(...points[0])
  for (let i = 1; i < points.length; i++) {
    const part = clamp(shown - (i - 1))
    if (part <= 0) break
    const [ax, ay] = points[i - 1]
    const [bx, by] = points[i]
    g.lineTo(lerp(ax, bx, part), lerp(ay, by, part))
  }
  g.stroke()
  g.setLineDash([])
}

/** The corners of a staircase of [from, to, level] steps, through px(k) and py(level). */
function stairs(steps, px, py) {
  const points = []
  for (const [a, b, level] of steps) points.push([px(a), py(level)], [px(b), py(level)])
  return points
}

// the fee steps, as parts of the planning time: open, three raises, and the top once the drivers have planned
const STEPS = [
  [0, 0.3, 0.88],
  [0.3, 0.55, 1.05],
  [0.55, 0.8, 1.25],
  [0.8, 0.86, 1.55],
  [0.86, 1, 2.0],
]

/** stepped() and rested(): the fee rises three times while drivers plan their day, and not over the weekend. */
export function feePanel(g, t, duration, area) {
  g.save()
  const parts = card(g, t, duration, area, ORANGE, 0.55)
  if (!parts) {
    g.restore()
    return
  }
  // stepped(), with "Fees open low and rise three times…" (1.2–5.2 s): the steps draw in, a dot where each starts
  const [steps, weekend] = parts
  heading(g, t, 'stepped()', steps, 0.8)
  let b = steps.box
  axes(g, b)
  let px = (k) => b.x + k * b.w
  let py = (fee) => b.y + b.h - ((fee - 0.7) / 1.45) * b.h
  const line = stairs(STEPS, px, py)
  const shown = progress(t, 1.6, 5.2) * (line.length - 1)
  g.strokeStyle = '#64748b'
  g.setLineDash([10, 9])
  g.lineWidth = 2
  g.beginPath()
  g.moveTo(px(0.86), b.y)
  g.lineTo(px(0.86), b.y + b.h)
  g.stroke()
  g.setLineDash([])
  trace(g, line, shown, ORANGE, 8)
  g.fillStyle = ORANGE
  STEPS.forEach(([a, , level], i) => {
    if (shown < i * 2) return
    g.beginPath()
    g.arc(px(a), py(level), 9, 0, Math.PI * 2)
    g.fill()
  })

  // rested(), with "And no raises on weekends…" (7.9–11.9 s): over the weekend (the band) the fee would have risen
  // (dashed), but it stays where it is until Monday, and rises then
  heading(g, t, 'rested()', weekend, 7.8)
  const a = clamp((t - 7.8) / 0.3)
  if (a > 0) {
    g.globalAlpha *= a
    b = weekend.box
    px = (k) => b.x + k * b.w
    py = (fee) => b.y + b.h - ((fee - 0.7) / 1.45) * b.h
    g.fillStyle = '#172238'
    g.fillRect(px(0.14), b.y, px(0.62) - px(0.14), b.h)
    axes(g, b, 3)
    const would = STEPS.map(([s, e, level]) => [lerp(0.14, 0.62, s), lerp(0.14, 0.62, e), level])
    trace(g, stairs([[0, 0.14, 0.88], ...would], px, py), progress(t, 8.2, 9.6) * 11, '#94a3b8', 4, [10, 9])
    const held = [[0, 0.62, 0.88], ...STEPS.map(([s, e, level]) => [lerp(0.62, 1, s), lerp(0.62, 1, e), level])]
    trace(g, stairs(held, px, py), progress(t, 9.0, 11.4) * 11, ORANGE, 8)
  }
  g.restore()
}

/** A small car seen from the side, at x, y (its middle), in a colour. */
function carIcon(g, x, y, colour) {
  g.fillStyle = colour
  g.beginPath()
  g.roundRect(x - 34, y - 12, 68, 22, 8)
  g.fill()
  g.beginPath()
  g.roundRect(x - 20, y - 26, 38, 18, 6)
  g.fill()
  g.fillStyle = '#0f172a'
  for (const dx of [-18, 18]) {
    g.beginPath()
    g.arc(x + dx, y + 12, 8, 0, Math.PI * 2)
    g.fill()
  }
}

/** A driver: a head and a body, at x, y (the feet). */
function driverIcon(g, x, y) {
  g.fillStyle = '#fbbf24'
  g.beginPath()
  g.arc(x, y - 40, 12, 0, Math.PI * 2)
  g.fill()
  g.beginPath()
  g.roundRect(x - 12, y - 26, 24, 26, 6)
  g.fill()
}

/** findChains() and bookChance(): one driver for up to four cars in a row, and more of the chains book. */
export function chainPanel(g, t, duration, area) {
  g.save()
  const parts = card(g, t, duration, area, '#ef4444', 0.5)
  if (!parts) {
    g.restore()
    return
  }
  // findChains(), with "Chains: one driver takes up to four cars…" (0.9–5.2 s): four cars come in one by one on one
  // route, then the one driver goes from the first to the last
  const [cars, book] = parts
  heading(g, t, 'findChains()', cars, 0.8)
  let b = cars.box
  const row = b.y + b.h * 0.68
  const xs = [0, 1, 2, 3].map((i) => b.x + 34 + (i * (b.w - 68)) / 3)
  const shown = progress(t, 1.4, 4.4) * 4
  g.strokeStyle = AXIS
  g.lineWidth = 4
  g.setLineDash([12, 10])
  g.beginPath()
  g.moveTo(xs[0], row + 34)
  g.lineTo(xs[0] + (xs[3] - xs[0]) * clamp((shown - 1) / 3), row + 34)
  g.stroke()
  g.setLineDash([])
  xs.forEach((cx, i) => {
    const k = clamp(shown - i)
    if (k > 0) carIcon(g, cx, row + 18 * (1 - ease.outBack(k)), '#ef4444')
  })
  if (shown > 0.4) {
    const along = ease.inOutCubic(progress(t, 4.6, 6.6))
    driverIcon(g, lerp(xs[0], xs[3], along), row - 40)
  }

  // bookChance(), with "Each chain's fee follows its chance to book." (7.5–10.2 s): the share of chains that book,
  // before (grey) and with it (green), the grey one's height carried across
  heading(g, t, 'bookChance()', book, 7.4)
  const a = clamp((t - 7.4) / 0.3)
  if (a > 0) {
    g.globalAlpha *= a
    b = book.box
    axes(g, b, 4)
    const w = 120
    const left = b.x + b.w * 0.3 - w / 2
    const right = b.x + b.w * 0.7 - w / 2
    const tall = (share) => share * b.h
    const before = tall(0.53) * ease.outCubic(progress(t, 7.6, 8.2))
    g.fillStyle = '#64748b'
    g.fillRect(left, b.y + b.h - before, w, before)
    const after = tall(lerp(0, 0.71, ease.inOutCubic(progress(t, 8.4, 9.8))))
    g.fillStyle = GREEN
    g.fillRect(right, b.y + b.h - after, w, after)
    if (t > 8.2) {
      g.strokeStyle = '#94a3b8'
      g.lineWidth = 2
      g.setLineDash([10, 9])
      g.beginPath()
      g.moveTo(left, b.y + b.h - tall(0.53))
      g.lineTo(right + w, b.y + b.h - tall(0.53))
      g.stroke()
      g.setLineDash([])
    }
  }
  g.restore()
}

/** Demand.learn() and Supply.ratio(): each quote moves the win curve; each booking moves what a driver costs. */
export function learnPanel(g, t, duration, area) {
  g.save()
  const parts = card(g, t, duration, area, GREEN, 0.55)
  if (!parts) {
    g.restore()
    return
  }
  // Demand.learn(), with "Every won or lost quote moves the win curve." (0.7–3.7 s): a win at 1.50 moves the middle
  // up, a loss at 1.38 down, a win at 1.46 up again
  const [curve, ratio] = parts
  heading(g, t, 'Demand.learn()', curve, 0.8)
  let b = curve.box
  axes(g, b)
  const from = 1.1
  const to = 1.8
  const px = (p) => b.x + ((p - from) / (to - from)) * b.w
  const py = (v) => b.y + b.h - v * b.h
  const quotes = [
    [1.4, 1.5, true],
    [2.3, 1.38, false],
    [3.2, 1.46, true],
  ]
  const middles = [1.4, 1.46, 1.42, 1.45]
  let mu = middles[0]
  quotes.forEach(([at], i) => {
    mu = lerp(mu, middles[i + 1], ease.inOutCubic(progress(t, at + 0.15, at + 0.65)))
  })
  const chance = (p) => 1 / (1 + Math.exp((Math.log(p) - Math.log(mu)) / 0.11))
  g.strokeStyle = '#94a3b8'
  g.setLineDash([10, 9])
  g.lineWidth = 2
  g.beginPath()
  g.moveTo(px(mu), b.y)
  g.lineTo(px(mu), b.y + b.h)
  g.stroke()
  g.setLineDash([])
  g.strokeStyle = '#60a5fa'
  g.lineWidth = 7
  g.beginPath()
  for (let i = 0; i <= 80; i++) {
    const p = from + (i / 80) * (to - from)
    if (i === 0) g.moveTo(px(p), py(chance(p)))
    else g.lineTo(px(p), py(chance(p)))
  }
  g.stroke()
  for (const [at, p, won] of quotes) {
    const s = ease.outBack(progress(t, at, at + 0.3))
    if (s <= 0) continue
    g.fillStyle = won ? GREEN : RED
    g.beginPath()
    g.arc(px(p), py(won ? 0.92 : 0.08), 13 * s, 0, Math.PI * 2)
    g.fill()
  }

  // Supply.ratio(), with "Every booking teaches what drivers cost." (5.8–8.2 s): bookings come in one by one, and the
  // ratio climbs from 0.84 towards 0.97
  heading(g, t, 'Supply.ratio()', ratio, 5.6)
  const a = clamp((t - 5.6) / 0.3)
  if (a > 0) {
    g.globalAlpha *= a
    b = ratio.box
    axes(g, b, 3)
    const values = [0.84, 0.88, 0.9, 0.925, 0.94, 0.955, 0.965, 0.97]
    const qx = (i) => b.x + 20 + (i / (values.length - 1)) * (b.w - 40)
    const qy = (v) => b.y + b.h - ((v - 0.78) / 0.24) * b.h
    const shown = progress(t, 5.9, 8.4) * (values.length - 1)
    trace(
      g,
      values.map((v, i) => [qx(i), qy(v)]),
      shown,
      GREEN,
      6,
    )
    values.forEach((v, i) => {
      if (shown < i) return
      g.fillStyle = GREEN
      g.beginPath()
      g.arc(qx(i), qy(v), 9, 0, Math.PI * 2)
      g.fill()
    })
  }
  g.restore()
}

/** Where each card sits: the left or the right third, inside the title-safe frame, between the chapter tag and the
 * subtitles. */
export const AREAS = {
  left: { x: 96, y: 136, w: 560, h: 864 },
  right: { x: 1264, y: 136, w: 560, h: 864 },
}
