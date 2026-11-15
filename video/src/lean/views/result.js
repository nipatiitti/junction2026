import * as THREE from 'three'
import { ease, progress } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { ROADS, ROUTES } from '../diagram.js'
import { captions, voiceCues } from '../lines.js'
import { buildMap, THEME } from '../map.js'
import { joined, polyline, queue } from '../traffic.js'
import { MONO, SANS } from '../ui.js'

// Chapter 03, the result: the whole diagram stays behind, dimmed, its traffic still running, and six cards come up in
// front, two rows of three. The first row: the margin, the strategies tried against the one shipped, and the on-time
// share (the one joke number, with its lying subtitle). The second, as the voice says "By stealing from drivers and
// dealers…": what drivers get paid less, what dealers pay over list, and in the middle, lit, the two together as
// stakeholder value. The texts are in timeline.js. Beats (local seconds):
//   0.6 the margin · 2.0 the strategies · 4.3 the on-time share, its decimals ticking in · 7.3 the voice ·
//   8.2 the drivers · 8.9 the dealers · 9.9 the stakeholder value · the last 0.3 s fade

// the middles of the two rows: between the chapter tag and the subtitles, 48 apart, with room under the second for
// the note and a subtitle of two lines
const ROWS = [366, 754]
const CARDS = [
  { key: 'margin', at: 0.6, colour: '#4ade80', x: 380, y: ROWS[0] },
  { key: 'strategies', at: 2.0, colour: '#60a5fa', x: 960, y: ROWS[0] },
  { key: 'onTime', at: 4.3, colour: '#fbbf24', x: 1540, y: ROWS[0] },
  { key: 'drivers', at: 8.2, colour: '#f87171', x: 380, y: ROWS[1] },
  { key: 'stakeholders', at: 9.9, colour: '#22c55e', x: 960, y: ROWS[1], lit: true },
  { key: 'dealers', at: 8.9, colour: '#c084fc', x: 1540, y: ROWS[1] },
]

/** A card: its value big, and under it a label of one or two lines; `lit` glows in its colour. */
function resultCard(g, t, { at, colour, x, y, lit }, value, label, end) {
  const s = ease.outCubic(progress(t, at, at + 0.45))
  if (s <= 0) return
  const lines = [label].flat()
  g.save()
  g.globalAlpha = s * (1 - progress(t, end - 0.3, end))
  g.translate(x, y + 40 * (1 - s))
  if (lit) {
    g.shadowColor = colour
    g.shadowBlur = 48
  }
  g.fillStyle = 'rgba(15, 23, 42, 0.95)'
  g.beginPath()
  g.roundRect(-270, -170, 540, 340, 24)
  g.fill()
  g.shadowBlur = 0
  g.strokeStyle = colour
  g.lineWidth = lit ? 5 : 3
  g.stroke()
  g.fillStyle = colour
  g.fillRect(-270, -170, 540, 8)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = '#f8fafc'
  g.font = `700 ${value.length > 9 ? 70 : 92}px ${MONO}`
  g.fillText(value, 0, lines.length > 1 ? -42 : -20)
  g.fillStyle = '#94a3b8'
  lines.forEach((line, i) => {
    // a long line gets a smaller font, so it keeps 30 clear of the card's sides
    let size = 32
    g.font = `500 ${size}px ${SANS}`
    while (g.measureText(line).width > 480 && size > 22) {
      size -= 1
      g.font = `500 ${size}px ${SANS}`
    }
    g.fillText(line, 0, (lines.length > 1 ? 58 : 90) + i * 46)
  })
  g.restore()
}

export default {
  sounds(segment) {
    const whoosh = (at, gain = 0.12) => ({ at, sound: 'whoosh', length: 0.4, from: 400, to: 2400, gain })
    return [
      ...voiceCues(segment),
      whoosh(0.6, 0.15),
      { at: 0.9, sound: 'kaching', gain: 0.22 },
      whoosh(2.0),
      whoosh(4.3),
      { at: 4.5, sound: 'slot', length: 1.2, gain: 0.08 },
      whoosh(8.2),
      whoosh(8.9),
      whoosh(9.9, 0.15),
      { at: 10.2, sound: 'kaching', gain: 0.24 },
    ]
  },
  build(segment) {
    const texts = segment.texts
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(THEME.ground)
    scene.add(new THREE.HemisphereLight('#ffffff', '#334155', 1.5))
    const sun = new THREE.DirectionalLight('#ffffff', 1.1)
    sun.position.set(-40, 120, 70)
    scene.add(sun)
    const map = buildMap(scene)
    map.chart(1)
    const loop = polyline(joined(ROUTES.quote.map((id) => ROADS.find((r) => r.id === id))))
    const vehicles = []
    // one car every 0.9 s from 6 s before the segment to its end
    for (let i = 0; i < Math.ceil((segment.duration + 6) / 0.9); i++) {
      const body = car({ color: i % 3 === 1 ? '#ef4444' : '#94a3b8' })
      body.root.scale.setScalar(0.7)
      scene.add(body.root)
      vehicles.push({ start: -6 + i * 0.9, speed: 30, body })
    }
    const camera = new THREE.PerspectiveCamera(30, 16 / 10, 5, 3000)
    return {
      scene,
      camera,
      update(t) {
        const turn = THREE.MathUtils.degToRad(6 + t * 0.6)
        const tilt = THREE.MathUtils.degToRad(32)
        const distance = (160 / (2 * Math.tan(THREE.MathUtils.degToRad(15)))) * (1 - t * 0.01)
        camera.position.set(
          Math.sin(turn) * distance * Math.sin(tilt),
          distance * Math.cos(tilt),
          -20.5 + Math.cos(turn) * distance * Math.sin(tilt),
        )
        camera.up.set(-Math.sin(turn), 0, -Math.cos(turn))
        camera.lookAt(0, 0, -20.5)
        const where = queue(loop, vehicles, t)
        vehicles.forEach((v, i) => {
          const d = where[i]
          v.body.root.visible = d >= 0 && Number.isFinite(d)
          if (!v.body.root.visible) return
          const [x, z, heading] = loop.at(d)
          v.body.root.position.set(x, 0.58, z)
          v.body.root.rotation.y = -heading
          v.body.spin(d)
        })
      },
      overlay(g, t) {
        g.fillStyle = 'rgba(8, 12, 22, 0.62)'
        g.fillRect(0, 0, 1920, 1200)
        const end = segment.duration
        // the on-time share: its decimals tick in one by one
        const [whole, decimals] = texts.onTime.replace('%', '').split('.')
        const count = Math.min(decimals.length, Math.floor(progress(t, 4.5, 5.7) * (decimals.length + 1)))
        const values = { ...texts, onTime: count > 0 ? `${whole}.${decimals.slice(0, count)}%` : `${whole}%` }
        for (const card of CARDS) resultCard(g, t, card, values[card.key], texts[`${card.key}Label`], end)
        // under the second row, above the subtitles
        if (t >= 1.2) {
          g.save()
          g.globalAlpha = progress(t, 1.2, 1.6) * (1 - progress(t, end - 0.3, end))
          g.fillStyle = '#64748b'
          g.font = `500 26px ${SANS}`
          g.textAlign = 'center'
          g.fillText(texts.fine, 960, 962)
          g.restore()
        }
        captions(g, t, segment)
      },
    }
  },
}
