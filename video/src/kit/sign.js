import * as THREE from 'three'
import { FONT } from './text.js'

// Text in the 3D world: signs, labels and screens drawn on canvas textures.

function paint(g, text, { width, height, bg, fg, size, stroke }) {
  g.fillStyle = bg
  g.fillRect(0, 0, width, height)
  const lines = String(text).split('\n')
  let px = size ?? height * (0.7 / lines.length)
  g.font = `900 ${px}px ${FONT}`
  const widest = Math.max(...lines.map((line) => g.measureText(line).width))
  if (widest > width * 0.9) px *= (width * 0.9) / widest
  g.font = `900 ${px}px ${FONT}`
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  lines.forEach((line, i) => {
    const y = height / 2 + (i - (lines.length - 1) / 2) * px * 1.1
    if (stroke) {
      g.lineWidth = px * 0.12
      g.strokeStyle = stroke
      g.strokeText(line, width / 2, y)
    }
    g.fillStyle = fg
    g.fillText(line, width / 2, y)
  })
}

/** A canvas texture with centred text that shrinks to fit. Lines split on \n. */
export function textTexture(text, { width = 1024, height = 256, bg = '#ffffff', fg = '#111111', size, stroke } = {}) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  paint(canvas.getContext('2d'), text, { width, height, bg, fg, size, stroke })
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

/** A flat sign w × h units with text, facing +z. A neon sign ignores the light. */
export function sign(text, { w = 4, h = 1, bg = '#ffffff', fg = '#111111', neon = false, stroke, size } = {}) {
  const texture = textTexture(text, { width: Math.round((256 * w) / h), height: 256, bg, fg, stroke, size })
  const material = neon
    ? new THREE.MeshBasicMaterial({ map: texture, toneMapped: false })
    : new THREE.MeshLambertMaterial({ map: texture })
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material)
  plane.receiveShadow = !neon
  return plane
}

/** A texture that a view repaints from its state; draw(g, state, width, height) runs only when the state changes. */
export function liveTexture(width, height, draw) {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const g = canvas.getContext('2d')
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  let last = null
  return {
    texture,
    set(state) {
      const key = JSON.stringify(state)
      if (key === last) return
      last = key
      draw(g, state, width, height)
      texture.needsUpdate = true
    },
  }
}
