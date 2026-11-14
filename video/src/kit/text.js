import * as THREE from 'three'
import { ease, lerp, pop, progress } from './anim.js'

// 2D drawing on the output picture (1080×1920): the header, title cards, spoken lines and phone screens.

export const FONT = '"Arial Black", Impact, "Helvetica Neue", sans-serif'
export const UI = '"Helvetica Neue", Helvetica, Arial, sans-serif'

/** Text with a thick black outline, TikTok style. */
export function outlined(
  g,
  text,
  x,
  y,
  size,
  {
    fill = '#ffffff',
    stroke = '#000000',
    line = size * 0.18,
    italic = false,
    font = FONT,
    align = 'center',
    alpha = 1,
  } = {},
) {
  g.save()
  g.globalAlpha *= alpha
  g.font = `${italic ? 'italic ' : ''}900 ${size}px ${font}`
  g.textAlign = align
  g.textBaseline = 'middle'
  g.lineJoin = 'round'
  if (stroke && line > 0) {
    g.strokeStyle = stroke
    g.lineWidth = line
    g.strokeText(text, x, y)
  }
  g.fillStyle = fill
  g.fillText(text, x, y)
  g.restore()
}

/** Splits text into lines no wider than maxWidth in the current font of g. */
export function wrap(g, text, maxWidth) {
  const lines = []
  let line = ''
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word
    if (line && g.measureText(next).width > maxWidth) {
      lines.push(line)
      line = word
    } else line = next
  }
  if (line) lines.push(line)
  return lines
}

/** The largest size up to `size` at which text fits in maxWidth. */
function fit(g, text, size, maxWidth) {
  g.save()
  g.font = `900 ${size}px ${FONT}`
  const width = g.measureText(text).width
  g.restore()
  return width > maxWidth ? (size * maxWidth) / width : size
}

/** The header at the top of every frame. */
export function drawHeader(g, text) {
  const size = 48
  g.save()
  g.font = `900 ${size}px ${FONT}`
  const lines = wrap(g, text, 940)
  g.restore()
  lines.forEach((line, i) => {
    outlined(g, line, 540, 222 + i * size * 1.22, size, { line: 10 })
  })
}

/** A title card: the big number slams in, a red strip grows, the line types in. */
export function drawCard(g, t, duration, big, small) {
  const fade = 1 - progress(t, duration - 0.1, duration)
  const slam = t < 0.24 ? lerp(1.8, 1, ease.outBack(progress(t, 0, 0.24))) : 1
  g.save()
  g.globalAlpha = fade
  g.translate(540, 880)
  g.scale(slam, slam)
  g.rotate(-0.04)
  outlined(g, big, 0, 0, fit(g, big, 230, 960), { line: 28 })
  g.restore()
  const width = 860 * ease.outCubic(progress(t, 0.1, 0.32))
  const caps = small.toUpperCase()
  const shown = caps.slice(0, Math.ceil(caps.length * progress(t, 0.25, 0.25 + caps.length * 0.022)))
  g.save()
  g.globalAlpha = fade
  g.fillStyle = '#e8262b'
  g.fillRect(540 - width / 2, 1030, width, 96)
  outlined(g, shown, 540, 1080, fit(g, caps, 50, 820), { stroke: null })
  g.restore()
}

/** A spoken line: pops in at t0, types out over `type` seconds if given, fades out at t1. */
export function caption(
  g,
  t,
  text,
  {
    t0 = 0,
    t1 = Number.POSITIVE_INFINITY,
    x = 540,
    y = 1340,
    size = 88,
    type = 0,
    fill = '#ffffff',
    italic = false,
  } = {},
) {
  if (t < t0 || t >= t1) return
  const shown = type > 0 ? text.slice(0, Math.ceil(text.length * progress(t, t0, t0 + type))) : text
  const scale = type > 0 ? 1 : pop(t, t0, 0.2)
  const alpha = 1 - progress(t, t1 - 0.12, t1)
  g.save()
  g.font = `${italic ? 'italic ' : ''}900 ${size}px ${FONT}`
  const lines = wrap(g, shown, 920)
  g.translate(x, y)
  g.scale(scale, scale)
  lines.forEach((line, i) => {
    outlined(g, line, 0, (i - (lines.length - 1) / 2) * size * 1.12, size, { fill, italic, alpha })
  })
  g.restore()
}

function rounded(g, x, y, w, h, r) {
  g.beginPath()
  g.roundRect(x, y, w, h, r)
  g.fill()
}

/**
 * A phone screen in the picture with chat or price bubbles that pop in at their time.
 * rows: [{ text, t0, side: 'left' | 'right', bg, fg, size }]
 */
export function phone(g, t, { x = 540, y = 1180, w = 620, h = 760, rows = [], scale = 1, title = '' } = {}) {
  if (scale <= 0.01) return
  g.save()
  g.translate(x, y)
  g.scale(scale, scale)
  g.fillStyle = '#0d0d10'
  rounded(g, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 64)
  g.fillStyle = '#f2f4f7'
  rounded(g, -w / 2, -h / 2, w, h, 46)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  if (title) {
    g.fillStyle = '#5b6170'
    g.font = `700 34px ${UI}`
    g.fillText(title, 0, -h / 2 + 56)
  }
  let top = -h / 2 + 110
  for (const row of rows) {
    if (t < row.t0) continue
    const size = row.size ?? 44
    g.font = `800 ${size}px ${UI}`
    const bw = Math.min(g.measureText(row.text).width, w - 120) + 56
    const bh = size + 44
    const left = row.side === 'right' ? w / 2 - 30 - bw : -w / 2 + 30
    const s = ease.outBack(progress(t, row.t0, row.t0 + 0.18))
    g.save()
    g.translate(left + bw / 2, top + bh / 2)
    g.scale(s, s)
    g.fillStyle = row.bg ?? '#ffffff'
    rounded(g, -bw / 2, -bh / 2, bw, bh, 30)
    g.fillStyle = row.fg ?? '#111111'
    g.fillText(row.text, 0, 2)
    g.restore()
    top += bh + 24
  }
  g.restore()
}

/** A notification banner that slides down from the top between t0 and t1. */
export function banner(g, t, text, { t0 = 0, t1 = 1, y = 420 } = {}) {
  if (t < t0 || t >= t1) return
  const slide = ease.outBack(progress(t, t0, t0 + 0.25)) * (1 - ease.inQuad(progress(t, t1 - 0.2, t1)))
  g.save()
  g.translate(540, lerp(y - 260, y, slide))
  g.fillStyle = 'rgba(250,250,252,0.96)'
  rounded(g, -440, -70, 880, 140, 36)
  g.fillStyle = '#e8262b'
  rounded(g, -410, -40, 80, 80, 20)
  g.fillStyle = '#111111'
  g.font = `800 46px ${UI}`
  g.textAlign = 'left'
  g.textBaseline = 'middle'
  g.fillText(text, -300, 2)
  g.restore()
}

/** Shades the parts of the picture that TikTok's buttons and captions cover. */
export function drawSafeAreas(g) {
  g.save()
  g.fillStyle = 'rgba(255, 40, 120, 0.22)'
  g.fillRect(0, 0, 1080, 160)
  g.fillRect(0, 1500, 1080, 420)
  g.fillRect(940, 600, 140, 900)
  g.restore()
  outlined(g, 'TikTok buttons and caption', 540, 1700, 40, { line: 6, alpha: 0.8 })
}

const point = new THREE.Vector3()

/** Where a point of the 3D view lands on the 1080×1920 picture. Call it after the frame is rendered. */
export function toScreen(position, camera) {
  point.copy(position).project(camera)
  return [(point.x + 1) * 540, (1 - point.y) * 960]
}
