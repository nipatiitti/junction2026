import * as THREE from 'three'
import { ease, lerp, pop, progress, track } from '../kit/anim.js'
import { car } from '../kit/car.js'
import { character, POSES, pose } from '../kit/character.js'
import { burst, flash, shake, snowfall, speedLines } from '../kit/fx.js'
import { at, box, glow, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { noise, rng } from '../kit/rng.js'
import { liveTexture, sign } from '../kit/sign.js'
import { caption, FONT, outlined, rounded, toScreen, UI } from '../kit/text.js'
import { building, lamp, lights, pole, sky, snowbank, snowGround } from '../kit/world.js'

// Scene 3, "Taxi is cooked": 3 AM in Helsinki. The ride apps ask over €40, we ask €6.70, and our car drifts in so
// hard that the snow buries the competition. The texts are in timeline.js.
// Beats (local seconds):
//   0–2.5    push in on the student outside the kebab shop; the ride app lists the prices; 1.5 "Bro…"
//   2.5      our ride pops in at €6.70 (flash, zoom punch); the other prices get struck out
//   3.2–4.5  the camera circles him doing the 6-7 hands: "SIX SEVEN!"
//   4.5–5.6  our car drifts in; at 5.05 a wave of snow flies down the street and hits the camera
//   5.6–6.9  the black and green cars are buried, the taxi sign flies off in confetti: "COOKED"; Unc despairs
//   6.9–7.6  the student walks to the car and gets in
//   7.6–8.3  through the windscreen: "W chews."
//   8.3–9.0  Unc on the kerb with a tiny violin; our car blasts past and snows him in

const OURS = 2.5 // our ride pops in
const STOP = 2.6 // where our car stops
const LANE = -2.6 // the kerb lane
const WAVE = 5.05 // the snow wave leaves
const POP = 5.75 // the taxi sign flies off
const BOARD = 7.5 // the student is in the car
const TAXI_X = -6.5
const BURIED = [-11.5, -16.5] // the black and the green car
const STUDENT = [2.0, 0.24, -5.0]
const UNC_STAND = [-5.6, 0.24, -4.7]
const UNC_SIT = [-3.9, -0.62, -4.05] // hips on the kerb
const RIDE_COLOURS = [C.taxiYellow, '#15161a', '#2fbf5a']

const carX = (t) =>
  track(t, [
    [4.5, 45],
    [5.5, STOP, 'outCubic'],
    [8.3, STOP],
    [9.0, -70, 'inQuad'],
  ])
const mixed = (a, b, k) => a.map((x, i) => lerp(x, b[i], k))

function doner(g, state, w, h) {
  const gradient = g.createLinearGradient(0, 0, 0, h)
  gradient.addColorStop(0, '#ffd88a')
  gradient.addColorStop(1, '#ff9f43')
  g.fillStyle = gradient
  g.fillRect(0, 0, w, h)
  g.fillStyle = '#7a4a2a'
  g.fillRect(0, h * 0.72, w, h * 0.28)
  // the spit: stripes that move sideways look like it turns
  const cx = w * 0.3
  for (let i = 0; i < 9; i++) {
    const y = h * 0.12 + i * h * 0.065
    const half = w * (0.07 - i * 0.004)
    g.fillStyle = (i + state.turn) % 2 ? '#8b4a2b' : '#a8653a'
    g.fillRect(cx - half, y, half * 2, h * 0.066)
  }
  g.fillStyle = '#c9ccd1'
  g.fillRect(cx - 3, h * 0.06, 6, h * 0.7)
  g.fillStyle = '#ffffff'
  g.fillRect(w * 0.55, h * 0.1, w * 0.34, h * 0.42)
  g.fillStyle = '#c81d25'
  g.font = `900 ${h * 0.09}px ${FONT}`
  g.textAlign = 'center'
  g.fillText('KEBAB', w * 0.72, h * 0.24)
  g.fillStyle = '#111111'
  g.font = `700 ${h * 0.07}px ${UI}`
  for (const [i, text] of ['+ RANSKIS', '+ VALKOSIPULI', '9,90 €'].entries())
    g.fillText(text, w * 0.72, h * (0.33 + i * 0.08))
}

/** The ride app on the student's phone. */
function rideApp(g, t, lines, scale) {
  if (scale <= 0.01) return
  const w = 640
  const h = 760
  g.save()
  g.translate(540, 1180)
  g.scale(scale, scale)
  g.fillStyle = '#0d0d10'
  rounded(g, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 64)
  g.fillStyle = '#f2f4f7'
  rounded(g, -w / 2, -h / 2, w, h, 46)
  g.textBaseline = 'middle'
  g.textAlign = 'left'
  g.fillStyle = '#111111'
  g.font = `700 30px ${UI}`
  g.fillText(lines.clock, -w / 2 + 40, -h / 2 + 42)
  g.textAlign = 'right'
  g.fillStyle = '#e8262b'
  g.fillText(lines.battery, w / 2 - 80, -h / 2 + 42)
  g.strokeStyle = '#111111'
  g.lineWidth = 3
  g.strokeRect(w / 2 - 70, -h / 2 + 31, 34, 22)
  g.fillStyle = '#e8262b'
  g.fillRect(w / 2 - 68, -h / 2 + 33, 4, 18)
  g.textAlign = 'left'
  g.fillStyle = '#7a8090'
  g.font = `600 28px ${UI}`
  g.fillText(lines.whereTo, -w / 2 + 40, -h / 2 + 100)
  g.fillStyle = '#111111'
  g.font = `800 44px ${UI}`
  g.fillText(lines.where, -w / 2 + 40, -h / 2 + 145)
  const rows = lines.rides.map((ride, i) => ({ ride, t0: 0.55 + i * 0.22, colour: RIDE_COLOURS[i], ours: false }))
  rows.push({ ride: lines.ours, t0: OURS, colour: '#ffffff', ours: true })
  let top = -h / 2 + 200
  for (const { ride, t0, colour, ours } of rows) {
    if (t < t0) continue
    const [name, price, wait] = ride
    const height = ours ? 130 : 104
    const s = ease.outBack(progress(t, t0, t0 + 0.2))
    g.save()
    g.translate(0, top + height / 2)
    g.scale(s, s)
    g.fillStyle = ours ? C.ourRed : '#ffffff'
    rounded(g, -w / 2 + 24, -height / 2, w - 48, height, 24)
    g.fillStyle = colour
    rounded(g, -w / 2 + 44, -28, 56, 56, 14)
    g.textAlign = 'left'
    g.fillStyle = ours ? '#ffffff' : '#111111'
    g.font = `800 ${ours ? 44 : 36}px ${UI}`
    g.fillText(name, -w / 2 + 120, -12)
    g.fillStyle = ours ? '#ffe3e3' : '#7a8090'
    g.font = `600 26px ${UI}`
    g.fillText(wait, -w / 2 + 120, 26)
    g.textAlign = 'right'
    g.fillStyle = ours ? '#ffffff' : '#111111'
    g.font = `900 ${ours ? 54 : 38}px ${UI}`
    g.fillText(price, w / 2 - 48, 0)
    if (!ours && t >= OURS + 0.25) {
      const width = g.measureText(price).width + 12
      g.strokeStyle = '#e8262b'
      g.lineWidth = 6
      g.beginPath()
      g.moveTo(w / 2 - 42 - width, 2)
      g.lineTo(w / 2 - 42 - width + width * progress(t, OURS + 0.25, OURS + 0.45), 2)
      g.stroke()
    }
    g.restore()
    top += height + 18
  }
  g.restore()
}

/** Wet snow on the lens: a few soft white blobs that fade. */
function splat(g, a) {
  if (a <= 0) return
  const rand = rng(77)
  g.save()
  for (let i = 0; i < 7; i++) {
    const x = rand.range(80, 1000)
    const y = rand.range(500, 1500)
    const r = rand.range(90, 220)
    const blob = g.createRadialGradient(x, y, 0, x, y, r)
    blob.addColorStop(0, `rgba(255,255,255,${0.85 * a})`)
    blob.addColorStop(0.6, `rgba(240,246,255,${0.55 * a})`)
    blob.addColorStop(1, 'rgba(240,246,255,0)')
    g.fillStyle = blob
    g.beginPath()
    g.arc(x, y, r, 0, Math.PI * 2)
    g.fill()
  }
  g.restore()
}

export default {
  build(segment) {
    const lines = segment.lines
    const rand = rng(31)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog('#0b1026', 14, 70)
    sky(scene, '#04061a', '#1c2650')
    lights(scene, {
      skyColor: '#4a5aa0',
      groundColor: '#151022',
      fill: 0.8,
      sun: '#a9b8ff',
      sunIntensity: 0.7,
      from: [10, 16, 8],
      area: 24,
    })
    scene.add(at(new THREE.PointLight('#ff3ea5', 40, 14), 2, 3.8, -6.2))
    scene.add(at(new THREE.PointLight('#9fb4ff', 10, 10), 2.6, 3.2, -1.6))
    scene.add(at(new THREE.PointLight('#ffd0b0', 6, 6), 2.4, 2.4, -3.2))
    scene.add(at(new THREE.PointLight('#ffd0b0', 5, 6), -2.6, 2.2, -2.6))
    scene.add(snowGround(rand, { bump: 0.15 }))

    // The street: road, kerb, tram rails, snow along the kerb, houses on both sides
    scene.add(at(box(120, 0.1, 9, C.asphalt, { shadow: false }), 0, 0.05, 0.5))
    scene.add(at(box(120, 0.24, 3.4, '#5b6170'), 0, 0.12, -5.6))
    for (const z of [0.6, 2.0]) scene.add(at(box(120, 0.04, 0.12, '#9aa0aa', { shadow: false }), 0, 0.12, z))
    for (const x of [-21, -9.2, -14, 7.5, 11, 16]) {
      scene.add(at(snowbank(rand, { w: rand.range(2, 3.5), h: 0.5, d: 0.9 }), x, 0.1, -3.75))
    }
    for (const side of [-1, 1]) {
      let x = -46
      while (x < 46) {
        const w = rand.range(7, 10)
        const colour = rand.pick(['#6b5d73', '#4f5d75', '#7a6a58', '#5d6b5e', '#8a7f8f'])
        const block = building(rand, { w, h: rand.range(9, 17), d: 8, color: colour, lit: 0.45 })
        scene.add(at(block, x + w / 2, 0, side * 11.4))
        x += w + 0.4
      }
    }

    // The kebab shop, the taxi rank and the lamps
    scene.add(at(sign(lines.shop, { w: 7, h: 1.4, bg: '#1a0612', fg: '#ff3ea5', neon: true }), 2, 5.0, -7.3))
    const shopWindow = liveTexture(512, 230, doner)
    const glass = new THREE.MeshBasicMaterial({ map: shopWindow.texture, toneMapped: false })
    scene.add(at(new THREE.Mesh(new THREE.PlaneGeometry(5, 2.2), glass), 2, 1.55, -7.33))
    scene.add(at(pole(3.2), -9, 0.24, -4.6))
    scene.add(at(sign('TAXI', { w: 1.2, h: 0.5, bg: C.taxiYellow }), -9, 3.4, -4.55))
    for (const x of [-14, 6, 20]) scene.add(at(lamp(), x, 0.24, -4.5))
    for (const x of [-14, 6]) scene.add(at(new THREE.PointLight('#ffd9a0', 25, 12), x + 0.85, 5.2, -4.5))
    const snow = snowfall(rand, { count: 1800, size: [44, 16, 30], speed: 2.2, flake: 0.06 })
    scene.add(snow.object)

    // The cars at the kerb: the taxi, and the two that the snow will bury
    const taxi = car({ color: C.taxiYellow, taxi: true, snowy: true })
    scene.add(at(taxi.root, TAXI_X, 0.1, LANE))
    const mounds = []
    for (const [i, x] of BURIED.entries()) {
      scene.add(at(car({ color: i === 0 ? '#15161a' : '#2fbf5a', snowy: true }).root, x, 0.1, LANE))
      const mound = snowbank(rand, { w: 4.6, h: 1.8, d: 2.6 })
      mounds.push({ mound, base: mound.scale.clone(), t0: 5.35 + i * 0.12 })
      scene.add(at(mound, x - 0.6, 0, LANE))
    }

    // The student, Unc and his violin
    const student = character({ shirt: '#3c6e71', puffer: true, beanie: '#e8262b', pants: '#2b2b2b', hair: 'none' })
    student.handR.add(at(box(0.13, 0.24, 0.04, '#121214'), 0, -0.05, 0.12))
    const kebab = new THREE.Group()
    kebab.add(mesh(new THREE.CylinderGeometry(0.1, 0.06, 0.34, 7), '#e6c48f'))
    kebab.add(at(box(0.14, 0.06, 0.14, '#8b4a2b'), 0, 0.17, 0))
    student.handL.add(at(kebab, 0, -0.08, 0.1))
    scene.add(student.root)
    const unc = character({
      shirt: '#8a7a5a',
      pants: '#55575c',
      hairColor: '#c9ccd1',
      glasses: true,
      mustache: true,
      cap: '#4a4f57',
    })
    const violin = at(box(0.18, 0.5, 0.08, '#8b4a2b'), 0, -0.05, 0.15)
    const bow = at(box(0.02, 0.6, 0.02, '#d9c9a0'), 0, -0.05, 0.15)
    unc.handL.add(violin)
    unc.handR.add(bow)
    const snowCap = at(box(0.62, 0.22, 0.6, C.snow), 0, 0.72, 0)
    unc.head.add(snowCap)
    scene.add(unc.root)

    // Our car with the developer at the wheel, its headlights, and the snow it throws
    const ours = car({ color: C.ourRed, stripe: true, glass: 0.2 })
    const dev = character({ shirt: C.hoodieRed, hood: true, sunglasses: true })
    dev.root.scale.setScalar(0.7)
    dev.root.rotation.y = Math.PI / 2
    ours.driver.add(at(dev.root, 0, -0.09, 0))
    const beam = new THREE.SpotLight('#fff3d6', 80, 30, 0.45, 0.5)
    beam.position.set(2.1, 0.7, 0)
    beam.target.position.set(12, 0, 0)
    ours.body.add(beam, beam.target)
    const cone = new THREE.ConeGeometry(1.5, 8, 16, 1, true).rotateZ(Math.PI / 2)
    const haze = new THREE.MeshBasicMaterial({
      color: '#fff6d8',
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
      toneMapped: false,
    })
    const beams = [-0.6, 0.6].map((z) => at(new THREE.Mesh(cone, haze), 6.1, 0.65, z))
    ours.body.add(...beams)
    scene.add(ours.root)
    const lump = new THREE.IcosahedronGeometry(0.09, 0)
    const spray = burst(rng(34), {
      count: 500,
      origin: (when, r) => [carX(when) + 1.6, 0.25, LANE + r.range(-0.9, 0.9)],
      start: 4.7,
      spread: 0.8,
      dir: [0.3, 0, 1],
      cone: 1.6,
      speed: [3, 9],
      up: [1.5, 4],
      floor: 0.12,
      geometry: lump,
      material: glow('#dfe8f5'),
    })
    const wave = burst(rng(32), {
      count: 900,
      origin: (when, r) => [carX(when) - 1.5, 0.3, LANE - 0.3 + r.range(-1, 1)],
      start: WAVE,
      spread: 0.5,
      dir: [-1, 0, 0],
      cone: 0.5,
      speed: [12, 24],
      up: [2.5, 5],
      floor: 0.12,
      geometry: lump,
      material: glow('#dfe8f5'),
    })
    const confetti = burst(rng(33), {
      count: 300,
      origin: [TAXI_X - 0.7, 2.0, LANE],
      start: POP,
      spread: 0.15,
      speed: [1, 4],
      up: [4, 8],
      floor: 0.12,
      geometry: new THREE.BoxGeometry(0.12, 0.01, 0.08),
      material: mat('#ffffff'),
      colors: ['#ff3ea5', '#f5c518', '#2b7de9', '#2fbf5a', '#ffffff'],
      flat: true,
    })
    const passBy = burst(rng(35), {
      count: 90,
      origin: (when, r) => [carX(when) + 1.6, 0.25, LANE + r.range(-0.9, 0.9)],
      start: 8.35,
      spread: 0.3,
      dir: [0, 0, -1],
      cone: 1.2,
      speed: [2, 6],
      up: [2, 4.5],
      floor: 0.12,
      geometry: lump,
      material: glow('#dfe8f5'),
    })
    scene.add(spray.object, wave.object, confetti.object, passBy.object)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1000)
    const spot = new THREE.Vector3()
    return {
      scene,
      camera,
      update(t) {
        snow.update(t)
        shopWindow.set({ turn: Math.floor(t * 12) % 2 })
        spray.update(t)
        wave.update(t)
        confetti.update(t)
        passBy.update(t)

        // Our car drifts in, waits, and leaves
        const x = carX(t)
        ours.root.visible = x > -70 && x < 44
        ours.root.position.set(x, 0.1, LANE)
        ours.root.rotation.y =
          Math.PI +
          track(t, [
            [4.5, -0.9],
            [5.25, 0.45, 'outQuad'],
            [5.7, 0, 'outBack'],
          ])
        ours.spin(-x)
        for (const b of beams) b.visible = t < 5.6
        pose(dev, {
          ...POSES.sit,
          armL: [-1.2, 0, -0.15],
          armR: [-1.2, 0, 0.15],
          head: t >= 7.6 && t < 8.3 ? [0.1 * Math.sin(t * 10), -0.5, 0] : [0, 0, 0],
        })

        // The snow buries the black and the green car; the taxi sign flies off
        for (const { mound, base, t0 } of mounds) {
          const k = ease.outBack(progress(t, t0, t0 + 0.45))
          mound.visible = k > 0
          mound.scale.copy(base).multiplyScalar(Math.max(k, 0.001))
        }
        const tau = Math.max(0, t - POP)
        taxi.taxiSign.position.set(-0.7 - 1.2 * tau, Math.max(-0.4, 1.83 + 7 * tau - 4.9 * tau * tau), 0)
        taxi.taxiSign.rotation.set(9 * tau, 0, 6 * tau)

        // The student: phone, a stare, the 6-7 hands, watching the car, walking to it, eating in it
        const inCar = t >= BOARD
        if (inCar && student.root.parent !== ours.seat) ours.seat.add(student.root)
        if (!inCar && student.root.parent !== scene) scene.add(student.root)
        if (inCar) {
          student.root.position.set(0, -0.09, 0)
          student.root.rotation.set(0, Math.PI / 2, 0)
          student.root.scale.setScalar(0.7)
          const bite = t >= 7.7 && t < 8.3 ? 0.15 * Math.abs(Math.sin(t * 16)) : 0
          pose(student, { ...POSES.sit, armL: [-2.2 + bite, 0, -0.35], armR: [-1.0, 0, 0.2], head: [0, 0.3, 0] })
        } else {
          const walk = progress(t, 6.9, BOARD)
          student.root.position.set(lerp(STUDENT[0], 2.9, walk), STUDENT[1], lerp(STUDENT[2], -4.0, walk))
          student.root.rotation.set(0, walk > 0 ? lerp(0, 0.6, walk) : 0, 0)
          student.root.scale.setScalar(1)
          // eyes: normal, then the dead "Bro…" stare, then wide at €6.70
          student.eyes.scale.y = t < 1.4 ? 1 : t < OURS ? 0.45 : t < 3.2 ? 1.7 : 1
          if (t < OURS)
            pose(student, { ...POSES.phone, lift: Math.sin(t * 40) * 0.01, head: [t < 1.4 ? 0.25 : -0.05, 0, 0] })
          else if (t < 3.2) pose(student, { ...POSES.phone, head: [-0.1, 0, 0] })
          else if (t < 4.5) pose(student, { ...POSES.sixSeven(t), head: [-0.1, 0, 0] })
          else if (t < 6.9)
            pose(student, { armR: [-0.4, 0, 0], armL: [-1.1, 0, -0.2], head: [0, t < 5.6 ? 0.9 : -0.5, 0] })
          else
            pose(student, {
              armR: [Math.sin(t * 14) * 0.5, 0, 0],
              armL: [-1.1, 0, -0.2],
              legL: [Math.sin(t * 14) * 0.6, 0, 0],
              legR: [-Math.sin(t * 14) * 0.6, 0, 0],
            })
        }

        // Unc: by his taxi, then despair, then the tiny violin on the kerb
        snowCap.visible = t >= 8.55
        if (t < 6.9) {
          unc.root.position.set(...UNC_STAND)
          violin.visible = false
          bow.visible = false
          if (t < 5.6) pose(unc, { armR: [-0.9, 0, 0.6], armL: [-0.9, 0, -0.6], head: [0, t > 4.6 ? 0.8 : 0.3, 0] })
          else
            pose(unc, {
              armR: [-2.6, 0, 0.5],
              armL: [-2.6, 0, -0.5],
              head: [0.25, -0.4, 0],
              lift: Math.abs(noise(t * 20, 3)) * 0.05,
            })
        } else {
          unc.root.position.set(...UNC_SIT)
          violin.visible = true
          bow.visible = true
          pose(unc, {
            ...POSES.sit,
            armL: [-1.6, 0, -0.5],
            armR: [-1.2 + 0.25 * Math.sin(t * 10), 0, 0.3],
            head: [0.35, 0, 0.2],
          })
        }

        // The camera
        let position
        let target
        let fov = 50
        if (t < OURS) {
          const k = ease.inOutQuad(progress(t, 0, OURS))
          position = mixed([6.2, 3.4, 4.5], [2.45, 2.05, -1.7], k)
          target = mixed([2.0, 2.6, -5.2], [2.0, 1.75, -5.0], k)
        } else if (t < 3.2) {
          position = [2.45, 2.05, -1.7]
          target = [2.0, 1.75, -5.0]
          fov = lerp(50, 46, ease.outCubic(progress(t, OURS, OURS + 0.15)))
        } else if (t < 4.5) {
          const a = track(t, [
            [3.2, -0.6],
            [4.5, 0.8],
          ])
          position = [STUDENT[0] + Math.sin(a) * 4.2, 1.95, STUDENT[2] + Math.cos(a) * 4.2]
          target = [STUDENT[0], 1.6, STUDENT[2]]
        } else if (t < 5.6) {
          const follow = ease.inOutQuad(progress(t, 4.5, 5.3))
          position = [-0.4, 0.75, 0.9]
          target = mixed([14, 1.2, LANE], [x, 0.9, LANE], follow)
        } else if (t < 6.9) {
          position = [-3.2, 2.6, 2.5]
          target = [-11.5, 0.8, -2.8]
        } else if (t < 7.6) {
          position = [-4.5, 2.6, -6.2]
          target = [2.4, 1.0, -3.8]
        } else if (t < 8.3) {
          position = [-1.6, 1.9, LANE]
          target = [STOP + 0.35, 1.3, LANE]
          fov = 34
        } else {
          position = [-0.6, 1.9, 1.6]
          target = [UNC_SIT[0], 1.0, UNC_SIT[2]]
        }
        const punch = shake(t, OURS, 0.35, 0.06)
        const hit = shake(t, 5.15, 0.5, 0.12, { seed: 6 })
        camera.position.set(position[0] + punch[0] + hit[0], position[1] + punch[1] + hit[1], position[2] + hit[2])
        camera.lookAt(...target)
        if (camera.fov !== fov) {
          camera.fov = fov
          camera.updateProjectionMatrix()
        }
      },
      overlay(g, t) {
        const shown = t < 0.4 ? 0 : t < 3.0 ? 0.64 * pop(t, 0.4, 0.3) : 0.64 * (1 - ease.inCubic(progress(t, 3.0, 3.3)))
        const bump = t >= OURS ? 1 + 0.08 * (1 - progress(t, OURS, OURS + 0.25)) : 1
        rideApp(g, t, lines, shown * bump)
        caption(g, t, lines.bro, { t0: 1.5, t1: OURS, y: 850, size: 84 })
        flash(g, t >= OURS ? 0.5 * (1 - progress(t, OURS, OURS + 0.25)) : 0)

        // the 6 and the 7 pop at whichever hand is up
        if (t >= 3.2 && t < 4.5) {
          const s = Math.sin(t * 14)
          for (const [hand, text, up] of [
            [student.handL, '6', s],
            [student.handR, '7', -s],
          ]) {
            if (up <= 0.2) continue
            hand.getWorldPosition(spot)
            const [hx, hy] = toScreen(spot, camera)
            outlined(g, text, hx, hy - 110, 90 + 70 * up, { fill: '#ffe14d', line: 16 })
          }
          caption(g, t, lines.sixSeven, { t0: 3.25, t1: 4.5, y: 1380, size: 110 })
        }
        speedLines(
          g,
          t,
          track(t, [
            [4.5, 0],
            [4.7, 0.8],
            [5.4, 0],
          ]),
          { seed: 9 },
        )
        splat(g, t >= 5.2 ? 1 - progress(t, 5.3, 5.75) : 0)

        // COOKED stamped over the buried cars
        if (t >= 5.9 && t < 6.9) {
          const s = lerp(2.2, 1, ease.outBack(progress(t, 5.9, 6.1)))
          g.save()
          g.translate(560, 980)
          g.rotate(-0.12)
          g.scale(s, s)
          g.globalAlpha = 1 - progress(t, 6.75, 6.9)
          g.strokeStyle = '#ff2d2d'
          g.lineWidth = 14
          g.strokeRect(-330, -95, 660, 190)
          outlined(g, lines.cooked, 0, 6, 150, { fill: '#ff2d2d', line: 18 })
          g.restore()
        }
        caption(g, t, lines.chews, { t0: 7.75, t1: 8.3, y: 1300, size: 100 })

        // notes from the tiny violin
        if (t >= 8.3) {
          unc.head.getWorldPosition(spot)
          const [ux, uy] = toScreen(spot, camera)
          for (let i = 0; i < 3; i++) {
            const k = (t * 0.9 + i / 3) % 1
            outlined(g, '♪', ux + 90 + i * 40 + k * 60, uy - 60 - k * 160, 64, {
              fill: '#cfe3ff',
              line: 8,
              alpha: 1 - k,
            })
          }
        }
      },
    }
  },
}
