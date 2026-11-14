import * as THREE from 'three'
import { character } from '../kit/character.js'
import { at, box, glow, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { liveTexture, sign } from '../kit/sign.js'
import { lights } from '../kit/world.js'

// Sets and cast that several views of the ts:lean video share, in the look of the joke video's scene 2.

/** The hackathon hall: floor, walls, LED strips, the HOUR sign and the lights. `day` makes it brighter. */
export function hall(scene, { day = false, hour = 'HOUR 31', banner = 'HACK 2026' } = {}) {
  const background = day ? '#2b2645' : '#14112a'
  scene.background = new THREE.Color(background)
  scene.fog = new THREE.Fog(background, 18, 55)
  lights(scene, {
    skyColor: day ? '#e4e0ff' : '#8a7cff',
    groundColor: '#2a2240',
    fill: day ? 2.0 : 1.3,
    sun: '#e9e2ff',
    sunIntensity: day ? 2.0 : 1.4,
    from: [4, 12, 10],
    area: 14,
  })
  scene.add(
    at(new THREE.PointLight('#ff3ea5', 80, 20), -6, 4.5, -2),
    at(new THREE.PointLight('#2ff3ff', 80, 20), 6, 4.5, -2),
  )
  scene.add(at(box(40, 0.2, 40, '#33304a', { shadow: false }), 0, -0.1, 2))
  scene.add(at(box(17.8, 9, 0.4, '#1d1a30'), 0, 4.5, -7))
  for (const side of [-1, 1]) scene.add(at(box(0.4, 9, 20, '#1d1a30'), side * 8.9, 4.5, 2.8))
  const led = new THREE.MeshBasicMaterial({ color: '#ff3ea5', toneMapped: false })
  scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(17, 0.14, 0.1), led), 0, 6, -6.75))
  for (const side of [-1, 1])
    scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.14, 19), led), side * 8.65, 6, 2.8))
  scene.add(at(sign(hour, { w: 4.4, h: 1.2, bg: '#120a1e', fg: '#ff3ea5', neon: true }), -3.8, 3.3, -6.78))
  scene.add(at(sign(banner, { w: 4.4, h: 1.2, bg: '#2b1d5c', fg: '#ffffff' }), 3.8, 3.3, -6.78))
}

/**
 * A table with a laptop whose screen `paint(g, state, w, h)` draws (640 × 420). Returns { group, screen, lid,
 * enterKey, top }: set the screen's state with screen.set(state); `top` is the height of the table top.
 */
export function laptopDesk(paint) {
  const group = new THREE.Group()
  group.add(at(box(3.4, 0.1, 1.5, '#d9d4c7'), 0, 1.0, -0.2))
  for (const x of [-1.55, 1.55]) for (const z of [-0.85, 0.45]) group.add(at(box(0.08, 1.0, 0.08, C.metal), x, 0.5, z))
  group.add(at(mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.24, 8), '#1f8fff'), -0.62, 1.17, 0.3))
  group.add(at(box(0.7, 0.07, 0.7, '#e3c48d'), -1.0, 1.09, -0.3))
  const laptop = at(new THREE.Group(), 0, 1.05, -0.15)
  laptop.add(at(box(0.95, 0.05, 0.65, '#c3c7cf'), 0, 0.025, 0))
  const enterKey = at(box(0.12, 0.006, 0.08, glow('#3dff7a'), { shadow: false }), 0.28, 0.053, 0.12)
  laptop.add(enterKey)
  const lid = at(new THREE.Group(), 0, 0.05, -0.3)
  lid.rotation.x = -0.22
  lid.add(at(box(0.95, 0.64, 0.04, '#c3c7cf'), 0, 0.32, 0))
  const screen = liveTexture(640, 420, paint)
  lid.add(
    at(
      new THREE.Mesh(
        new THREE.PlaneGeometry(0.86, 0.56),
        new THREE.MeshBasicMaterial({ map: screen.texture, toneMapped: false }),
      ),
      0,
      0.32,
      0.021,
    ),
  )
  laptop.add(lid)
  group.add(laptop)
  return { group, screen, lid, enterKey, top: 1.05 }
}

/** The developer of the joke video: the red hoodie. */
export const developer = (options = {}) => character({ shirt: C.hoodieRed, hood: true, ...options })

/** A lanyard with a badge on a character's chest. */
export function lanyard(person, text) {
  const badge = at(sign(text, { w: 0.34, h: 0.2, bg: '#ffffff', fg: '#e8262b' }), 0, 0.4, 0.215)
  person.torso.add(badge)
  person.torso.add(at(box(0.03, 0.34, 0.02, '#e8262b', { shadow: false }), -0.12, 0.62, 0.205))
  person.torso.add(at(box(0.03, 0.34, 0.02, '#e8262b', { shadow: false }), 0.12, 0.62, 0.205))
  return badge
}
