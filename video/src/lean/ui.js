import { ease, progress } from '../kit/anim.js'

// The ts:lean video's own look over the picture, in the style of a technical YouTube video: a chapter tag at the
// top left, a small mark at the top right, and subtitles in a dark box at the bottom. The picture is 1920×1200.

export const SANS = '"Inter", "SF Pro Display", -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif'
export const MONO = '"SF Mono", "JetBrains Mono", Menlo, Consolas, "Liberation Mono", monospace'
export const ACCENT = '#ef4444'
const PANEL = 'rgba(8, 12, 22, 0.78)'

function box(g, x, y, w, h, r, fill) {
  g.fillStyle = fill
  g.beginPath()
  g.roundRect(x, y, w, h, r)
  g.fill()
}

/** Lines of `text` no wider than `max` in the current font. */
function wrap(g, text, max) {
  const lines = []
  let line = ''
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word
    if (line && g.measureText(next).width > max) {
      lines.push(line)
      line = word
    } else line = next
  }
  if (line) lines.push(line)
  return lines
}

/** The chapter tag: its number in a red square and its title, sliding in over 0.35 s when the chapter starts. */
function chapterTag(g, { n, title }, since) {
  const k = ease.outCubic(progress(since, 0, 0.35))
  if (k <= 0) return
  g.save()
  g.globalAlpha = k
  g.translate(-40 * (1 - k), 0)
  g.font = `600 34px ${SANS}`
  const w = g.measureText(title).width
  box(g, 56, 48, 82 + w + 34, 64, 14, PANEL)
  box(g, 64, 56, 48, 48, 10, ACCENT)
  g.fillStyle = '#ffffff'
  g.textBaseline = 'middle'
  g.textAlign = 'center'
  g.font = `800 24px ${MONO}`
  g.fillText(n, 88, 81)
  g.textAlign = 'left'
  g.font = `600 34px ${SANS}`
  g.fillStyle = '#f8fafc'
  g.fillText(title, 128, 81)
  g.restore()
}

/** The mark at the top right: the strategy's name and the team. */
function mark(g, alpha = 1) {
  g.save()
  g.globalAlpha = alpha * 0.85
  g.textBaseline = 'middle'
  g.textAlign = 'right'
  g.font = `700 26px ${MONO}`
  g.fillStyle = '#e2e8f0'
  g.fillText('ts:lean', 1864 - 168, 80)
  g.font = `600 24px ${SANS}`
  g.fillStyle = '#94a3b8'
  g.fillText('· Blib Blib', 1864, 80)
  g.restore()
}

/**
 * What every frame gets on top: the chapter tag (from the first segment of the chapter, so it slides in once) and
 * the mark. A `bare` segment (a joke, the title card) gets neither.
 */
export function chrome(g, { segment, time, segments }) {
  if (segment.bare) return
  if (segment.chapter) {
    const first = segments.find((s) => s.chapter?.n === segment.chapter.n)
    chapterTag(g, segment.chapter, time - first.start)
  }
  mark(g)
}

/** Title-safe (90%) and action-safe (95%) frames, for checking the layout. */
export function titleSafe(g) {
  g.save()
  g.strokeStyle = 'rgba(255, 64, 160, 0.8)'
  g.lineWidth = 3
  g.setLineDash([16, 10])
  g.strokeRect(96, 60, 1728, 1080)
  g.strokeStyle = 'rgba(64, 200, 255, 0.8)'
  g.strokeRect(48, 30, 1824, 1140)
  g.restore()
}

/** A subtitle: `text` in a dark box at the bottom centre, wrapped to at most two lines, faded in and out. */
export function subtitle(g, t, text, t0, t1, { y = 1078, size = 44, max = 1460 } = {}) {
  if (t < t0 || t >= t1) return
  const alpha = Math.min(progress(t, t0, t0 + 0.12), 1 - progress(t, t1 - 0.12, t1))
  g.save()
  g.globalAlpha = alpha
  g.font = `600 ${size}px ${SANS}`
  const lines = wrap(g, text, max)
  const lineHeight = size * 1.28
  const w = Math.max(...lines.map((line) => g.measureText(line).width)) + size * 1.2
  const h = lineHeight * lines.length + size * 0.62
  const top = y - h / 2
  box(g, 960 - w / 2, top, w, h, 14, PANEL)
  g.fillStyle = '#f8fafc'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  lines.forEach((line, i) => {
    g.fillText(line, 960, top + size * 0.31 + lineHeight * (i + 0.5))
  })
  g.restore()
}

/** A lower third: a title and a line under it on a dark panel with a red edge, sliding in from the left at t0. */
export function lowerThird(g, t, title, line, { t0 = 0, x = 96, y = 860 } = {}) {
  const k = ease.outCubic(progress(t, t0, t0 + 0.45))
  if (k <= 0) return
  g.save()
  g.globalAlpha = k
  g.translate(-60 * (1 - k), 0)
  g.font = `800 92px ${MONO}`
  const w1 = g.measureText(title).width
  g.font = `600 40px ${SANS}`
  const w2 = g.measureText(line).width
  const w = Math.max(w1, w2) + 80
  box(g, x, y, w, 200, 18, PANEL)
  box(g, x, y, 10, 200, 4, ACCENT)
  g.fillStyle = '#ffffff'
  g.textAlign = 'left'
  g.textBaseline = 'middle'
  g.font = `800 92px ${MONO}`
  g.fillText(title, x + 44, y + 76)
  g.fillStyle = '#cbd5e1'
  g.font = `600 40px ${SANS}`
  g.fillText(line, x + 44, y + 154)
  g.restore()
}
