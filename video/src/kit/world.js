import * as THREE from 'three'
import { at, box, glow, mat, mesh } from './materials.js'
import { C, shade } from './palette.js'

// The world kit: sky, light, ground and props that every scene reuses.

const dummy = new THREE.Object3D()

/** Moves each vertex in or out by an amount fixed by its position, so corners shared by faces stay joined. */
export function jitter(geometry, amount, seed = 1) {
  const p = geometry.attributes.position
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i)
    const y = p.getY(i)
    const z = p.getZ(i)
    const s = Math.sin(
      Math.round(x * 1000) * 12.9898 + Math.round(y * 1000) * 78.233 + Math.round(z * 1000) * 37.719 + seed,
    )
    const n = s * 43758.5453
    const k = 1 + (n - Math.floor(n) - 0.5) * amount
    p.setXYZ(i, x * k, y * k, z * k)
  }
  geometry.computeVertexNormals()
  return geometry
}

/** A gradient sky on a big inside-out sphere. Returns the sphere. */
export function sky(scene, top, bottom, { radius = 400 } = {}) {
  const geometry = new THREE.SphereGeometry(radius, 32, 16)
  const low = new THREE.Color(bottom)
  const high = new THREE.Color(top)
  const c = new THREE.Color()
  const p = geometry.attributes.position
  const colors = new Float32Array(p.count * 3)
  for (let i = 0; i < p.count; i++) {
    const k = THREE.MathUtils.clamp((p.getY(i) / radius) * 1.6, 0, 1)
    c.copy(low).lerp(high, Math.sqrt(k))
    colors.set([c.r, c.g, c.b], i * 3)
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const material = new THREE.MeshBasicMaterial({
    vertexColors: true,
    side: THREE.BackSide,
    fog: false,
    depthWrite: false,
    toneMapped: false,
  })
  const dome = new THREE.Mesh(geometry, material)
  dome.renderOrder = -1
  scene.add(dome)
  return dome
}

/** Stars as screen-sized dots on a sphere. */
export function stars(rand, { count = 1400, radius = 320, size = 2.6 } = {}) {
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const u = rand() * 2 - 1
    const a = rand() * Math.PI * 2
    const r = Math.sqrt(1 - u * u)
    positions.set([Math.cos(a) * r * radius, u * radius, Math.sin(a) * r * radius], i * 3)
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ color: '#ffffff', size, sizeAttenuation: false, fog: false }),
  )
}

/** A hemisphere fill and a sun that casts shadows over `area` around `target`. */
export function lights(
  scene,
  {
    sun = '#fff1d6',
    sunIntensity = 2.4,
    skyColor = '#cfe6ff',
    groundColor = '#8a7f74',
    fill = 1.2,
    from = [12, 18, 10],
    area = 25,
    target = [0, 0, 0],
  } = {},
) {
  scene.add(new THREE.HemisphereLight(skyColor, groundColor, fill))
  const light = new THREE.DirectionalLight(sun, sunIntensity)
  light.position.set(target[0] + from[0], target[1] + from[1], target[2] + from[2])
  light.target.position.set(...target)
  light.castShadow = true
  light.shadow.mapSize.set(2048, 2048)
  const cam = light.shadow.camera
  cam.left = -area
  cam.right = area
  cam.top = area
  cam.bottom = -area
  cam.near = 0.5
  cam.far = 160
  light.shadow.bias = -0.0005
  light.shadow.normalBias = 0.03
  scene.add(light, light.target)
  return light
}

/** Faceted snowy ground with small bumps; no bumps within `flat` of the middle. */
export function snowGround(rand, { size = 240, segments = 70, color = C.snow, bump = 0.25, flat = 0 } = {}) {
  const geometry = new THREE.PlaneGeometry(size, size, segments, segments)
  geometry.rotateX(-Math.PI / 2)
  const p = geometry.attributes.position
  for (let i = 0; i < p.count; i++) {
    const far = Math.hypot(p.getX(i), p.getZ(i)) > flat
    p.setY(i, far ? rand() * bump : 0)
  }
  geometry.computeVertexNormals()
  return mesh(geometry, color, { shadow: false })
}

/** A pine with snow on its tiers. */
export function pine(rand, { height = 7 } = {}) {
  const tree = new THREE.Group()
  tree.add(at(mesh(new THREE.CylinderGeometry(0.18, 0.25, height * 0.25, 6), C.trunk), 0, height * 0.125, 0))
  for (let i = 0; i < 3; i++) {
    const r = (1 - i / 3) * height * 0.3 + 0.4
    const h = height * 0.38
    const y = height * 0.2 + i * height * 0.22
    const cone = at(mesh(new THREE.ConeGeometry(r, h, 7), i % 2 ? C.pine : C.pineDark), 0, y + h / 2, 0)
    cone.rotation.y = rand() * Math.PI
    tree.add(cone)
    tree.add(at(mesh(new THREE.ConeGeometry(r * 0.55, h * 0.45, 7), C.snow), 0, y + h * 0.78, 0))
  }
  return tree
}

/** A lumpy pile of snow w wide, h high and d deep, half sunk in the ground. */
export function snowbank(rand, { w = 3, h = 1, d = 2 } = {}) {
  const bank = mesh(jitter(new THREE.IcosahedronGeometry(1, 1), 0.35, rand() * 100), C.snow)
  bank.scale.set(w / 2, h, d / 2)
  return bank
}

/** A block of flats with a roof edge and windows on every side; `lit` is the share of lit windows. */
export function building(rand, { w = 8, h = 10, d = 8, color = C.wall, lit = 0, windowColor = C.glassDark } = {}) {
  const block = new THREE.Group()
  block.add(at(box(w, h, d, color), 0, h / 2, 0))
  block.add(at(box(w + 0.3, 0.3, d + 0.3, shade(color, 0.75)), 0, h + 0.15, 0))
  const rows = Math.max(1, Math.floor((h - 1.5) / 2.6))
  const spots = []
  const side = (count, span, place) => {
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < count; c++) spots.push(place(-span / 2 + (c + 0.5) * (span / count), 1.8 + r * 2.6))
    }
  }
  const across = Math.max(1, Math.floor(w / 2.4))
  const deep = Math.max(1, Math.floor(d / 2.4))
  side(across, w, (x, y) => [x, y, d / 2 + 0.03, 0])
  side(across, w, (x, y) => [x, y, -d / 2 - 0.03, Math.PI])
  side(deep, d, (z, y) => [w / 2 + 0.03, y, z, Math.PI / 2])
  side(deep, d, (z, y) => [-w / 2 - 0.03, y, z, -Math.PI / 2])
  const on = []
  const off = []
  for (const spot of spots) (rand() < lit ? on : off).push(spot)
  const pane = new THREE.BoxGeometry(1.1, 1.4, 0.06)
  for (const [list, material] of [
    [on, glow('#ffd37a')],
    [off, mat(windowColor)],
  ]) {
    if (list.length === 0) continue
    const windows = new THREE.InstancedMesh(pane, material, list.length)
    list.forEach(([x, y, z, turn], i) => {
      dummy.position.set(x, y, z)
      dummy.rotation.set(0, turn, 0)
      dummy.scale.set(1, 1, 1)
      dummy.updateMatrix()
      windows.setMatrixAt(i, dummy.matrix)
    })
    block.add(windows)
  }
  return block
}

/** A pole standing on y = 0. */
export function pole(height = 5, color = C.metal) {
  const group = new THREE.Group()
  group.add(at(mesh(new THREE.CylinderGeometry(0.09, 0.11, height, 6), color), 0, height / 2, 0))
  return group
}

/** A street lamp; a lit one glows. */
export function lamp({ height = 5.5, lit = true } = {}) {
  const group = pole(height)
  group.add(at(box(1.0, 0.1, 0.12, C.metal), 0.45, height, 0))
  group.add(at(box(0.45, 0.16, 0.32, lit ? glow('#ffe2a0') : C.metal), 0.85, height - 0.1, 0))
  return group
}

/** A sagging line of pennants from a to b; call .update(t) to make them flutter. */
export function bunting(a, b, { count = 16, sag = 0.8, colors = ['#e8262b', '#f5c518', '#2b7de9', '#ffffff'] } = {}) {
  const group = new THREE.Group()
  const start = new THREE.Vector3(...a)
  const end = new THREE.Vector3(...b)
  const turn = -Math.atan2(end.z - start.z, end.x - start.x)
  const triangle = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-0.22, 0, 0),
    new THREE.Vector3(0.22, 0, 0),
    new THREE.Vector3(0, -0.5, 0),
  ])
  triangle.computeVertexNormals()
  const points = []
  const flags = []
  for (let i = 0; i <= count; i++) {
    const k = i / count
    const p = start.clone().lerp(end, k)
    p.y -= Math.sin(k * Math.PI) * sag
    points.push(p)
    if (i === 0 || i === count) continue
    const flag = new THREE.Mesh(triangle, mat(colors[i % colors.length], { side: THREE.DoubleSide }))
    flag.position.copy(p)
    flag.rotation.y = turn
    flags.push(flag)
    group.add(flag)
  }
  group.add(
    new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: '#30343a' })),
  )
  group.update = (t) => {
    flags.forEach((flag, i) => {
      flag.rotation.x = Math.sin(t * 3 + i * 0.7) * 0.25
    })
  }
  return group
}
