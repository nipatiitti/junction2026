import * as THREE from 'three'
import { at, box, glow, mat, mesh } from './materials.js'
import { C } from './palette.js'
import { sign } from './sign.js'

const v2 = (x, y) => new THREE.Vector2(x, y)

function extrude(points, depth, material) {
  const geometry = new THREE.ExtrudeGeometry(new THREE.Shape(points), { depth, bevelEnabled: false })
  geometry.translate(0, 0, -depth / 2)
  return mesh(geometry, material)
}

/**
 * A low-poly hatchback about 4 units long, wheels on y = 0, front towards +x, right side towards +z.
 * Returns { root, body, wheels, seat, driver, taxiSign, spin(distance) }. `seat` is the right front seat and `driver`
 * the left one; a character at scale 0.7 fits in either. `glass` is how opaque the windows are; `snowy` puts snow on
 * the roof and the bonnet. `taxiSign` (taxis only) can be thrown off the roof.
 */
export function car({ color = C.ourRed, taxi = false, stripe = false, glass = 0.55, snowy = false } = {}) {
  const root = new THREE.Group()
  const body = new THREE.Group()
  root.add(body)
  const windows = mat(C.glassDark, { transparent: true, opacity: glass })
  body.add(
    extrude([v2(-2, 0.3), v2(2, 0.3), v2(2.05, 0.72), v2(1.7, 0.94), v2(-1.95, 0.98), v2(-2.06, 0.72)], 1.8, color),
  )
  body.add(extrude([v2(-1.8, 0.94), v2(0.8, 0.94), v2(0.15, 1.5), v2(-1.55, 1.52)], 1.62, windows))
  body.add(at(box(1.75, 0.08, 1.66, color), -0.7, 1.54, 0))
  body.add(at(box(0.12, 0.58, 1.64, color), -0.5, 1.23, 0))
  body.add(at(box(0.16, 0.2, 1.84, '#2a2d33'), 2.04, 0.42, 0))
  body.add(at(box(0.16, 0.2, 1.84, '#2a2d33'), -2.05, 0.42, 0))
  for (const z of [-0.6, 0.6]) {
    body.add(at(box(0.06, 0.14, 0.42, glow('#fff6d8')), 2.07, 0.66, z))
    body.add(at(box(0.06, 0.16, 0.34, glow('#ff2a2a')), -2.08, 0.72, z))
  }
  if (stripe) {
    body.add(at(box(1.0, 0.02, 0.32, '#ffffff'), 1.3, 0.97, 0))
    body.add(at(box(1.75, 0.02, 0.32, '#ffffff'), -0.7, 1.59, 0))
  }
  if (snowy) {
    body.add(at(box(1.7, 0.12, 1.6, C.snow), -0.7, 1.64, 0))
    body.add(at(box(1.0, 0.08, 1.5, C.snow), 1.25, 0.99, 0))
  }
  let taxiSign = null
  if (taxi) {
    taxiSign = at(new THREE.Group(), -0.7, snowy ? 1.83 : 1.71, 0)
    taxiSign.add(box(0.7, 0.26, 0.34, C.taxiYellow))
    for (const side of [-1, 1]) {
      const label = sign('TAXI', { w: 0.62, h: 0.2, bg: C.taxiYellow, fg: '#111111' })
      label.rotation.y = side < 0 ? Math.PI : 0
      taxiSign.add(at(label, 0, 0, side * 0.175))
    }
    body.add(taxiSign)
  }
  const wheels = []
  const tyre = new THREE.CylinderGeometry(0.38, 0.38, 0.3, 10).rotateX(Math.PI / 2)
  const hub = new THREE.CylinderGeometry(0.2, 0.2, 0.32, 6).rotateX(Math.PI / 2)
  for (const x of [-1.25, 1.3]) {
    for (const z of [-0.82, 0.82]) {
      const wheel = at(new THREE.Group(), x, 0.38, z)
      wheel.add(mesh(tyre, '#17181b'))
      wheel.add(mesh(hub, '#b9bec6'))
      root.add(wheel)
      wheels.push(wheel)
    }
  }
  const seat = at(new THREE.Group(), -0.35, 0, 0.4)
  const driver = at(new THREE.Group(), -0.35, 0, -0.4)
  body.add(seat, driver)
  const spin = (distance) => {
    for (const wheel of wheels) wheel.rotation.z = -distance / 0.38
  }
  return { root, body, wheels, seat, driver, taxiSign, spin }
}
