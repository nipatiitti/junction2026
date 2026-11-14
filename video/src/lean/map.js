import * as THREE from 'three'
import { clamp, ease, progress } from '../kit/anim.js'
import { liveTexture } from '../kit/sign.js'
import { CLASSES, FUNCTIONS, LINES, NOTES, ROADS, SIZES, SYSTEMS } from './diagram.js'
import { MONO, SANS } from './ui.js'

// The block diagram in 3D (the data is in diagram.js), in the dark style of a technical video: rounded panels for
// systems with a rim in their colour, plates for classes, tiles for functions, lanes and thin lines of data between
// them, every name painted flat on top. Everything lies on the ground and faces up, so a camera that looks straight
// down sees a drawing, and a tilted one a town with traffic.

export { MONO }

// Heights of the layers: panel tops, class plates, tiles, the data lines between them, lanes over everything.
const Y = { slab: 0.3, plate: 0.42, tile: 0.52, line: 0.46, road: 0.56 }
export const THEME = {
  ground: '#0a0f1c',
  grid: '#141c2e',
  gridMajor: '#1c2740',
  plate: '#172033',
  plateRim: '#34425f',
  tile: '#222d44',
  tileRim: '#4a5c80',
  text: '#e2e8f0',
  muted: '#8b9bb4',
  tag: '#4ade80',
  lane: '#273248',
  dash: '#7c8aa5',
  arrow: '#cbd5e1',
  line: '#52627f',
  learn: '#4ade80',
  light: '#fbbf24',
}

const cache = new Map()
/** A flat-shaded colour that keeps its exact value under the renderer's tone mapping. */
export function paint(color) {
  if (!cache.has(color)) cache.set(color, new THREE.MeshLambertMaterial({ color, toneMapped: false }))
  return cache.get(color)
}
/** An unlit colour. */
function flat(color, options = {}) {
  return new THREE.MeshBasicMaterial({ color, toneMapped: false, ...options })
}

const width = ([x0, , x1]) => x1 - x0
const depth = ([, z0, , z1]) => z1 - z0
const middle = ([x0, z0, x1, z1]) => [(x0 + x1) / 2, (z0 + z1) / 2]
/** The colour a part of the way from a to b. */
const blend = (a, b, k) => `#${new THREE.Color(a).lerp(new THREE.Color(b), k).getHexString()}`

/** A rounded panel of the rect's size, `height` thick, its top at `top`. */
export function panel(rect, height, top, material, radius = 0.6) {
  const w = width(rect)
  const d = depth(rect)
  const r = Math.min(radius, w / 2, d / 2)
  const shape = new THREE.Shape()
  shape.moveTo(-w / 2 + r, -d / 2)
  shape.lineTo(w / 2 - r, -d / 2)
  shape.quadraticCurveTo(w / 2, -d / 2, w / 2, -d / 2 + r)
  shape.lineTo(w / 2, d / 2 - r)
  shape.quadraticCurveTo(w / 2, d / 2, w / 2 - r, d / 2)
  shape.lineTo(-w / 2 + r, d / 2)
  shape.quadraticCurveTo(-w / 2, d / 2, -w / 2, d / 2 - r)
  shape.lineTo(-w / 2, -d / 2 + r)
  shape.quadraticCurveTo(-w / 2, -d / 2, -w / 2 + r, -d / 2)
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false, curveSegments: 4 })
  geometry.rotateX(Math.PI / 2)
  const mesh = new THREE.Mesh(geometry, material)
  const [x, z] = middle(rect)
  mesh.position.set(x, top, z)
  return mesh
}

/**
 * Text painted flat on the ground, facing up and reading towards -z: `size` is the height of a line in world units.
 * Returns the mesh, its width, and place(x, z) that puts its left end (or its middle) at x. Lines split on \n.
 */
export function label(
  text,
  { size, font = SANS, weight = 800, fill = THEME.text, align = 'left', y = 0, spacing = 0 },
) {
  const px = Math.round(clamp(size * 100, 96, 240))
  const lines = String(text).split('\n')
  const probe = document.createElement('canvas').getContext('2d')
  probe.font = `${weight} ${px}px ${font}`
  probe.letterSpacing = `${spacing * px}px`
  const pad = Math.ceil(px * 0.2)
  const lineHeight = px * 1.2
  const textWidth = Math.max(...lines.map((line) => probe.measureText(line).width))
  const canvas = document.createElement('canvas')
  canvas.width = Math.min(4096, Math.ceil(textWidth + pad * 2))
  canvas.height = Math.ceil(lineHeight * lines.length + pad * 2)
  const g = canvas.getContext('2d')
  g.font = `${weight} ${px}px ${font}`
  g.letterSpacing = `${spacing * px}px`
  g.textBaseline = 'middle'
  g.fillStyle = fill
  lines.forEach((line, i) => {
    g.fillText(line, pad, pad + lineHeight * (i + 0.5))
  })
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 8
  const unit = size / px
  const w = canvas.width * unit
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(w, canvas.height * unit),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false }),
  )
  mesh.rotation.x = -Math.PI / 2
  mesh.position.y = y
  mesh.renderOrder = 2
  const place = (x, z) => {
    mesh.position.x = align === 'left' ? x - pad * unit + w / 2 : x
    mesh.position.z = z
    return mesh
  }
  return { mesh, width: textWidth * unit, place }
}

/** A frame of four glowing bars around a rect, to light a block up; set its opacity. */
function outline(rect, thickness, y) {
  const material = flat(THEME.light, { transparent: true, opacity: 0, depthWrite: false })
  const group = new THREE.Group()
  const [x0, z0, x1, z1] = rect
  const t = thickness
  const bar = (w, d, x, z) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, 0.05, d), material)
    m.position.set(x, y, z)
    m.renderOrder = 4
    group.add(m)
  }
  bar(x1 - x0 + 2 * t, t, (x0 + x1) / 2, z0 - t / 2)
  bar(x1 - x0 + 2 * t, t, (x0 + x1) / 2, z1 + t / 2)
  bar(t, z1 - z0, x0 - t / 2, (z0 + z1) / 2)
  bar(t, z1 - z0, x1 + t / 2, (z0 + z1) / 2)
  group.visible = false
  return {
    group,
    set(a) {
      material.opacity = a
      group.visible = a > 0.01
    },
  }
}

/** A strip from a to b of the given width, as a thin box at height y. */
function strip(a, b, w, y, material, thickness = 0.02) {
  const dx = b[0] - a[0]
  const dz = b[1] - a[1]
  const m = new THREE.Mesh(new THREE.BoxGeometry(Math.hypot(dx, dz), thickness, w), material)
  m.position.set((a[0] + b[0]) / 2, y, (a[1] + b[1]) / 2)
  m.rotation.y = -Math.atan2(dz, dx)
  return m
}

/** The dark ground with a grid of fine and major lines. */
export function ground() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 512
  const g = canvas.getContext('2d')
  g.fillStyle = THEME.ground
  g.fillRect(0, 0, 512, 512)
  for (let i = 0; i <= 10; i++) {
    g.fillStyle = i % 5 === 0 ? THEME.gridMajor : THEME.grid
    const w = i % 5 === 0 ? 4 : 2
    g.fillRect(i * 51.2 - w / 2, 0, w, 512)
    g.fillRect(0, i * 51.2 - w / 2, 512, w)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.anisotropy = 8
  const size = 1200
  texture.repeat.set(size / 25, size / 25) // a major line every 25 units, a fine one every 5
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(size, size), flat('#ffffff', { map: texture }))
  plane.rotation.x = -Math.PI / 2
  return plane
}

/**
 * The chart inside bestPrice(), drawn in as `k` goes from 0 to 1: the win chance, the margin and their product, with
 * the peak marked; the name and the formula beside it. The tile is 16:10, as the picture, and fills most of it at the
 * end of the zoom.
 */
function chartPainter(g, { k }, w, h) {
  const mu = Math.log(1.4)
  const scale = 0.11
  const cost = 1.0
  const chance = (p) => 1 / (1 + Math.exp((Math.log(p) - mu) / scale))
  const from = 0.9
  const to = 2.0
  g.fillStyle = '#0f172a'
  g.fillRect(0, 0, w, h)
  g.textBaseline = 'middle'
  g.textAlign = 'left'
  g.fillStyle = '#f8fafc'
  g.font = `700 64px ${MONO}`
  g.fillText('bestPrice()', 64, 78)
  g.fillStyle = THEME.muted
  g.font = `500 34px ${MONO}`
  g.fillText('demand.ts', 64, 134)

  // the plot on the left
  const left = 120
  const right = 900
  const top = 220
  const bottom = 820
  const px = (p) => left + ((p - from) / (to - from)) * (right - left)
  const py = (v) => bottom - v * (bottom - top)
  g.strokeStyle = '#1e293b'
  g.lineWidth = 2
  for (let v = 0; v <= 1.001; v += 0.25) {
    g.beginPath()
    g.moveTo(left, py(v))
    g.lineTo(right, py(v))
    g.stroke()
  }
  g.strokeStyle = '#64748b'
  g.lineWidth = 4
  g.beginPath()
  g.moveTo(left, top - 20)
  g.lineTo(left, bottom)
  g.lineTo(right + 10, bottom)
  g.stroke()
  g.fillStyle = '#94a3b8'
  g.font = `500 30px ${MONO}`
  g.textAlign = 'center'
  for (const p of [1.0, 1.2, 1.4, 1.6, 1.8, 2.0]) {
    g.fillText(p.toFixed(1), px(p), bottom + 36)
    g.fillRect(px(p) - 1.5, bottom, 3, 10)
  }
  g.fillText('price × list', (left + right) / 2, bottom + 84)
  g.textAlign = 'right'
  for (const v of [0, 0.5, 1]) g.fillText(v.toFixed(1), left - 16, py(v))

  const curve = (f, a, b, colour, lineWidth = 7) => {
    const span = clamp((k - a) / (b - a))
    if (span <= 0) return
    g.strokeStyle = colour
    g.lineWidth = lineWidth
    g.lineJoin = 'round'
    g.lineCap = 'round'
    g.beginPath()
    const steps = 160
    for (let i = 0; i <= steps * span; i++) {
      const p = from + (i / steps) * (to - from)
      const x = px(p)
      const v = py(clamp(f(p), 0, 1.03))
      if (i === 0) g.moveTo(x, v)
      else g.lineTo(x, v)
    }
    g.stroke()
  }
  // the margin is drawn on 0 to 1 (p − cost is 1 at p = 2); the product at 2.5 times its size
  curve(chance, 0.05, 0.35, '#60a5fa')
  curve((p) => p - cost, 0.3, 0.55, '#fb923c')
  curve((p) => chance(p) * (p - cost) * 2.5, 0.55, 0.85, '#4ade80', 10)

  // the peak: the quote
  if (k > 0.85) {
    const s = ease.outBack(progress(k, 0.85, 1))
    const peak = 1.35
    const x = px(peak)
    const v = py(chance(peak) * (peak - cost) * 2.5)
    g.strokeStyle = '#4ade80'
    g.setLineDash([14, 12])
    g.lineWidth = 3
    g.beginPath()
    g.moveTo(x, v)
    g.lineTo(x, bottom)
    g.stroke()
    g.setLineDash([])
    g.fillStyle = '#4ade80'
    g.beginPath()
    g.arc(x, v, 16 * s, 0, Math.PI * 2)
    g.fill()
    g.save()
    g.translate(x + 30, v - 130)
    g.scale(s, s)
    g.fillStyle = '#14532d'
    g.strokeStyle = '#4ade80'
    g.lineWidth = 3
    g.beginPath()
    g.roundRect(0, -56, 470, 124, 16)
    g.fill()
    g.stroke()
    g.fillStyle = '#f0fdf4'
    g.textAlign = 'left'
    g.font = `700 42px ${MONO}`
    g.fillText('quote 1.35 × list', 24, -18)
    g.fillStyle = '#bbf7d0'
    g.font = `500 32px ${SANS}`
    g.fillText('58% of these quotes win', 24, 34)
    g.restore()
  }

  // the legend and the formula on the right
  const panelX = 950
  g.textAlign = 'left'
  const legend = [
    ['#60a5fa', 'chance(p)', 'the dealer takes it', 0.05],
    ['#fb923c', 'p − cost', 'what is left', 0.3],
    ['#4ade80', 'chance × margin', 'what we expect', 0.55],
  ]
  legend.forEach(([colour, name, what, at], i) => {
    const y = 250 + i * 92
    g.globalAlpha = clamp((k - at) / 0.08)
    g.fillStyle = colour
    g.fillRect(panelX, y - 4, 44, 8)
    g.fillStyle = '#f1f5f9'
    g.font = `600 34px ${MONO}`
    g.fillText(name, panelX + 64, y - 14)
    g.fillStyle = THEME.muted
    g.font = `500 28px ${SANS}`
    g.fillText(what, panelX + 64, y + 24)
    g.globalAlpha = 1
  })
  g.fillStyle = '#1e293b'
  g.beginPath()
  g.roundRect(panelX - 24, 560, w - panelX - 8, 300, 16)
  g.fill()
  g.fillStyle = '#e2e8f0'
  g.font = `600 28px ${MONO}`
  const formula = [
    'quote = argmax chance(p) ×',
    '  (p·list − cost·(1 + 0.47·load))',
    'chance(p) = 1/(1 + e^((ln p − μ)/s))',
    'μ = ln 1.40   s = 0.11',
  ]
  formula.forEach((line, i) => {
    g.fillText(line, panelX, 610 + i * 52)
  })
  g.fillStyle = THEME.muted
  g.font = `500 26px ${SANS}`
  g.fillText('p from 0.90 to 3.00 × list, in steps of 0.01', panelX, 830)
}

/**
 * Builds the diagram into `scene`. Returns { heights, highlight(id, a), chart(k) }: highlight lights a block up (a from
 * 0 to 1), chart draws bestPrice()'s chart in.
 */
export function buildMap(scene) {
  const lit = new Map()
  scene.add(ground())

  for (const system of SYSTEMS) {
    const { rect, color } = system
    scene.add(panel(rect, 0.3, Y.slab - 0.02, paint(color), 1.2))
    const inner = [rect[0] + 0.35, rect[1] + 0.35, rect[2] - 0.35, rect[3] - 0.35]
    scene.add(panel(inner, 0.3, Y.slab, paint(blend(color, THEME.ground, 0.84)), 1.0))
    const name = label(system.label, { size: SIZES.system, fill: color, y: Y.slab + 0.01, spacing: 0.02 })
    const path = label(system.path, {
      size: SIZES.function,
      font: MONO,
      weight: 500,
      fill: THEME.muted,
      y: Y.slab + 0.01,
    })
    const z = rect[1] + SIZES.system * 0.62
    if (system.align === 'center') {
      const total = name.width + 1.8 + path.width
      const x = middle(rect)[0] - total / 2
      scene.add(name.place(x, z), path.place(x + name.width + 1.8, z + 0.4))
    } else if (system.pathBelow) {
      scene.add(name.place(rect[0] + 1.4, z), path.place(rect[0] + 1.5, z + SIZES.system * 0.82))
    } else {
      scene.add(name.place(rect[0] + 1.4, z), path.place(rect[0] + 1.4 + name.width + 1.8, z + 0.4))
    }
    if (system.note)
      scene.add(
        label(system.note, {
          size: SIZES.function,
          font: MONO,
          weight: 500,
          fill: THEME.muted,
          y: Y.slab + 0.01,
        }).place(rect[0] + 1.5, z + SIZES.system * (system.pathBelow ? 1.2 : 0.95)),
      )
    const frame = outline(rect, 0.7, Y.road + 0.05)
    scene.add(frame.group)
    lit.set(system.id, frame)
  }

  for (const cls of CLASSES) {
    const { rect } = cls
    scene.add(
      panel(
        [rect[0] - 0.16, rect[1] - 0.16, rect[2] + 0.16, rect[3] + 0.16],
        0.1,
        Y.plate - 0.01,
        paint(THEME.plateRim),
        0.5,
      ),
    )
    scene.add(panel(rect, 0.1, Y.plate, paint(THEME.plate), 0.4))
    const [lx, lz] = cls.labelAt ?? [rect[0] + 0.7, rect[1] + 1.5]
    scene.add(label(cls.id, { size: SIZES.class, weight: 700, y: Y.plate + 0.01 }).place(lx, lz))
    if (cls.note)
      scene.add(
        label(cls.note, { size: SIZES.tag, font: MONO, weight: 500, fill: THEME.muted, y: Y.plate + 0.01 }).place(
          rect[0] + 0.7,
          rect[1] + 4.6,
        ),
      )
    const frame = outline(rect, 0.4, Y.road + 0.06)
    scene.add(frame.group)
    lit.set(cls.id, frame)
  }

  let chart = null
  for (const fn of FUNCTIONS) {
    const { rect } = fn
    scene.add(
      panel(
        [rect[0] - 0.12, rect[1] - 0.12, rect[2] + 0.12, rect[3] + 0.12],
        0.1,
        Y.tile - 0.01,
        paint(THEME.tileRim),
        0.4,
      ),
    )
    scene.add(panel(rect, 0.1, Y.tile, paint(THEME.tile), 0.3))
    const [cx, cz] = middle(rect)
    if (fn.chart) {
      // bestPrice(): its tile is the chart, name and all
      const texture = liveTexture(1600, 1000, chartPainter)
      texture.texture.anisotropy = 8
      const face = new THREE.Mesh(
        new THREE.PlaneGeometry(width(rect) - 0.2, depth(rect) - 0.2),
        new THREE.MeshBasicMaterial({ map: texture.texture, toneMapped: false }),
      )
      face.rotation.x = -Math.PI / 2
      face.position.set(cx, Y.tile + 0.01, cz)
      face.renderOrder = 1
      scene.add(face)
      chart = texture
    } else {
      const name = label(fn.label, { size: SIZES.function, font: MONO, weight: 600, align: 'center', y: Y.tile + 0.01 })
      scene.add(name.place(cx, fn.tag ? rect[1] + 0.95 : cz))
      if (fn.tag)
        scene.add(
          label(fn.tag, {
            size: SIZES.tag,
            font: MONO,
            weight: 700,
            fill: THEME.tag,
            align: 'center',
            y: Y.tile + 0.01,
          }).place(cx, rect[3] - 0.72),
        )
    }
    const frame = outline(rect, 0.3, Y.road + 0.07)
    scene.add(frame.group)
    lit.set(fn.id, frame)
  }

  for (const [text, x, z, align] of NOTES)
    scene.add(
      label(text, { size: SIZES.tag, font: MONO, weight: 500, fill: THEME.muted, align, y: Y.slab + 0.01 }).place(x, z),
    )

  // Lanes: a dashed middle line, and an arrowhead where the traffic leaves them
  const lane = paint(THEME.lane)
  const dash = flat(THEME.dash)
  const arrowPaint = flat(THEME.arrow)
  for (const road of ROADS) {
    const w = road.width ?? 2.4
    const points = road.points
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1]
      const b = points[i]
      scene.add(strip(a, b, w, Y.road, lane))
      if (w >= 2) {
        const length = Math.hypot(b[0] - a[0], b[1] - a[1])
        for (let s = 0.6; s + 1.0 < length; s += 2.2) {
          const p = [a[0] + ((b[0] - a[0]) * s) / length, a[1] + ((b[1] - a[1]) * s) / length]
          const q = [a[0] + ((b[0] - a[0]) * (s + 1.0)) / length, a[1] + ((b[1] - a[1]) * (s + 1.0)) / length]
          scene.add(strip(p, q, 0.14, Y.road + 0.015, dash, 0.01))
        }
      }
      if (i > 1) {
        const corner = new THREE.Mesh(new THREE.BoxGeometry(w, 0.02, w), lane)
        corner.position.set(a[0], Y.road, a[1])
        scene.add(corner)
      }
    }
    const [a, b] = points.slice(-2)
    const heading = Math.atan2(b[1] - a[1], b[0] - a[0])
    const arrow = new THREE.Mesh(
      new THREE.ShapeGeometry(
        new THREE.Shape([new THREE.Vector2(0.9, 0), new THREE.Vector2(-0.6, 0.75), new THREE.Vector2(-0.6, -0.75)]),
      ),
      arrowPaint,
    )
    arrow.scale.setScalar(w / 2.4)
    arrow.rotation.set(-Math.PI / 2, 0, -heading)
    arrow.position.set(b[0] - Math.cos(heading) * 1.2, Y.road + 0.02, b[1] - Math.sin(heading) * 1.2)
    scene.add(arrow)
    if (road.label) {
      const text = label(road.label, {
        size: SIZES.function,
        font: MONO,
        weight: 600,
        fill: THEME.muted,
        align: 'center',
        y: Y.road + 0.03,
      })
      const mesh = text.place(...road.labelAt)
      if (road.turn) mesh.rotation.z = Math.PI / 2
      scene.add(mesh)
    }
  }

  // Lines of data, under the tiles
  const ink = paint(THEME.line)
  const green = flat(THEME.learn)
  for (const line of LINES) {
    for (let i = 1; i < line.points.length; i++) {
      const a = line.points[i - 1]
      const b = line.points[i]
      if (!line.dotted) {
        scene.add(strip(a, b, 0.22, Y.line, ink, 0.03))
        continue
      }
      const length = Math.hypot(b[0] - a[0], b[1] - a[1])
      for (let s = 0; s < length; s += 0.8) {
        const e = Math.min(length, s + 0.4)
        const p = [a[0] + ((b[0] - a[0]) * s) / length, a[1] + ((b[1] - a[1]) * s) / length]
        const q = [a[0] + ((b[0] - a[0]) * e) / length, a[1] + ((b[1] - a[1]) * e) / length]
        scene.add(strip(p, q, 0.22, Y.line, green, 0.03))
      }
    }
  }

  return {
    heights: Y,
    highlight(id, a) {
      lit.get(id)?.set(a)
    },
    chart(k) {
      chart?.set({ k: Math.round(clamp(k) * 200) / 200 })
    },
  }
}
