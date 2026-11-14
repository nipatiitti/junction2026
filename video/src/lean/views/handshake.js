import * as THREE from 'three'
import { progress, track } from '../../kit/anim.js'
import { at, box } from '../../kit/materials.js'
import { liveTexture } from '../../kit/sign.js'
import { developer, hall, lanyard } from '../sets.js'
import { lowerThird } from '../ui.js'

// Joke 3 and the end: the developer and a teammate shake hands in front of the whiteboard with the same diagram drawn
// by hand, smiling at the camera in stock-photo light, for far too long. The end title comes up as a lower third.
// The texts are in timeline.js. Beats (local seconds):
//   0–4.5 the handshake, a slow push-in, the smiles never move · 1.0 the end title · 2.6 the teammate blinks once

/** The diagram on the whiteboard, drawn by hand in marker. */
function whiteboard(g, _state, w, h) {
  g.fillStyle = '#f8fafc'
  g.fillRect(0, 0, w, h)
  g.lineWidth = 6
  g.lineJoin = 'round'
  g.font = `700 34px "Marker Felt", "Comic Sans MS", "Chalkboard SE", sans-serif`
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const blockAt = (x, y, bw, bh, text, colour) => {
    g.strokeStyle = colour
    g.beginPath()
    g.moveTo(x + 4, y + 2)
    g.lineTo(x + bw - 3, y - 2)
    g.lineTo(x + bw + 2, y + bh + 3)
    g.lineTo(x - 2, y + bh - 1)
    g.closePath()
    g.stroke()
    g.fillStyle = colour
    g.fillText(text, x + bw / 2, y + bh / 2)
  }
  const arrow = (x1, y1, x2, y2) => {
    g.strokeStyle = '#334155'
    g.beginPath()
    g.moveTo(x1, y1)
    g.lineTo(x2, y2)
    g.stroke()
    const a = Math.atan2(y2 - y1, x2 - x1)
    g.beginPath()
    g.moveTo(x2, y2)
    g.lineTo(x2 - 18 * Math.cos(a - 0.4), y2 - 18 * Math.sin(a - 0.4))
    g.moveTo(x2, y2)
    g.lineTo(x2 - 18 * Math.cos(a + 0.4), y2 - 18 * Math.sin(a + 0.4))
    g.stroke()
  }
  blockAt(330, 40, 360, 70, 'SPREAD WORLD', '#d97706')
  blockAt(370, 160, 280, 60, 'KIT · HARNESS', '#2563eb')
  blockAt(300, 280, 420, 200, '', '#dc2626')
  g.fillStyle = '#dc2626'
  g.fillText('TS:LEAN', 510, 310)
  g.font = `700 26px "Marker Felt", "Comic Sans MS", sans-serif`
  g.fillStyle = '#16a34a'
  g.fillText('bestPrice()', 510, 380)
  g.fillStyle = '#334155'
  g.fillText('fees · chains', 510, 430)
  blockAt(40, 330, 200, 70, 'OPS', '#059669')
  blockAt(780, 330, 200, 70, 'WEEKS', '#7c3aed')
  arrow(500, 110, 500, 160)
  arrow(510, 220, 510, 280)
  arrow(300, 365, 240, 365)
  arrow(780, 365, 720, 365)
  g.strokeStyle = '#16a34a'
  g.beginPath()
  g.moveTo(620, 470)
  g.quadraticCurveTo(820, 520, 900, 430)
  g.stroke()
  g.fillStyle = '#16a34a'
  g.fillText('+€24,451 / week ↑', 830, 520)
}

export default {
  sounds() {
    // elevator music: a music box, slow and polite
    const melody = [72, 76, 79, 76, 74, 77, 81, 77, 72, 76, 79, 84, 83, 79, 76, 74, 72]
    return melody.map((note, i) => ({ at: 0.1 + i * 0.26, sound: 'musicBox', note, gain: 0.16 }))
  },
  build(segment) {
    const scene = new THREE.Scene()
    hall(scene, { day: true, hour: 'HOUR 47', banner: 'DEMO TIME' })
    const board = liveTexture(1024, 560, whiteboard)
    board.set({})
    scene.add(at(box(4.4, 2.5, 0.1, '#9aa3ad'), 0, 2.15, -3.2))
    const surface = new THREE.Mesh(
      new THREE.PlaneGeometry(4.2, 2.3),
      new THREE.MeshBasicMaterial({ map: board.texture }),
    )
    scene.add(at(surface, 0, 2.15, -3.14))
    for (const x of [-1.9, 1.9]) scene.add(at(box(0.08, 1.0, 0.08, '#6b7280'), x, 0.5, -3.2))

    const dev = developer()
    const mate = developer({ shirt: '#2563eb', hair: 'short', hood: false })
    for (const [person, x, turn] of [
      [dev, -0.62, 0.45],
      [mate, 0.62, -0.45],
    ]) {
      person.root.position.set(x, 0, -1.2)
      person.root.rotation.y = turn
      lanyard(person, 'BLIB BLIB')
      scene.add(person.root)
    }
    // the handshake: right hands meet between them
    dev.armR.rotation.set(-1.05, 0.55, 0)
    mate.armR.rotation.set(-1.05, -0.55, 0)
    dev.armL.rotation.set(0, 0, 0.12)
    mate.armL.rotation.set(0, 0, -0.12)
    const camera = new THREE.PerspectiveCamera(36, 16 / 10, 0.05, 100)
    return {
      scene,
      camera,
      update(t) {
        const shake = Math.sin(t * 9) * 0.04 * (1 - progress(t, 0.6, 1.0))
        dev.armR.rotation.x = -1.05 + shake
        mate.armR.rotation.x = -1.05 + shake
        mate.eyes.scale.y = t > 2.6 && t < 2.72 ? 0.1 : 1
        const eye = track(t, [
          [0, [0, 1.75, 4.6]],
          [4.5, [0, 1.72, 3.5], 'linear'],
        ])
        camera.position.set(...eye)
        camera.lookAt(0, 1.55, -1.6)
      },
      overlay(g, t) {
        // stock-photo light: everything a little too bright and soft
        g.fillStyle = 'rgba(255, 255, 255, 0.14)'
        g.fillRect(0, 0, 1920, 1200)
        lowerThird(g, t, segment.texts.title, segment.texts.team, { t0: 1.0 })
      },
    }
  },
}
