import * as THREE from 'three'
import { at, box, mat, mesh } from './materials.js'
import { C, shade } from './palette.js'

/**
 * A blocky low-poly person about 2.2 units tall, feet at y = 0, facing +z (towards a camera on +z).
 * Their right side is -x. The joints are groups that a view turns from the time:
 *   root (place and turn the person), body (pose() lifts it for jumps), torso (leans; carries arms and head),
 *   head, eyes, armL, armR, legL, legR, handL, handR (attach props), mullet (only with hair: 'mullet').
 */
export function character({
  skin = C.skin,
  shirt = C.hoodieRed,
  pants = C.denim,
  shoes = C.black,
  hair = 'short',
  hairColor = C.hair,
  hood = false,
  beanie = null,
  sunglasses = false,
  glasses = false,
  mustache = false,
  chain = false,
  tank = false,
  puffer = false,
  tired = false,
} = {}) {
  const root = new THREE.Group()
  const body = new THREE.Group()
  root.add(body)

  const legR = at(new THREE.Group(), -0.17, 0.92, 0)
  const legL = at(new THREE.Group(), 0.17, 0.92, 0)
  for (const leg of [legL, legR]) {
    leg.add(at(box(0.3, 0.8, 0.32, pants), 0, -0.4, 0))
    leg.add(at(box(0.32, 0.14, 0.42, shoes), 0, -0.85, 0.05))
    body.add(leg)
  }

  const width = puffer ? 0.88 : 0.72
  const depth = puffer ? 0.52 : 0.4
  const torso = at(new THREE.Group(), 0, 0.92, 0)
  body.add(torso)
  torso.add(at(box(width, 0.78, depth, shirt), 0, 0.39, 0))
  if (puffer) {
    for (const y of [0.22, 0.46, 0.68]) torso.add(at(box(width + 0.02, 0.04, depth + 0.02, shade(shirt, 0.7)), 0, y, 0))
  }
  if (hood) torso.add(at(box(0.62, 0.34, 0.2, shade(shirt, 0.85)), 0, 0.82, -0.27))
  if (chain) {
    const ring = mesh(new THREE.TorusGeometry(0.2, 0.035, 5, 14), C.gold)
    ring.scale.set(1, 1.25, 1)
    torso.add(at(ring, 0, 0.6, depth / 2 + 0.02))
  }

  const sleeve = tank ? skin : shirt
  const armR = at(new THREE.Group(), -(width / 2 + 0.13), 0.72, 0)
  const armL = at(new THREE.Group(), width / 2 + 0.13, 0.72, 0)
  const handR = at(new THREE.Group(), 0, -0.72, 0)
  const handL = at(new THREE.Group(), 0, -0.72, 0)
  for (const [arm, hand] of [
    [armR, handR],
    [armL, handL],
  ]) {
    arm.add(at(box(0.24, 0.6, 0.26, sleeve), 0, -0.3, 0))
    arm.add(at(box(0.22, 0.16, 0.24, skin), 0, -0.68, 0))
    arm.add(hand)
    torso.add(arm)
  }

  const head = at(new THREE.Group(), 0, 0.8, 0)
  torso.add(head)
  head.add(at(box(0.52, 0.5, 0.5, skin), 0, 0.27, 0))
  const eyes = at(new THREE.Group(), 0, 0.3, 0.255)
  for (const x of [-0.11, 0.11]) eyes.add(at(box(0.07, 0.1, 0.02, C.black, { shadow: false }), x, 0, 0))
  head.add(eyes)
  head.add(at(box(0.16, 0.03, 0.02, C.mouth, { shadow: false }), 0, 0.15, 0.255))
  if (tired)
    for (const x of [-0.11, 0.11]) head.add(at(box(0.1, 0.035, 0.02, '#8b5a7a', { shadow: false }), x, 0.225, 0.256))
  if (hair === 'short' || hair === 'mullet') {
    head.add(at(box(0.56, 0.14, 0.54, hairColor), 0, 0.56, 0))
    head.add(at(box(0.56, 0.32, 0.1, hairColor), 0, 0.4, -0.24))
  }
  let mullet = null
  if (hair === 'mullet') {
    mullet = at(new THREE.Group(), 0, 0.5, -0.27)
    mullet.add(at(box(0.5, 0.62, 0.12, hairColor), 0, -0.31, 0))
    head.add(mullet)
  }
  if (beanie) {
    head.add(at(box(0.57, 0.24, 0.55, beanie), 0, 0.6, 0))
    head.add(at(box(0.59, 0.08, 0.57, shade(beanie, 0.75)), 0, 0.5, 0))
  }
  if (mustache) head.add(at(box(0.28, 0.06, 0.04, hairColor, { shadow: false }), 0, 0.2, 0.265))
  if (sunglasses) head.add(at(box(0.46, 0.11, 0.03, '#0b0b0d', { shadow: false }), 0, 0.31, 0.265))
  if (glasses) {
    const lens = mat('#d8ecff', { transparent: true, opacity: 0.5 })
    for (const x of [-0.11, 0.11]) head.add(at(box(0.16, 0.13, 0.02, lens, { shadow: false }), x, 0.3, 0.27))
  }

  return { root, body, torso, head, eyes, armL, armR, legL, legR, handL, handR, mullet }
}

const JOINTS = ['torso', 'head', 'armL', 'armR', 'legL', 'legR']

/** Sets every joint from angles in radians, { armR: [x, y, z], ... }; joints left out go back to rest. */
export function pose(ch, angles = {}) {
  for (const joint of JOINTS) {
    const [x = 0, y = 0, z = 0] = angles[joint] ?? []
    ch[joint].rotation.set(x, y, z)
  }
  ch.body.position.y = angles.lift ?? 0
}

/** Mixes two poses: k = 0 gives a, k = 1 gives b. */
export function mix(a, b, k) {
  const out = { lift: (a.lift ?? 0) + ((b.lift ?? 0) - (a.lift ?? 0)) * k }
  for (const joint of JOINTS) {
    const va = a[joint] ?? [0, 0, 0]
    const vb = b[joint] ?? [0, 0, 0]
    out[joint] = va.map((x, i) => x + (vb[i] - x) * k)
  }
  return out
}

/** Walk-cycle angles at phase p (radians) with swing a. */
export function walk(p, a = 0.6) {
  const s = Math.sin(p)
  return {
    armL: [s * a, 0, 0],
    armR: [-s * a, 0, 0],
    legL: [-s * a, 0, 0],
    legR: [s * a, 0, 0],
    lift: Math.abs(Math.cos(p)) * 0.05,
  }
}

// Poses the scenes share. Negative x on an arm lifts it forward; z lifts it to the side.
export const POSES = {
  phone: { armR: [-1.25, 0, 0.1], armL: [-1.05, 0, -0.25], head: [0.35, 0, 0] },
  armsUp: { armR: [0, 0, -2.7], armL: [0, 0, 2.7] },
  sit: { legL: [-1.5, 0, 0], legR: [-1.5, 0, 0] },
  /** the 6-7 hands at time t: palms up, going up and down in turn */
  sixSeven: (t) => ({
    armR: [-1.45 + 0.4 * Math.sin(t * 14), 0, 0.2],
    armL: [-1.45 - 0.4 * Math.sin(t * 14), 0, -0.2],
    lift: Math.abs(Math.sin(t * 14)) * 0.05,
  }),
  /** one arm flexed up, the other hand making a heart at the chest */
  bicepHeart: { armR: [-0.2, 0, -2.1], armL: [-1.5, 0, -0.7], head: [0, 0.25, 0.1] },
}
