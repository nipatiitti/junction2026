import * as THREE from 'three'
import { pop, progress, track } from '../../kit/anim.js'
import { burst, vignette } from '../../kit/fx.js'
import { at, mat } from '../../kit/materials.js'
import { rng } from '../../kit/rng.js'
import { captions, voiceCues } from '../lines.js'
import { developer, hall, laptopDesk } from '../sets.js'
import { MONO, SANS } from '../ui.js'

// Joke 2, before strategy 2: hour 2 of the hackathon, the first strategy quotes the list price. "This will definitely
// work." A hard cut to the laptop's webcam: the developer's face in the dark, frozen, while the narrator says "It did
// not." Back at the desk the screen shows the week's loss and the laptop smokes. The texts are in timeline.js. Beats
// (local seconds):
//   0–1.4 the developer cracks the knuckles and slams Enter at 1.4 · 1.95–3.4 the webcam, dark red, the narrator ·
//   3.4–4.5 the loss in red, smoke, the head drops

const NARRATOR = [1.95, 3.4]
const LOSS = '−€72,456'

function screenPainter(text) {
  return (g, { lost, bump }, w, h) => {
    g.fillStyle = lost ? '#1a0b0f' : '#0b1220'
    g.fillRect(0, 0, w, h)
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    if (!lost) {
      g.fillStyle = '#e2e8f0'
      g.font = `700 44px ${MONO}`
      text.split('\n').forEach((line, i) => {
        g.fillText(line, w / 2, h * 0.38 + i * 64)
      })
      g.fillStyle = '#4ade80'
      g.fillRect(w / 2 - 90, h * 0.78, 180, 8)
      return
    }
    g.save()
    g.translate(w / 2, h * 0.48)
    g.scale(bump, bump)
    g.fillStyle = '#ef4444'
    g.font = `800 112px ${SANS}`
    g.fillText(LOSS, 0, 0)
    g.restore()
    g.fillStyle = '#fca5a5'
    g.font = `600 34px ${SANS}`
    g.fillText('margin, one week', w / 2, h * 0.78)
  }
}

export default {
  sounds(segment) {
    return [
      ...voiceCues(segment),
      { at: 0.5, sound: 'tap', gain: 0.12 },
      { at: 0.75, sound: 'tap', gain: 0.12 },
      { at: 1.4, sound: 'tap', gain: 0.25 },
      { at: NARRATOR[0], sound: 'boom', gain: 0.35, length: 0.6 },
      { at: 3.4, sound: 'slide', length: 0.8, from: 900, to: 200, gain: 0.18 },
      { at: 3.45, sound: 'boom', gain: 0.3, length: 0.5 },
    ]
  },
  build(segment) {
    const scene = new THREE.Scene()
    hall(scene, { day: true, hour: segment.texts.hour })
    const desk = laptopDesk(screenPainter(segment.texts.screen))
    scene.add(desk.group)
    const dev = developer({ sunglasses: true })
    dev.root.rotation.y = Math.PI
    scene.add(at(dev.root, 0, -0.32, 1.25))
    const smoke = burst(rng(7), {
      count: 90,
      origin: (_when, r) => [r.range(-0.35, 0.35), 1.82, r.range(-0.55, -0.35)],
      start: 3.4,
      spread: 0.8,
      speed: [0.1, 0.5],
      up: [0.5, 1.1],
      gravity: 0.05, // smoke barely falls; burst() needs a gravity above zero
      floor: -10,
      geometry: new THREE.BoxGeometry(0.16, 0.16, 0.16),
      material: mat('#9ca3af'),
      size: [0.8, 2.2],
    })
    scene.add(smoke.object)
    const camera = new THREE.PerspectiveCamera(38, 16 / 10, 0.05, 100)
    return {
      scene,
      camera,
      update(t) {
        const lost = t >= NARRATOR[1]
        desk.screen.set({ lost, bump: lost ? Math.round(pop(t, NARRATOR[1], 0.3) * 100) / 100 : 1 })
        const crack = Math.sin(t * 16) * 0.08 * (1 - progress(t, 1.0, 1.2))
        const press = t >= 1.3 && t < 1.6 ? -0.25 : 0
        dev.armL.rotation.set(-1.2 + crack + press, 0, -0.25)
        dev.armR.rotation.set(-1.2 - crack + press, 0, 0.25)
        dev.head.rotation.set(lost ? 0.45 * progress(t, 3.5, 3.9) : 0.1, 0, 0)
        smoke.update(t)
        if (t >= NARRATOR[0] && t < NARRATOR[1]) {
          // the webcam: up from the keyboard at the face, pushing in slowly
          const k = progress(t, NARRATOR[0], NARRATOR[1])
          camera.fov = 58
          camera.position.set(0.1, 1.8, 0.05 + 0.25 * k)
          camera.updateProjectionMatrix()
          camera.lookAt(0, 1.68, 1.1)
          return
        }
        camera.fov = 38
        camera.updateProjectionMatrix()
        const eye = track(t, [
          [0, [2.4, 2.5, 3.9]],
          [1.8, [1.9, 2.3, 3.3], 'outQuad'],
          [3.4, [1.7, 2.1, 2.5]],
          [4.5, [1.5, 2.0, 2.2], 'outQuad'],
        ])
        camera.position.set(...eye)
        camera.lookAt(0, 1.45, -0.3)
      },
      overlay(g, t) {
        if (t >= NARRATOR[0] && t < NARRATOR[1]) {
          // the webcam in the dark: a deep red cast, heavy edges, a small REC light
          g.fillStyle = 'rgba(40, 4, 8, 0.58)'
          g.fillRect(0, 0, 1920, 1200)
          vignette(g, 0.9)
          if (Math.floor(t * 2) % 2 === 0) {
            g.fillStyle = '#ef4444'
            g.beginPath()
            g.arc(96, 96, 14, 0, Math.PI * 2)
            g.fill()
          }
          g.fillStyle = '#f8fafc'
          g.font = `700 28px ${MONO}`
          g.textAlign = 'left'
          g.textBaseline = 'middle'
          g.fillText('REC', 122, 97)
        }
        captions(g, t, segment)
      },
    }
  },
}
