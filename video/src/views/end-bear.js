import * as THREE from 'three'
import { ease, lerp, progress } from '../kit/anim.js'
import { flash, grain, shake, snowfall, sparkle, vignette } from '../kit/fx.js'
import { at, box, mat } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { liveTexture } from '../kit/sign.js'
import { caption, FONT, outlined, UI } from '../kit/text.js'
import { lights, pine, sky, snowbank, snowGround, stars } from '../kit/world.js'
import { NUMBERS } from '../timeline.js'

// The end, "November 2026": a polar bear sits on a fell under the northern lights with a calendar page. It turns
// its head slowly while the camera does a dolly zoom, its eyes glint, and then: "It was us." The texts are in
// timeline.js. Beats (local seconds):
//   0–0.4    wide: the bear on the fell, looking up at the aurora; 0.2 "Remember November 2026?" (voice and text)
//   0.4–1.6  the head turns to the camera; the camera moves in while it widens (the background stretches)
//   1.6      the eyes glint
//   2.35     "It was us." slams in: red flash, a snap zoom, the hackathon days get circled on the calendar
//   3.0      the team name

const GLINT = 1.6
const US = 2.35

function calendarPage(page) {
  return (g, state, w, h) => {
    g.fillStyle = '#ffffff'
    g.fillRect(0, 0, w, h)
    g.fillStyle = '#c9ccd1'
    for (const x of [w * 0.3, w * 0.7]) g.fillRect(x - 6, 0, 12, 22)
    g.fillStyle = '#d42a2a'
    g.fillRect(0, 22, w, 92)
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    g.fillStyle = '#ffffff'
    g.font = `900 44px ${FONT}`
    g.fillText(page.title, w / 2, 70)
    g.fillStyle = '#111111'
    g.font = `900 96px ${FONT}`
    g.fillText(String(page.year), w / 2, 190)
    // the month, Monday first
    const first = (new Date(page.year, page.month - 1, 1).getDay() + 6) % 7
    const days = new Date(page.year, page.month, 0).getDate()
    const cell = w / 7
    const top = 285
    const row = 30
    g.font = `700 20px ${UI}`
    g.fillStyle = '#7a8090'
    for (const [i, day] of ['M', 'T', 'W', 'T', 'F', 'S', 'S'].entries()) g.fillText(day, cell * (i + 0.5), top - 24)
    g.font = `700 24px ${UI}`
    for (let day = 1; day <= days; day++) {
      const index = first + day - 1
      g.fillStyle = index % 7 >= 5 ? '#d42a2a' : '#111111'
      g.fillText(String(day), cell * ((index % 7) + 0.5), top + Math.floor(index / 7) * row)
    }
    if (state.circled) {
      const a = first + page.circled[0] - 1
      const b = first + page.circled.at(-1) - 1
      const x0 = cell * (a % 7) + 2
      const x1 = cell * ((b % 7) + 1) - 2
      g.strokeStyle = '#e8262b'
      g.lineWidth = 5
      g.beginPath()
      g.ellipse((x0 + x1) / 2, top + Math.floor(a / 7) * row, (x1 - x0) / 2, 18, -0.05, 0, Math.PI * 2)
      g.stroke()
    }
  }
}

function polarBear(page) {
  const fur = mat(C.bear, { emissive: '#232838' })
  const root = new THREE.Group()
  const body = new THREE.Group()
  root.add(body)
  body.add(at(box(1.5, 1.7, 1.2, fur), 0, 1.15, 0))
  body.add(at(box(1.7, 0.6, 1.6, fur), 0, 0.3, 0.1))
  for (const x of [-0.45, 0.45]) body.add(at(box(0.45, 0.35, 0.8, fur), x, 0.18, 0.75))
  const head = at(new THREE.Group(), 0, 2.05, 0.05)
  head.add(at(box(1.0, 0.85, 0.9, fur), 0, 0.4, 0))
  head.add(at(box(0.5, 0.36, 0.42, mat('#e3e7eb', { emissive: '#232838' })), 0, 0.25, 0.6))
  head.add(at(box(0.22, 0.14, 0.08, '#111111'), 0, 0.38, 0.82))
  const eyes = []
  for (const x of [-0.24, 0.24]) {
    const eye = at(new THREE.Group(), x, 0.55, 0.46)
    eye.add(box(0.14, 0.16, 0.04, '#0b0b0d', { shadow: false }))
    eye.add(at(box(0.04, 0.04, 0.01, '#ffffff', { shadow: false }), 0.03, 0.04, 0.025))
    head.add(eye)
    eyes.push(eye)
    head.add(at(box(0.24, 0.24, 0.14, fur), x * 1.5, 0.86, -0.05))
  }
  body.add(head)
  for (const side of [-1, 1]) {
    const arm = at(new THREE.Group(), side * 0.72, 1.75, 0.15)
    arm.add(at(box(0.42, 1.0, 0.45, fur), 0, -0.45, 0))
    arm.rotation.set(-1.0, 0, side * -0.25)
    body.add(arm)
  }
  const sheet = liveTexture(320, 460, calendarPage(page))
  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(1.25, 1.8),
    new THREE.MeshLambertMaterial({ map: sheet.texture }),
  )
  body.add(at(plane, 0, 1.15, 0.95))
  return { root, body, head, eyes, sheet }
}

function curtainTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 256
  const g = canvas.getContext('2d')
  const gradient = g.createLinearGradient(0, 256, 0, 0)
  gradient.addColorStop(0, 'rgba(93,255,176,0)')
  gradient.addColorStop(0.2, 'rgba(93,255,176,0.95)')
  gradient.addColorStop(0.6, 'rgba(120,200,255,0.45)')
  gradient.addColorStop(0.85, 'rgba(170,100,255,0.3)')
  gradient.addColorStop(1, 'rgba(170,100,255,0)')
  g.fillStyle = gradient
  g.fillRect(0, 0, 32, 256)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

export default {
  /** A low drone, an eerie music box, a glint, a boom on "It was us." */
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
      { at: 0, sound: 'drone', length: 3.9, note: 33, gain: 0.2 },
      { at: 0, sound: 'whoosh', length: 1.6, from: 200, to: 700, gain: 0.1 },
      ...melody.map(([note, at]) => ({ at, sound: 'musicBox', note, gain: 0.22, wet: 0.6 })),
      { at: GLINT, sound: 'ding', notes: [100], gain: 0.12, wet: 0.5 },
      { at: US, sound: 'boom', gain: 0.8 },
      { at: 0.2, voice: 'end-remember', rate: 1.1 },
      { at: US, voice: 'end-us', rate: 1.05 },
    ]
  },
  build(segment) {
    const lines = segment.lines
    const rand = rng(51)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog('#050a20', 30, 130)
    sky(scene, '#01030f', '#0d2142')
    scene.add(stars(rand, { radius: 300 }))
    lights(scene, {
      skyColor: '#5a6fa8',
      groundColor: '#0e1222',
      fill: 0.6,
      sun: '#e8eeff',
      sunIntensity: 1.0,
      from: [6, 14, 12],
      area: 14,
    })
    const rim = new THREE.DirectionalLight('#5dffb0', 0.9)
    rim.position.set(0, 18, -40)
    scene.add(rim, at(new THREE.PointLight('#ffffff', 3.5, 12), 0, 4, 5))
    scene.add(snowGround(rand, { bump: 0.5, color: '#c4d2ea' }))
    scene.add(at(snowbank(rand, { w: 16, h: 2.0, d: 12 }), 0, 0, -1))
    for (let n = 0; n < 40; n++) {
      scene.add(at(pine(rand, { height: rand.range(5, 9) }), rand.range(-60, 60), 0, rand.range(-50, -14)))
    }
    const snow = snowfall(rand, { count: 500, size: [24, 12, 20], center: [0, 0, 2], speed: 0.5, flake: 0.05 })
    scene.add(snow.object)

    // The northern lights: curtains whose vertices wave with time
    const texture = curtainTexture()
    const curtains = []
    for (let k = 0; k < 4; k++) {
      const geometry = new THREE.PlaneGeometry(120, 30, 64, 1)
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        side: THREE.DoubleSide,
        fog: false,
        opacity: 0.5,
        toneMapped: false,
      })
      const curtain = at(new THREE.Mesh(geometry, material), k * 10 - 15, 24 + k * 3, -55 - k * 10)
      curtains.push({ curtain, base: geometry.attributes.position.array.slice(), k })
      scene.add(curtain)
    }

    const bear = polarBear(lines.calendar)
    scene.add(at(bear.root, 0, 1.85, 0))

    const camera = new THREE.PerspectiveCamera(40, 9 / 16, 0.1, 1000)
    const spot = new THREE.Vector3()
    return {
      scene,
      camera,
      update(t) {
        snow.update(t)
        for (const { curtain, base, k } of curtains) {
          const p = curtain.geometry.attributes.position
          for (let i = 0; i < p.count; i++) {
            const x = base[i * 3]
            p.setXYZ(
              i,
              x,
              base[i * 3 + 1] + Math.sin(x * 0.09 + t * 0.9 + k * 2) * 1.6,
              Math.sin(x * 0.05 + t * 0.6 + k) * 8,
            )
          }
          p.needsUpdate = true
        }

        // The bear breathes, turns its head from the sky to us, and tilts it
        bear.body.scale.y = 1 + 0.015 * Math.sin(t * 3)
        const turn = ease.inOutCubic(progress(t, 0.4, GLINT))
        bear.head.rotation.set(lerp(-0.35, 0, turn), lerp(1.5, 0, turn), 0.14 * ease.outBack(progress(t, GLINT, 2.3)))
        bear.sheet.set({ circled: t >= US })

        // Dolly zoom while it turns (closer and wider, so the background stretches), then a snap zoom on "It was us."
        const k = ease.inOutQuad(progress(t, 0.3, 2.1))
        const distance = lerp(11, 5.6, k)
        const wide = 2 * Math.atan((Math.tan((40 * Math.PI) / 360) * 11) / distance) * (180 / Math.PI)
        const fov = t < US ? wide : lerp(wide, 62, ease.outCubic(progress(t, US, US + 0.15)))
        const [sx, sy] = shake(t, US, 0.45, 0.12)
        camera.position.set(0.3 * (1 - k) + sx, lerp(2.6, 3.1, k) + sy, distance)
        camera.lookAt(0, lerp(2.4, 2.75, ease.outCubic(progress(t, US, US + 0.15))), 0)
        camera.rotateZ(0.03)
        if (camera.fov !== fov) {
          camera.fov = fov
          camera.updateProjectionMatrix()
        }
      },
      overlay(g, t) {
        if (t >= GLINT && t < GLINT + 0.5) {
          for (const eye of bear.eyes) {
            eye.getWorldPosition(spot)
            const p = spot.project(camera)
            sparkle(g, (p.x + 1) * 540, (1 - p.y) * 960, 70 * Math.sin(Math.PI * progress(t, GLINT, GLINT + 0.5)))
          }
        }
        caption(g, t, lines.remember, { t0: 0.2, y: 1230, size: 76, type: 1.6 })
        if (t >= US) {
          const s = lerp(1.8, 1, ease.outBack(progress(t, US, US + 0.2)))
          g.save()
          g.translate(540, 1370)
          g.scale(s, s)
          outlined(g, lines.us, 0, 0, 140, { fill: '#ff3b3b', line: 24 })
          g.restore()
        }
        caption(g, t, NUMBERS.team, { t0: 3.0, y: 1480, size: 46, fill: '#cfe3ff' })
        flash(g, t >= US ? 0.4 * (1 - progress(t, US, US + 0.3)) : 0, '255,40,60')
        vignette(g, 0.5 + 0.3 * progress(t, 0, 3.4))
        grain(g, t, 0.05)
      },
    }
  },
}
