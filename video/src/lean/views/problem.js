import * as THREE from 'three'
import { ease, lerp, pop, progress, track } from '../../kit/anim.js'
import { car } from '../../kit/car.js'
import { character, mix, POSES, pose } from '../../kit/character.js'
import { toScreen } from '../../kit/text.js'
import { captions, voiceCues } from '../lines.js'
import { ground, label, paint, panel } from '../map.js'
import { MONO, SANS } from '../ui.js'

// Chapter 01, the problem: a dealer, ts:lean and the drivers on three panels. A price request flies in and a gig flies
// out; a price too high loses the car to the competitor; a fee too low leaves the car late; and under 90% on time the
// week is not ranked. The texts are in timeline.js. Beats (local seconds):
//   0.6–1.6 the request flies to ts:lean · 2.0–2.9 the gig flies to the drivers
//   3.9 the price tag 1.9 × list · 4.2–6.0 the competitor's car drives in and leaves with the dealer's car
//   6.2 a new car waits · 6.4 the fee tag 0.6 × typical · 6.8–8.2 the drivers shrug · 7.0–8.5 the clock · 7.8 LATE
//   8.7–9.3 the on-time gauge falls under 90% · 9.3 NOT RANKED

const W = 1920
const H = 1200
const PANELS = {
  dealer: { rect: [-20.5, -4.8, -9.5, 4.8], color: '#f59e0b' },
  lean: { rect: [-5, -4.8, 5, 4.8], color: '#ef4444' },
  drivers: { rect: [9.5, -4.8, 20.5, 4.8], color: '#34d399' },
}
const CAR_AT = [-12.9, -1.6]
const SHRUG = { armL: [0, 0, 0.75], armR: [0, 0, -0.75], head: [0, 0, 0.18], lift: 0.04 }

/** A card in the picture: a dark rounded panel with a coloured edge, a monospace title and a line under it. */
function card(g, x, y, title, line, colour, { alpha = 1, scale = 1, struck = 0 } = {}) {
  if (alpha <= 0 || scale <= 0) return
  g.save()
  g.globalAlpha = alpha
  g.translate(x, y)
  g.scale(scale, scale)
  g.font = `700 32px ${MONO}`
  const w = Math.max(g.measureText(title).width, 220) + 64
  g.fillStyle = 'rgba(15, 23, 42, 0.94)'
  g.beginPath()
  g.roundRect(-w / 2, -54, w, line ? 108 : 70, 14)
  g.fill()
  g.fillStyle = colour
  g.fillRect(-w / 2, -54, 8, line ? 108 : 70)
  g.fillStyle = '#f1f5f9'
  g.textAlign = 'left'
  g.textBaseline = 'middle'
  g.fillText(title, -w / 2 + 30, line ? -24 : -19)
  if (line) {
    g.fillStyle = '#94a3b8'
    g.font = `500 28px ${SANS}`
    g.fillText(line, -w / 2 + 30, 20)
  }
  if (struck > 0) {
    g.strokeStyle = '#ef4444'
    g.lineWidth = 6
    g.beginPath()
    g.moveTo(-w / 2 + 20, -2)
    g.lineTo(-w / 2 + 20 + (w - 40) * struck, -2)
    g.stroke()
  }
  g.restore()
}

/** A tag: bold text on a coloured pill. */
function tag(g, x, y, text, bg, scale) {
  if (scale <= 0) return
  g.save()
  g.translate(x, y)
  g.scale(scale, scale)
  g.font = `800 40px ${MONO}`
  const w = g.measureText(text).width + 48
  g.fillStyle = bg
  g.beginPath()
  g.roundRect(-w / 2, -34, w, 68, 34)
  g.fill()
  g.fillStyle = '#ffffff'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillText(text, 0, 2)
  g.restore()
}

export default {
  sounds(segment) {
    const cues = [
      ...voiceCues(segment),
      { at: 0.6, sound: 'whoosh', length: 0.6, from: 400, to: 2400, gain: 0.18 },
      { at: 1.6, sound: 'ding', gain: 0.18 },
      { at: 2.0, sound: 'whoosh', length: 0.5, from: 400, to: 2400, gain: 0.15 },
      { at: 3.9, sound: 'boom', gain: 0.25, length: 0.4 },
      { at: 4.2, sound: 'engine', length: 1.6, from: 70, to: 190, gain: 0.14 },
      { at: 4.8, sound: 'screech', length: 0.5, gain: 0.08 },
      { at: 6.4, sound: 'boom', gain: 0.2, length: 0.4 },
      { at: 9.3, sound: 'boom', gain: 0.45 },
    ]
    for (let at = 7.0; at < 8.5; at += 0.25) cues.push({ at, sound: 'tap', gain: 0.07 })
    return cues
  },

  build(segment) {
    const texts = segment.texts
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0a0f1c')
    scene.add(ground())
    scene.add(new THREE.HemisphereLight('#ffffff', '#334155', 1.5))
    const sun = new THREE.DirectionalLight('#ffffff', 1.2)
    sun.position.set(-30, 80, 60)
    scene.add(sun)
    const camera = new THREE.PerspectiveCamera(30, 16 / 10, 1, 1000)
    const screen = (x, y, z) => toScreen(new THREE.Vector3(x, y, z), camera, W, H)

    const names = { dealer: texts.dealer, lean: texts.lean, drivers: texts.drivers }
    for (const [id, { rect, color }] of Object.entries(PANELS)) {
      scene.add(panel(rect, 0.3, 0.28, paint(color), 1.0))
      const inner = [rect[0] + 0.3, rect[1] + 0.3, rect[2] - 0.3, rect[3] - 0.3]
      scene.add(
        panel(inner, 0.3, 0.3, paint(new THREE.Color(color).lerp(new THREE.Color('#0a0f1c'), 0.82).getStyle()), 0.8),
      )
      const font = id === 'lean' ? MONO : SANS
      scene.add(label(names[id], { size: 1.9, font, fill: color, y: 0.32 }).place(rect[0] + 0.8, rect[1] + 1.4))
    }

    const dealer = character({ shirt: '#6b4a32', hair: 'mullet', hairColor: '#7a5230', mustache: true, chain: true })
    dealer.root.position.set(-17.8, 0.3, 2.2)
    dealer.root.rotation.y = 0.45
    dealer.root.scale.setScalar(1.5)
    scene.add(dealer.root)
    const first = car({ color: '#ef4444' })
    first.root.position.set(CAR_AT[0], 0.3, CAR_AT[1])
    first.root.rotation.y = 0.2
    first.root.scale.setScalar(1.1)
    scene.add(first.root)
    const second = car({ color: '#2b7de9' })
    second.root.position.set(CAR_AT[0], 0.3, CAR_AT[1])
    second.root.rotation.y = 0.2
    second.root.scale.setScalar(1.1)
    scene.add(second.root)
    const rival = car({ color: '#64748b' })
    rival.root.scale.setScalar(1.1)
    scene.add(rival.root)
    const drivers = [
      character({ shirt: '#8a8f98', pants: '#5a5f68', hood: true, hair: 'none' }),
      character({ shirt: '#f4f4f4', tank: true, skin: '#d9a074', pants: '#2d2d2d', sunglasses: true }),
      character({ shirt: '#6a8caf', glasses: true, pants: '#4a4a4a' }),
    ]
    drivers.forEach((d, i) => {
      d.root.position.set(12.2 + i * 3.2, 0.3, 1.8 - (i % 2) * 1.6)
      d.root.rotation.y = -0.3
      d.root.scale.setScalar(1.5)
      scene.add(d.root)
    })

    return {
      scene,
      camera,
      update(t) {
        const eye = track(t, [
          [0, [-1.5, 30, 46]],
          [10, [1.5, 28.5, 43.5], 'linear'],
        ])
        camera.position.set(...eye)
        camera.lookAt(0, 0, -6)

        pose(dealer, t < 0.6 ? POSES.phone : mix(POSES.phone, {}, progress(t, 0.6, 1.0)))
        // the competitor drives in and leaves with the dealer's car
        const inK = ease.outCubic(progress(t, 4.2, 4.9))
        const outK = ease.inCubic(progress(t, 5.1, 6.0))
        rival.root.visible = t >= 4.2 && t < 6.1
        rival.root.position.set(lerp(-62, -15.5, inK) - 44 * outK, 0.3, 3.4)
        rival.root.rotation.y = Math.PI
        rival.spin(t * 20)
        first.root.visible = t < 6.0
        first.root.position.x = CAR_AT[0] - 46 * outK
        first.root.rotation.y = lerp(0.2, Math.PI, progress(t, 5.0, 5.3))
        second.root.visible = t >= 6.2
        second.root.scale.setScalar(1.1 * Math.max(0.01, pop(t, 6.2, 0.3)))
        drivers.forEach((d, i) => {
          const k = progress(t, 6.8 + i * 0.1, 7.1 + i * 0.1) * (1 - progress(t, 8.0, 8.4))
          pose(d, mix(POSES.phone, SHRUG, k))
        })
      },
      overlay(g, t) {
        const [lx, ly] = screen(0, 3.5, -3)
        const [dx, dy] = screen(-15, 3.5, -3)
        const [rx, ry] = screen(15, 3.5, -3)
        // the request flies from the dealer to ts:lean, the gig from ts:lean to the drivers
        const fly = ease.inOutCubic(progress(t, 0.6, 1.6))
        if (t >= 0.6 && t < 6.0) {
          const struck = progress(t, 4.8, 5.2)
          card(
            g,
            lerp(dx, lx, fly),
            lerp(dy, ly, fly) - 120 - Math.sin(Math.PI * fly) * 80,
            'price_request',
            texts.request.split(' · ')[1],
            '#60a5fa',
            {
              alpha: 1 - 0.5 * struck - progress(t, 5.6, 6.0),
              struck,
            },
          )
        }
        const gig = ease.inOutCubic(progress(t, 2.0, 2.9))
        if (t >= 2.0 && t < 6.2)
          card(
            g,
            lerp(lx, rx, gig),
            lerp(ly, ry, gig) - 120 - Math.sin(Math.PI * gig) * 80,
            'gig',
            'fee ?',
            '#34d399',
            {
              alpha: 1 - progress(t, 5.8, 6.2),
            },
          )
        // too high: the price tag, and the competitor's name over its car
        if (t >= 3.9 && t < 6.2)
          tag(g, lx, ly - 260, texts.high, '#dc2626', pop(t, 3.9, 0.3) * (1 - progress(t, 5.9, 6.2)))
        if (t >= 4.4 && t < 6.0) {
          const [cx, cy] = screen(
            lerp(-62, -15.5, ease.outCubic(progress(t, 4.2, 4.9))) - 44 * ease.inCubic(progress(t, 5.1, 6.0)),
            3.2,
            3.4,
          )
          card(g, cx, cy - 50, texts.competitor, null, '#64748b', { alpha: progress(t, 4.4, 4.6) })
        }
        // too little: the fee tag, the clock, LATE
        if (t >= 6.4) tag(g, rx, ry - 230, texts.low, '#ea580c', pop(t, 6.4, 0.3) * (1 - progress(t, 9.6, 10)))
        if (t >= 7.0 && t < 9.8) {
          const [cx, cy] = screen(-12.5, 4.5, -1)
          const a = progress(t, 7.0, 7.2) * (1 - progress(t, 9.5, 9.8))
          g.save()
          g.globalAlpha = a
          g.translate(cx + 150, cy - 150)
          g.fillStyle = 'rgba(15, 23, 42, 0.94)'
          g.beginPath()
          g.arc(0, 0, 56, 0, Math.PI * 2)
          g.fill()
          g.strokeStyle = '#e2e8f0'
          g.lineWidth = 6
          g.stroke()
          g.lineCap = 'round'
          g.beginPath()
          g.moveTo(0, 0)
          const angle = (t - 7.0) * 9
          g.lineTo(Math.sin(angle) * 40, -Math.cos(angle) * 40)
          g.stroke()
          g.lineWidth = 8
          g.beginPath()
          g.moveTo(0, 0)
          g.lineTo(Math.sin(angle / 12) * 26, -Math.cos(angle / 12) * 26)
          g.stroke()
          g.restore()
        }
        if (t >= 7.8) {
          const [cx, cy] = screen(CAR_AT[0], 3, CAR_AT[1])
          tag(g, cx + 40, cy - 70, texts.late, '#dc2626', pop(t, 7.8, 0.3) * (1 - progress(t, 9.6, 10)))
        }
        // the on-time gauge falls under 90%, and the stamp
        if (t >= 8.6) {
          const a = progress(t, 8.6, 8.8)
          const share = lerp(0.96, 0.84, ease.inOutCubic(progress(t, 8.7, 9.3)))
          const angle = (s) => Math.PI + ((s - 0.8) / 0.2) * Math.PI
          g.save()
          g.globalAlpha = a
          g.translate(960, 300)
          g.fillStyle = 'rgba(15, 23, 42, 0.94)'
          g.beginPath()
          g.roundRect(-230, -150, 460, 220, 18)
          g.fill()
          g.lineWidth = 22
          g.strokeStyle = '#334155'
          g.beginPath()
          g.arc(0, 30, 140, Math.PI, 2 * Math.PI)
          g.stroke()
          g.strokeStyle = '#16a34a'
          g.beginPath()
          g.arc(0, 30, 140, angle(0.9), 2 * Math.PI)
          g.stroke()
          g.strokeStyle = '#dc2626'
          g.beginPath()
          g.arc(0, 30, 140, Math.PI, angle(0.9))
          g.stroke()
          g.strokeStyle = '#f8fafc'
          g.lineWidth = 6
          g.lineCap = 'round'
          g.beginPath()
          g.moveTo(0, 30)
          g.lineTo(Math.cos(angle(share)) * 120, 30 + Math.sin(angle(share)) * 120)
          g.stroke()
          g.fillStyle = '#f8fafc'
          g.font = `700 40px ${MONO}`
          g.textAlign = 'center'
          g.textBaseline = 'middle'
          g.fillText(`${Math.round(share * 100)}%`, 0, 2)
          g.fillStyle = '#94a3b8'
          g.font = `500 24px ${SANS}`
          g.fillText('on time · 90% to be ranked', 0, 52)
          g.restore()
          const s = pop(t, 9.3, 0.25)
          if (s > 0) {
            g.save()
            g.translate(960, 300)
            g.rotate(-0.12)
            g.scale(s, s)
            g.strokeStyle = '#dc2626'
            g.lineWidth = 8
            g.strokeRect(-210, -46, 420, 92)
            g.fillStyle = '#dc2626'
            g.font = `800 60px ${SANS}`
            g.textAlign = 'center'
            g.textBaseline = 'middle'
            g.fillText(texts.stamp, 0, 2)
            g.restore()
          }
        }
        captions(g, t, segment)
      },
    }
  },
}
