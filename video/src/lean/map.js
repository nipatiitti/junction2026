import * as THREE from 'three'
import { clamp, ease, progress } from '../kit/anim.js'
import { liveTexture } from '../kit/sign.js'
import { CLASSES, FUNCTIONS, LINES, ROADS, SIZES, SYSTEMS } from './diagram.js'
import { MONO, SANS } from './ui.js'

// The block diagram in 3D (the data is in diagram.js), in the dark style of a technical video: rounded panels for
// systems with a rim in their colour, plates for classes, tiles for functions, lanes and thin lines of data between
// them, every name painted flat on top. The names are the only words on it. Everything lies on the ground and faces
// up, so a camera that looks straight down sees a drawing, and a tilted one a town with traffic.

/** How far a system's name sits inside its edge, and the middle of its line below the top edge. */
const INSET = 1.5
const TITLE = SIZES.system * 0.62
/** How far a class's name sits inside its plate, and the middle of its line below the plate's top edge. */
const PAD = 0.8
const CLASS_LINE = 1.7

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
 * The chart inside bestPrice(), drawn in as `k` goes from 0 to 1: the win chance (blue), the margin (orange) and their
 * product (green), with its peak, the quote, marked. Its name is the only word on it; the voice says the rest. The
 * tile is 16:10, as the picture, and fills most of it at the end of the zoom. The plot keeps one margin, 80 px, from
 * the tile's edges, under the name.
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
  g.font = `700 72px ${MONO}`
  g.fillText('bestPrice()', 80, 104)

  // the plot, under the name
  const left = 80
  const right = w - 80
  const top = 210
  const bottom = h - 80
  const px = (p) => left + ((p - from) / (to - from)) * (right - left)
  const py = (v) => bottom - v * (bottom - top)
  g.strokeStyle = '#1e293b'
  g.lineWidth = 2
  for (let v = 0.25; v <= 1.001; v += 0.25) {
    g.beginPath()
    g.moveTo(left, py(v))
    g.lineTo(right, py(v))
    g.stroke()
  }
  g.strokeStyle = '#64748b'
  g.lineWidth = 4
  g.beginPath()
  g.moveTo(left, top)
  g.lineTo(left, bottom)
  g.lineTo(right, bottom)
  g.stroke()

  const curve = (f, a, b, colour, lineWidth = 8) => {
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
  curve((p) => chance(p) * (p - cost) * 2.5, 0.55, 0.85, '#4ade80', 11)

  // the peak: the quote
  if (k > 0.85) {
    const s = ease.outBack(progress(k, 0.85, 1))
    const peak = 1.35
    const x = px(peak)
    const v = py(chance(peak) * (peak - cost) * 2.5)
    g.strokeStyle = '#4ade80'
    g.setLineDash([16, 14])
    g.lineWidth = 4
    g.beginPath()
    g.moveTo(x, v)
    g.lineTo(x, bottom)
    g.stroke()
    g.setLineDash([])
    g.fillStyle = '#0f172a'
    g.beginPath()
    g.arc(x, v, 30 * s, 0, Math.PI * 2)
    g.fill()
    g.fillStyle = '#4ade80'
    g.beginPath()
    g.arc(x, v, 20 * s, 0, Math.PI * 2)
    g.fill()
  }
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
    // the name at the top left; at the top centre, out of the lanes' way; or in the middle of a system with no blocks
    const align = system.title ? 'center' : 'left'
    const name = label(system.label, { size: SIZES.system, fill: color, y: Y.slab + 0.01, spacing: 0.02, align })
    const [cx, cz] = middle(rect)
    if (system.title === 'middle') scene.add(name.place(cx, cz))
    else if (system.title === 'top') scene.add(name.place(cx, rect[1] + TITLE))
    else scene.add(name.place(rect[0] + INSET, rect[1] + TITLE))
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
    // a class with tiles has its name at its top left (or at labelAt); one without has it in its middle
    const tiles = FUNCTIONS.some((fn) => fn.owner === cls.id)
    const align = !tiles || cls.align === 'center' ? 'center' : 'left'
    const at = !tiles ? middle(rect) : (cls.labelAt ?? [rect[0] + PAD, rect[1] + CLASS_LINE])
    scene.add(label(cls.id, { size: SIZES.class, weight: 700, y: Y.plate + 0.01, align }).place(...at))
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
      scene.add(name.place(cx, cz))
    }
    const frame = outline(rect, 0.3, Y.road + 0.07)
    scene.add(frame.group)
    lit.set(fn.id, frame)
  }

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
