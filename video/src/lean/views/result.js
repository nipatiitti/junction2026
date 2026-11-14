import * as THREE from 'three'
import { ease, progress } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { ROADS, ROUTES } from '../diagram.js'
import { captions, voiceCues } from '../lines.js'
import { buildMap, THEME } from '../map.js'
import { joined, polyline, queue } from '../traffic.js'
import { MONO, SANS } from '../ui.js'

// Chapter 03, the result: the whole diagram stays behind, dimmed, its traffic still running, and three cards come up
// in front: the margin, the strategies tried against the one shipped, and the on-time share (the one joke number, with
// its lying subtitle). The texts are in timeline.js. Beats (local seconds):
//   0.6 the margin card · 2.0 the strategies card · 3.8 the on-time card, its decimals ticking in · 6.7 fade

const CARDS = [
  { key: 'margin', at: 0.6, colour: '#4ade80', x: 380 },
  { key: 'strategies', at: 2.0, colour: '#60a5fa', x: 960 },
  { key: 'onTime', at: 3.8, colour: '#fbbf24', x: 1540 },
]

function resultCard(g, t, { at, colour, x }, value, label) {
  const s = ease.outCubic(progress(t, at, at + 0.45))
  if (s <= 0) return
  g.save()
  g.globalAlpha = s * (1 - progress(t, 6.7, 7.0))
  g.translate(x, 470 + 40 * (1 - s))
  g.fillStyle = 'rgba(15, 23, 42, 0.95)'
  g.beginPath()
  g.roundRect(-270, -170, 540, 340, 24)
  g.fill()
  g.strokeStyle = colour
  g.lineWidth = 3
  g.stroke()
  g.fillStyle = colour
  g.fillRect(-270, -170, 540, 8)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = '#f8fafc'
  g.font = `700 ${value.length > 9 ? 70 : 92}px ${MONO}`
  g.fillText(value, 0, -20)
  g.fillStyle = '#94a3b8'
  g.font = `500 32px ${SANS}`
  g.fillText(label, 0, 90)
  g.restore()
}

export default {
  sounds(segment) {
    return [
      ...voiceCues(segment),
      { at: 0.6, sound: 'whoosh', length: 0.4, from: 400, to: 2400, gain: 0.15 },
      { at: 0.9, sound: 'kaching', gain: 0.22 },
      { at: 2.0, sound: 'whoosh', length: 0.4, from: 400, to: 2400, gain: 0.12 },
      { at: 3.8, sound: 'whoosh', length: 0.4, from: 400, to: 2400, gain: 0.12 },
      { at: 3.9, sound: 'slot', length: 0.9, gain: 0.08 },
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
    for (let i = 0; i < 14; i++) {
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
        resultCard(g, t, CARDS[0], texts.margin, texts.marginLabel)
        resultCard(g, t, CARDS[1], texts.strategies, texts.strategiesLabel)
        // the on-time share: its decimals tick in one by one
        const [whole, decimals] = texts.onTime.replace('%', '').split('.')
        const count = Math.min(decimals.length, Math.floor(progress(t, 4.0, 5.2) * (decimals.length + 1)))
        const shown = count > 0 ? `${whole}.${decimals.slice(0, count)}%` : `${whole}%`
        resultCard(g, t, CARDS[2], shown, texts.onTimeLabel)
        if (t >= 1.2) {
          g.save()
          g.globalAlpha = progress(t, 1.2, 1.6) * (1 - progress(t, 6.7, 7.0))
          g.fillStyle = '#64748b'
          g.font = `500 26px ${SANS}`
          g.textAlign = 'center'
          g.fillText(texts.fine, 960, 712)
          g.restore()
        }
        captions(g, t, segment)
      },
    }
  },
}
