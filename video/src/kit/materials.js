import * as THREE from 'three'

// Flat-shaded materials, shared by every view: one per colour and option set.
const cache = new Map()

export function mat(color, options = {}) {
  const key = `lambert|${color}|${JSON.stringify(options)}`
  if (!cache.has(key)) cache.set(key, new THREE.MeshLambertMaterial({ color, flatShading: true, ...options }))
  return cache.get(key)
}

/** Unlit colour for lamps, neon and screens. */
export function glow(color, options = {}) {
  const key = `basic|${color}|${JSON.stringify(options)}`
  if (!cache.has(key)) cache.set(key, new THREE.MeshBasicMaterial({ color, toneMapped: false, ...options }))
  return cache.get(key)
}

/** A mesh that casts and receives shadows; `material` is a colour or a material. */
export function mesh(geometry, material, { shadow = true } = {}) {
  const m = new THREE.Mesh(geometry, typeof material === 'string' ? mat(material) : material)
  m.castShadow = shadow
  m.receiveShadow = true
  return m
}

export const box = (w, h, d, material, options) => mesh(new THREE.BoxGeometry(w, h, d), material, options)

/** Puts an object at x, y, z and returns it. */
export function at(object, x = 0, y = 0, z = 0) {
  object.position.set(x, y, z)
  return object
}
