import * as THREE from 'three'
import { ease, progress } from '../../kit/anim.js'
import { ground } from '../map.js'
import { ACCENT, MONO, SANS } from '../ui.js'

// The title card after the cold open: the strategy's name, what the video is about and who made it, over the dark
// grid of the diagram while the camera drifts. The texts are in timeline.js. Beats (local seconds):
//   0–0.5 the name rises in · 0.2–0.6 the red rule grows · 0.45 the line · 0.7 the team · 2.7–3.0 all fade out

export default {
  sounds() {
    return [
      { at: 0, sound: 'whoosh', length: 0.6, from: 300, to: 2000, gain: 0.25 },
      { at: 0.15, sound: 'ding', gain: 0.2 },
      { at: 2.2, sound: 'riser', length: 0.8, gain: 0.1 },
    ]
  },
  build(segment) {
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0a0f1c')
    scene.add(ground())
    const camera = new THREE.PerspectiveCamera(30, 16 / 10, 1, 2000)
    const { title, line, team } = segment.texts
    return {
      scene,
      camera,
      update(t) {
        camera.position.set(-20 + t * 6, 160, 140 - t * 4)
        camera.up.set(0, 1, 0)
        camera.lookAt(t * 6, 0, 0)
      },
      overlay(g, t) {
        const out = 1 - progress(t, 2.7, 3.0)
        const rise = (at) => ease.outCubic(progress(t, at, at + 0.5))
        g.save()
        g.fillStyle = 'rgba(10, 15, 28, 0.55)'
        g.fillRect(0, 0, 1920, 1200)
        g.textBaseline = 'middle'
        g.textAlign = 'left'
        const x = 220
        g.globalAlpha = out * rise(0)
        g.fillStyle = '#f8fafc'
        g.font = `700 168px ${MONO}`
        g.fillText(title, x, 520 + 30 * (1 - rise(0)))
        g.globalAlpha = out
        g.fillStyle = ACCENT
        g.fillRect(x, 640, 520 * ease.outCubic(progress(t, 0.2, 0.6)), 10)
        g.globalAlpha = out * rise(0.45)
        g.fillStyle = '#cbd5e1'
        g.font = `500 48px ${SANS}`
        g.fillText(line, x, 730 + 16 * (1 - rise(0.45)))
        g.globalAlpha = out * rise(0.7)
        g.fillStyle = '#94a3b8'
        g.font = `600 36px ${SANS}`
        g.fillText(team, x, 810 + 16 * (1 - rise(0.7)))
        g.restore()
      },
    }
  },
}
