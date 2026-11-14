import * as THREE from 'three'
import { progress } from './anim.js'
import { glow } from './materials.js'
import { noise, rng } from './rng.js'

// Effects. Every one is a formula of time, so scrubbing and exporting give the same frames.

const dummy = new THREE.Object3D()

/** Falling snow in a box of `size` above `center`. */
export function snowfall(
  rand,
  { count = 800, size = [40, 20, 40], center = [0, 0, 0], speed = 1.5, flake = 0.06, color = '#ffffff' } = {},
) {
  const flakes = []
  for (let i = 0; i < count; i++) {
    flakes.push({
      x: rand.range(-0.5, 0.5) * size[0],
      y: rand() * size[1],
      z: rand.range(-0.5, 0.5) * size[2],
      s: rand.range(0.6, 1.4),
      p: rand() * 6.28,
    })
  }
  const object = new THREE.InstancedMesh(new THREE.BoxGeometry(flake, flake, flake), glow(color), count)
  object.frustumCulled = false
  const update = (t) => {
    for (let i = 0; i < count; i++) {
      const f = flakes[i]
      const y = (((f.y - t * speed * f.s) % size[1]) + size[1]) % size[1]
      dummy.position.set(center[0] + f.x + Math.sin(t * 1.3 + f.p) * 0.3, center[1] + y, center[2] + f.z)
      dummy.rotation.set(t * 2 + f.p, t + f.p, 0)
      dummy.scale.set(1, 1, 1)
      dummy.updateMatrix()
      object.setMatrixAt(i, dummy.matrix)
    }
    object.instanceMatrix.needsUpdate = true
  }
  update(0)
  return { object, update }
}

/**
 * Pieces thrown from time `start` (money notes, confetti, snow). Each leaves `origin` (a point, or a function of its
 * launch time) on a parabola, spins, and lies still on `floor`. `clock` maps the view's time to the burst's time,
 * for slow motion. `colors` gives each piece one of these colours (use a white material).
 */
export function burst(
  rand,
  {
    count = 200,
    origin = [0, 0, 0],
    start = 0,
    spread = 0.3,
    dir = null,
    cone = Math.PI * 2,
    speed = [3, 8],
    up = [3, 7],
    gravity = 9.8,
    floor = 0,
    geometry,
    material,
    colors = null,
    size = [0.8, 1.3],
    flat = false,
    clock = (t) => t,
  } = {},
) {
  const heading = dir ? Math.atan2(dir[2], dir[0]) : 0
  const pieces = []
  for (let i = 0; i < count; i++) {
    const launch = start + rand() * spread
    const from = typeof origin === 'function' ? origin(launch, rand) : origin
    const a = heading + (rand() - 0.5) * cone
    const s = rand.range(speed[0], speed[1])
    const vy = rand.range(up[0], up[1])
    const drop = Math.max(0, from[1] - floor)
    pieces.push({
      launch,
      from,
      vx: Math.cos(a) * s,
      vz: Math.sin(a) * s,
      vy,
      hit: (vy + Math.sqrt(vy * vy + 2 * gravity * drop)) / gravity,
      spin: [rand.range(-9, 9), rand.range(-9, 9), rand.range(-9, 9)],
      scale: rand.range(size[0], size[1]),
      turn: rand() * 6.28,
    })
  }
  const object = new THREE.InstancedMesh(geometry, material, count)
  object.frustumCulled = false
  object.castShadow = true
  if (colors) {
    const c = new THREE.Color()
    for (let i = 0; i < count; i++) object.setColorAt(i, c.set(rand.pick(colors)))
  }
  const update = (t) => {
    const now = clock(t)
    for (let i = 0; i < count; i++) {
      const p = pieces[i]
      const age = now - p.launch
      if (age < 0) {
        dummy.scale.setScalar(0)
      } else {
        const tau = Math.min(age, p.hit)
        dummy.position.set(
          p.from[0] + p.vx * tau,
          p.from[1] + p.vy * tau - 0.5 * gravity * tau * tau,
          p.from[2] + p.vz * tau,
        )
        if (flat && age >= p.hit) dummy.rotation.set(0, p.turn, 0)
        else dummy.rotation.set(p.spin[0] * tau + p.turn, p.spin[1] * tau, p.spin[2] * tau)
        dummy.scale.setScalar(p.scale)
      }
      dummy.updateMatrix()
      object.setMatrixAt(i, dummy.matrix)
    }
    object.instanceMatrix.needsUpdate = true
  }
  update(-1e6)
  return { object, update }
}

/** A sonic-boom ring that grows and fades from t0. Turn `object` to face along the motion. */
export function boomRing({ color = '#ffffff', thickness = 0.06 } = {}) {
  const material = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.8,
    depthWrite: false,
    side: THREE.DoubleSide,
    toneMapped: false,
  })
  const object = new THREE.Mesh(new THREE.TorusGeometry(1, thickness, 6, 40), material)
  object.visible = false
  const update = (t, t0, duration = 0.6, size = 12) => {
    const k = progress(t, t0, t0 + duration)
    object.visible = t >= t0 && k < 1
    object.scale.setScalar(0.4 + k * size)
    material.opacity = 0.9 * (1 - k)
  }
  return { object, update }
}

/** A soft glowing dot that always faces the camera, for stars and sparks. */
export function glowSprite(color = '#fff3c4') {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const g = canvas.getContext('2d')
  const gradient = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, 'rgba(255,255,255,1)')
  gradient.addColorStop(0.25, 'rgba(255,255,255,0.8)')
  gradient.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = gradient
  g.fillRect(0, 0, 128, 128)
  const texture = new THREE.CanvasTexture(canvas)
  return new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: texture,
      color,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
    }),
  )
}

/** Camera shake from t0 for `duration` seconds, fading out: an [x, y, z] offset. */
export function shake(t, t0, duration, amount, { freq = 22, seed = 1 } = {}) {
  const k = progress(t, t0, t0 + duration)
  if (t < t0 || k >= 1) return [0, 0, 0]
  const a = amount * (1 - k) ** 2
  return [noise(t * freq, seed) * a, noise(t * freq, seed + 7) * a, noise(t * freq, seed + 13) * a * 0.4]
}

/** Radial speed streaks over the picture; strength 0–1. */
export function speedLines(g, t, strength, { seed = 3, count = 80 } = {}) {
  if (strength <= 0.01) return
  const { width, height } = g.canvas
  const rand = rng(seed * 1000 + Math.floor(t * 30))
  g.save()
  g.lineCap = 'round'
  for (let i = 0; i < count; i++) {
    const a = rand() * Math.PI * 2
    const inner = rand.range(380, 760)
    const length = rand.range(120, 520) * strength
    g.strokeStyle = `rgba(255,255,255,${(0.25 + rand() * 0.5) * strength})`
    g.lineWidth = rand.range(2, 9)
    g.beginPath()
    g.moveTo(width / 2 + Math.cos(a) * inner, height / 2 + Math.sin(a) * inner * 1.6)
    g.lineTo(width / 2 + Math.cos(a) * (inner + length), height / 2 + Math.sin(a) * (inner + length) * 1.6)
    g.stroke()
  }
  g.restore()
}

/** Covers the picture with a colour at opacity a (0–1). */
export function flash(g, a, color = '255,255,255') {
  if (a <= 0) return
  g.save()
  g.fillStyle = `rgba(${color},${Math.min(1, a)})`
  g.fillRect(0, 0, g.canvas.width, g.canvas.height)
  g.restore()
}
