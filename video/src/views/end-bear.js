import * as THREE from 'three'
import { progress, track } from '../kit/anim.js'
import { at, box } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { liveTexture } from '../kit/sign.js'
import { caption, FONT } from '../kit/text.js'
import { lights, pine, sky, snowbank, snowGround, stars } from '../kit/world.js'
import { NUMBERS } from '../timeline.js'

// The end, "November 2026" (rough set): a polar bear on a fell under northern lights turns slowly and stares.
// "Remember November 2026? It was us." Beats (local seconds): 0.4–1.6 the head turns · 1.35 the first line ·
// 2.15 "It was us." · 2.6 the team name.

function polarBear(calendarLines) {
  const root = new THREE.Group()
  root.add(at(box(1.5, 1.7, 1.2, C.bear), 0, 1.15, 0))
  root.add(at(box(1.7, 0.6, 1.6, C.bear), 0, 0.3, 0.1))
  for (const x of [-0.45, 0.45]) root.add(at(box(0.45, 0.35, 0.8, C.bear), x, 0.18, 0.75))
  const head = at(new THREE.Group(), 0, 2.05, 0.05)
  head.add(at(box(1.0, 0.85, 0.9, C.bear), 0, 0.4, 0))
  head.add(at(box(0.5, 0.36, 0.42, '#e3e7eb'), 0, 0.25, 0.6))
  head.add(at(box(0.2, 0.13, 0.08, '#111111'), 0, 0.38, 0.82))
  for (const x of [-0.26, 0.26]) {
    head.add(at(box(0.1, 0.12, 0.04, '#111111', { shadow: false }), x, 0.55, 0.46))
    head.add(at(box(0.24, 0.24, 0.14, C.bear), x * 1.45, 0.86, -0.05))
  }
  root.add(head)
  for (const side of [-1, 1]) {
    const arm = at(new THREE.Group(), side * 0.72, 1.75, 0.15)
    arm.add(at(box(0.42, 1.0, 0.45, C.bear), 0, -0.45, 0))
    arm.rotation.set(-1.0, 0, side * -0.25)
    root.add(arm)
  }
  const page = liveTexture(256, 300, (g, _state, w, h) => {
    g.fillStyle = '#ffffff'
    g.fillRect(0, 0, w, h)
    g.fillStyle = '#d42a2a'
    g.fillRect(0, 0, w, 80)
    g.fillStyle = '#ffffff'
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    g.font = `900 34px ${FONT}`
    g.fillText(calendarLines[0], w / 2, 42)
    g.fillStyle = '#111111'
    g.font = `900 92px ${FONT}`
    g.fillText(calendarLines[1], w / 2, 190)
  })
  page.set({})
  root.add(
    at(
      new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.4), new THREE.MeshLambertMaterial({ map: page.texture })),
      0,
      1.25,
      0.95,
    ),
  )
  return { root, head }
}

function curtainTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 256
  const g = canvas.getContext('2d')
  const gradient = g.createLinearGradient(0, 256, 0, 0)
  gradient.addColorStop(0, 'rgba(93,255,176,0)')
  gradient.addColorStop(0.25, 'rgba(93,255,176,0.9)')
  gradient.addColorStop(0.7, 'rgba(155,93,255,0.35)')
  gradient.addColorStop(1, 'rgba(155,93,255,0)')
  g.fillStyle = gradient
  g.fillRect(0, 0, 32, 256)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

export default {
  /** A low drone, an eerie music box, a boom on "It was us." */
  sounds() {
    const melody = [
      [81, 0],
      [84, 0.35],
      [83, 0.7],
      [79, 1.05],
      [76, 1.4],
      [77, 1.75],
      [76, 2.1],
      [72, 2.45],
    ]
    return [
      { at: 0, sound: 'drone', length: 3.4, note: 33, gain: 0.2 },
      ...melody.map(([note, at]) => ({ at, sound: 'musicBox', note, gain: 0.22, wet: 0.6 })),
      { at: 2.15, sound: 'boom', gain: 0.7 },
      { at: 1.35, voice: 'end-remember' },
      { at: 2.15, voice: 'end-us' },
    ]
  },
  build(segment) {
    const lines = segment.lines
    const rand = rng(51)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog('#050a20', 25, 110)
    sky(scene, '#01030f', '#0d2142')
    scene.add(stars(rand, { radius: 300 }))
    lights(scene, {
      skyColor: '#3a5a9a',
      groundColor: '#0a0f1e',
      fill: 0.7,
      sun: '#bcd0ff',
      sunIntensity: 1.0,
      from: [8, 14, 12],
      area: 14,
    })
    const auroraLight = new THREE.DirectionalLight('#5dffb0', 0.6)
    auroraLight.position.set(0, 20, -40)
    scene.add(auroraLight)
    scene.add(snowGround(rand, { bump: 0.5 }))
    scene.add(at(snowbank(rand, { w: 16, h: 2.0, d: 12 }), 0, 0, -1))
    for (let n = 0; n < 40; n++) {
      scene.add(at(pine(rand, { height: rand.range(5, 9) }), rand.range(-60, 60), 0, rand.range(-50, -14)))
    }

    const texture = curtainTexture()
    const curtains = []
    for (let k = 0; k < 3; k++) {
      const geometry = new THREE.PlaneGeometry(110, 26, 64, 1)
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        fog: false,
        opacity: 0.8,
      })
      const curtain = at(new THREE.Mesh(geometry, material), k * 8 - 8, 24 + k * 3, -70 - k * 12)
      curtains.push({ curtain, base: geometry.attributes.position.array.slice(), k })
      scene.add(curtain)
    }

    const bear = polarBear(lines.calendar)
    scene.add(at(bear.root, 0, 1.85, 0))

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1000)
    return {
      scene,
      camera,
      update(t) {
        for (const { curtain, base, k } of curtains) {
          const p = curtain.geometry.attributes.position
          for (let i = 0; i < p.count; i++) {
            const x = base[i * 3]
            p.setXYZ(
              i,
              x,
              base[i * 3 + 1] + Math.sin(x * 0.09 + t * 0.8 + k * 2) * 1.2,
              Math.sin(x * 0.05 + t * 0.5 + k) * 7,
            )
          }
          p.needsUpdate = true
        }
        bear.head.rotation.set(
          0,
          track(t, [
            [0.4, 1.1],
            [1.6, 0, 'inOutCubic'],
          ]),
          0.12 * progress(t, 1.6, 2.6),
        )
        const [x, y, z] = track(t, [
          [0, [0.6, 3.9, 9.5]],
          [3.4, [0.2, 3.7, 6.4]],
        ])
        camera.position.set(x, y, z)
        camera.lookAt(0, 2.7, 0)
        camera.rotateZ(0.03)
      },
      overlay(g, t) {
        caption(g, t, lines.remember, { t0: 1.35, y: 1180, size: 76, type: 0.5 })
        caption(g, t, lines.us, { t0: 2.15, y: 1330, size: 128, fill: '#ff4545' })
        caption(g, t, NUMBERS.team, { t0: 2.6, y: 1450, size: 48, fill: '#cfe3ff' })
      },
    }
  },
}
