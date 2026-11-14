import { clamp, ease, lerp, progress } from '../kit/anim.js'
import { MONO, SANS } from './ui.js'

// The cards that explain a decision while the camera shows its blocks: the fee schedule, the chains, and the win
// curve learning. Each is drawn over the picture in a third of it (the camera leaves that third to the card), comes
// in at 0.6 s, builds up with the voice, and goes out over the last 0.3 s of its segment. The numbers are the code's
// defaults and the measured effects in src/strategies/lean/README.md.

const PANEL = 'rgba(11, 17, 30, 0.94)'
const TEXT = '#e2e8f0'
const MUTED = '#8b9bb4'
const GREEN = '#4ade80'

/** The card's frame and title; returns false while it is not on. */
function card(g, t, duration, { x, y, w, h }, title, line, colour) {
  const k = ease.outCubic(progress(t, 0.6, 1.0)) * (1 - progress(t, duration - 0.3, duration))
  if (k <= 0) return false
  g.globalAlpha = k
  g.translate(-30 * (1 - k), 0)
  g.fillStyle = PANEL
  g.beginPath()
  g.roundRect(x, y, w, h, 20)
  g.fill()
  g.fillStyle = colour
  g.fillRect(x, y, w, 7)
  g.textAlign = 'left'
  g.textBaseline = 'middle'
  g.fillStyle = '#f8fafc'
  g.font = `700 30px ${MONO}`
  g.fillText(title, x + 32, y + 54)
  g.fillStyle = MUTED
  g.font = `500 24px ${SANS}`
  g.fillText(line, x + 32, y + 94)
  return true
}

function tag(g, x, y, text, colour = GREEN) {
  g.font = `700 24px ${MONO}`
  const w = g.measureText(text).width + 28
  g.fillStyle = 'rgba(20, 83, 45, 0.9)'
  g.beginPath()
  g.roundRect(x, y - 19, w, 38, 19)
  g.fill()
  g.fillStyle = colour
  g.textAlign = 'left'
  g.fillText(text, x + 14, y + 1)
  return w
}

/** stepped(), planBy() and rested(): the fee climbs in three steps over the drivers' planning time. */
export function feePanel(g, t, duration, area) {
  g.save()
  if (!card(g, t, duration, area, 'stepped() · planBy()', 'the fee a gig shows, × typical', '#f59e0b')) {
    g.restore()
    return
  }
  const { x, y, w } = area
  const left = x + 90
  const right = x + w - 40
  const top = y + 170
  const bottom = y + 470
  const px = (k) => left + k * (right - left)
  const py = (fee) => bottom - ((fee - 0.8) / 1.25) * (bottom - top)
  g.strokeStyle = '#334155'
  g.lineWidth = 2
  for (const fee of [1.0, 1.5, 2.0]) {
    g.beginPath()
    g.moveTo(left, py(fee))
    g.lineTo(right, py(fee))
    g.stroke()
    g.fillStyle = MUTED
    g.font = `500 22px ${MONO}`
    g.textAlign = 'right'
    g.fillText(fee.toFixed(1), left - 14, py(fee))
  }
  g.textAlign = 'left'
  g.fillText('posted', left - 4, bottom + 30)
  g.textAlign = 'right'
  g.fillText('plan by', px(0.86), bottom + 30)
  // the steps: open, three raises at 30%, 55% and 80% of the planning time, the top when it is over
  const steps = [
    [0, 0.3, 0.88],
    [0.3, 0.55, 1.05],
    [0.55, 0.8, 1.25],
    [0.8, 0.86, 1.55],
    [0.86, 1, 2.0],
  ]
  const shown = progress(t, 1.2, 4.4) * steps.length
  g.strokeStyle = '#f59e0b'
  g.lineWidth = 7
  g.lineJoin = 'round'
  g.beginPath()
  steps.forEach(([a, b, fee], i) => {
    const part = clamp(shown - i)
    if (part <= 0) return
    if (i === 0) g.moveTo(px(a), py(fee))
    else g.lineTo(px(a), py(fee))
    g.lineTo(px(lerp(a, b, part)), py(fee))
  })
  g.stroke()
  g.fillStyle = TEXT
  g.font = `600 22px ${MONO}`
  g.textAlign = 'center'
  steps.forEach(([a, b, fee], i) => {
    if (shown - i < 0.5) return
    g.fillText(i === 4 ? 'top 2.0' : fee.toFixed(2), px((a + b) / 2), py(fee) - 24)
  })
  g.strokeStyle = '#64748b'
  g.setLineDash([10, 8])
  g.lineWidth = 2
  g.beginPath()
  g.moveTo(px(0.86), top - 10)
  g.lineTo(px(0.86), bottom)
  g.stroke()
  g.setLineDash([])
  g.textAlign = 'left'
  g.fillStyle = MUTED
  g.font = `500 22px ${SANS}`
  g.fillText('drivers plan the day before: by 21:00', x + 32, bottom + 76)
  g.fillText('for a pickup before 16:00', x + 32, bottom + 106)
  if (t > 1.6) tag(g, x + 32, bottom + 152, 'every week ranked')
  // rested(): the weekend
  const weekend = ease.outCubic(progress(t, 5.2, 5.7))
  if (weekend > 0) {
    g.globalAlpha *= weekend
    g.fillStyle = '#1e293b'
    g.beginPath()
    g.roundRect(x + 24, bottom + 190, w - 48, 92, 14)
    g.fill()
    g.fillStyle = TEXT
    g.font = `700 24px ${MONO}`
    g.fillText('rested()', x + 48, bottom + 220)
    g.fillStyle = MUTED
    g.font = `500 22px ${SANS}`
    g.fillText("Monday's cars: no raises Sat–Sun", x + 48, bottom + 254)
    tag(g, x + w - 210, bottom + 220, '+€624 a week')
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

/** findChains() and bookChance(): up to four cars for one driver, and a fee by the chain's chance to book. */
export function chainPanel(g, t, duration, area) {
  g.save()
  if (!card(g, t, duration, area, 'findChains() · bookChance()', 'one driver, up to four cars in a row', '#ef4444')) {
    g.restore()
    return
  }
  const { x, y, w } = area
  const row = y + 220
  const xs = [0, 1, 2, 3].map((i) => x + 80 + i * ((w - 160) / 3))
  const shown = progress(t, 1.0, 3.8) * 4
  xs.forEach((cx, i) => {
    const k = clamp(shown - i)
    if (k <= 0) return
    g.globalAlpha = g.globalAlpha * 1
    carIcon(g, cx, row + 20 * (1 - ease.outBack(k)), '#ef4444')
    if (i > 0) {
      g.strokeStyle = MUTED
      g.lineWidth = 3
      g.beginPath()
      g.moveTo(xs[i - 1] + 42, row)
      g.lineTo(cx - 44, row)
      g.stroke()
      g.fillStyle = MUTED
      g.font = `500 20px ${MONO}`
      g.textAlign = 'center'
      g.fillText('≤ 60 min', (xs[i - 1] + cx) / 2, row - 34)
    }
  })
  // the one driver above the first car
  if (shown > 0.4) {
    g.fillStyle = '#fbbf24'
    g.beginPath()
    g.arc(xs[0], row - 70, 12, 0, Math.PI * 2)
    g.fill()
    g.fillRect(xs[0] - 9, row - 56, 18, 22)
  }
  g.textAlign = 'left'
  g.fillStyle = TEXT
  g.font = `500 24px ${SANS}`
  const facts = ['at most 8 hours of driving', 'at least 15% under the cars’ fees']
  facts.forEach((fact, i) => {
    if (t > 2.4 + i * 0.6) g.fillText(`· ${fact}`, x + 32, row + 90 + i * 38)
  })
  if (t > 3.4) tag(g, x + 32, row + 190, '+€1,560 a week')
  // bookChance(): more of the posted chains book
  const booked = ease.inOutCubic(progress(t, 5.4, 7.2))
  if (t > 5.0) {
    const top = row + 250
    g.fillStyle = TEXT
    g.font = `700 24px ${MONO}`
    g.fillText('bookChance()', x + 32, top)
    g.fillStyle = MUTED
    g.font = `500 22px ${SANS}`
    g.fillText('chains that book', x + 32, top + 36)
    const barX = x + 32
    const barW = w - 64
    g.fillStyle = '#1e293b'
    g.fillRect(barX, top + 60, barW, 26)
    g.fillStyle = '#64748b'
    g.fillRect(barX, top + 60, barW * 0.53, 26)
    g.fillStyle = GREEN
    g.fillRect(barX, top + 60, barW * lerp(0.53, 0.71, booked), 26)
    g.fillStyle = TEXT
    g.font = `700 22px ${MONO}`
    g.fillText(`${Math.round(lerp(53, 71, booked))}%`, barX + barW * lerp(0.53, 0.71, booked) + 10, top + 74)
    if (t > 6.8) tag(g, x + 32, top + 124, '+€1,126 a week')
  }
  g.restore()
}

/** Demand.learn() and Supply.learn(): each quote moves the win curve, each booking the cost of a place. */
export function learnPanel(g, t, duration, area) {
  g.save()
  if (!card(g, t, duration, area, 'learn()', 'Demand: the win curve · Supply: the cost', '#4ade80')) {
    g.restore()
    return
  }
  const { x, y, w } = area
  const left = x + 70
  const right = x + w - 40
  const top = y + 150
  const bottom = y + 420
  const from = 1.1
  const to = 1.8
  const px = (p) => left + ((p - from) / (to - from)) * (right - left)
  const py = (v) => bottom - v * (bottom - top)
  // three quotes: a win at 1.50 moves the middle up, a loss at 1.38 down, a win at 1.46 up again
  const quotes = [
    [1.0, 1.5, true],
    [2.0, 1.38, false],
    [3.0, 1.46, true],
  ]
  const middles = [1.4, 1.46, 1.42, 1.45]
  let mu = middles[0]
  quotes.forEach(([at], i) => {
    mu = lerp(mu, middles[i + 1], ease.inOutCubic(progress(t, at + 0.15, at + 0.65)))
  })
  const chance = (p) => 1 / (1 + Math.exp((Math.log(p) - Math.log(mu)) / 0.11))
  g.strokeStyle = '#334155'
  g.lineWidth = 2
  g.beginPath()
  g.moveTo(left, top - 10)
  g.lineTo(left, bottom)
  g.lineTo(right, bottom)
  g.stroke()
  g.strokeStyle = '#60a5fa'
  g.lineWidth = 6
  g.beginPath()
  for (let i = 0; i <= 80; i++) {
    const p = from + (i / 80) * (to - from)
    if (i === 0) g.moveTo(px(p), py(chance(p)))
    else g.lineTo(px(p), py(chance(p)))
  }
  g.stroke()
  g.strokeStyle = '#94a3b8'
  g.setLineDash([8, 8])
  g.lineWidth = 2
  g.beginPath()
  g.moveTo(px(mu), top)
  g.lineTo(px(mu), bottom)
  g.stroke()
  g.setLineDash([])
  g.fillStyle = MUTED
  g.font = `500 20px ${MONO}`
  g.textAlign = 'center'
  g.fillText(`middle ${mu.toFixed(2)} × list`, px(mu), top - 22)
  g.fillText('price × list', (left + right) / 2, bottom + 30)
  quotes.forEach(([at, p, won]) => {
    if (t < at) return
    g.fillStyle = won ? GREEN : '#f87171'
    g.beginPath()
    g.arc(px(p), py(won ? 0.9 : 0.1), 12, 0, Math.PI * 2)
    g.fill()
    g.fillStyle = TEXT
    g.font = `600 18px ${MONO}`
    g.fillText(won ? 'won' : 'lost', px(p), py(won ? 0.9 : 0.1) - 22)
  })
  g.textAlign = 'left'
  g.fillStyle = TEXT
  g.font = `500 22px ${SANS}`
  g.fillText('each quote moves its dealer, places, day', x + 32, bottom + 74)
  g.fillText('and option by their share of the doubt', x + 32, bottom + 104)
  // Supply: what bookings pay for such a car here
  const k = ease.inOutCubic(progress(t, 4.4, 6.4))
  if (t > 4.2) {
    const top2 = bottom + 150
    g.fillStyle = TEXT
    g.font = `700 24px ${MONO}`
    g.fillText('Supply.ratio()', x + 32, top2)
    g.fillStyle = MUTED
    g.font = `500 22px ${SANS}`
    g.fillText('what a booking here costs, × typical', x + 32, top2 + 34)
    g.fillStyle = '#f8fafc'
    g.font = `700 44px ${MONO}`
    g.fillText(`${lerp(0.84, 0.97, k).toFixed(2)}`, x + 32, top2 + 92)
    if (t > 6.0) tag(g, x + 190, top2 + 90, '+€769 a week (sim)')
  }
  g.restore()
}

/** Where each card sits: the left or the right third, above the subtitles. */
export const AREAS = {
  left: { x: 64, y: 150, w: 600, h: 840 },
  right: { x: 1256, y: 150, w: 600, h: 840 },
}
