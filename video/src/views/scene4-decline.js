import * as THREE from 'three'
import { ease, lerp, pop, progress } from '../kit/anim.js'
import { car } from '../kit/car.js'
import { character, POSES, pose } from '../kit/character.js'
import { boomRing, burst, flash, glowSprite, shake, sparkle, speedLines } from '../kit/fx.js'
import { at, box, glow, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { sign } from '../kit/sign.js'
import { banner, caption, outlined, rounded, toScreen, UI } from '../kit/text.js'
import { building, jitter, lamp, lights, pine, pole, sky, snowGround, stars } from '../kit/world.js'

// Scene 4, "Nah, I'd win": three gig drivers get our offer at a truck stop at sunset. The NPC accepts at once,
// the gym bro laughs at the fee and declines, and our car passes at light speed and launches him into space.
// The texts are in timeline.js. Beats (local seconds):
//   0–1.8    wide: the phones ding; 1.0 the NPC accepts ("Accepted.")
//   1.8–2.6  the gym bro reads the gig card, laughs ("HAH") and presses DECLINE at 2.45
//   2.6–4.3  low hero shot: bicep heart with an aura; 3.2 "Nah, I'd win."
//   4.3      our car passes at light speed: flash, a red light trail, a sonic boom; he is launched
//   4.4–6.0  the camera tilts after him into the sky; his sunglasses fall into the crater
//   6.0–8.0  space: "BOMBOCLAAAT", he flies past a satellite and becomes a star; "−∞ AURA", "he did not win"
//   8.0–8.9  the crater with his smoking sunglasses between the two others
//   8.9–10   the scared driver presses ACCEPT again and again, sweating

const SPACE = 800 // the space set floats this high above the parking lot
const PASS = 4.3 // our car passes
const LAUNCH = PASS + 0.05 // the gym bro leaves the ground
const STAR = 7.3 // he becomes a star
const LANE_Z = 5.2
const DRIVERS = { npc: -1.5, bro: 0, scared: 1.5 }
const PRESSES = [8.95, 9.3, 9.65] // the scared driver's ACCEPTs
const mixed = (a, b, k) => a.map((x, i) => lerp(x, b[i], k))
/** Seconds until something thrown up at v from h metres above the ground lands. */
const fallTime = (h, v) => (v + Math.sqrt(v * v + 2 * 9.8 * h)) / 9.8
const broHeight = (t) => {
  const tau = Math.max(0, t - LAUNCH)
  return 30 * tau + 12 * tau * tau
}

function heart() {
  const shape = new THREE.Shape()
  shape.moveTo(0, -0.5)
  shape.bezierCurveTo(-0.6, -0.05, -0.55, 0.45, -0.25, 0.45)
  shape.bezierCurveTo(-0.05, 0.45, 0, 0.3, 0, 0.2)
  shape.bezierCurveTo(0, 0.3, 0.05, 0.45, 0.25, 0.45)
  shape.bezierCurveTo(0.55, 0.45, 0.6, -0.05, 0, -0.5)
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: 0.12, bevelEnabled: false, curveSegments: 6 })
  geometry.translate(0, 0, -0.06)
  return new THREE.Mesh(geometry, glow('#ff2d78'))
}

function truck() {
  const group = new THREE.Group()
  group.add(at(box(9, 3.2, 2.6, '#e9e9ee'), -2.2, 2.0, 0))
  group.add(at(box(2.4, 2.8, 2.5, '#2b4c9a'), 3.6, 1.8, 0))
  group.add(at(box(0.1, 1.0, 2.2, mat(C.glassDark)), 4.82, 2.4, 0))
  const tyre = new THREE.CylinderGeometry(0.55, 0.55, 0.4, 10).rotateX(Math.PI / 2)
  for (const x of [-5.5, -4.2, 0.5, 3.8]) for (const z of [-1.1, 1.1]) group.add(at(mesh(tyre, '#17181b'), x, 0.55, z))
  return group
}

/** The gig card on a driver's phone; `press` names the button that gets pressed at each of `times`. */
function gigCard(g, t, lines, { scale, press, times, y = 1170 }) {
  if (scale <= 0.01) return
  const w = 600
  const h = 640
  g.save()
  g.translate(540, y)
  g.scale(scale, scale)
  g.fillStyle = '#0d0d10'
  rounded(g, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 64)
  g.fillStyle = '#f2f4f7'
  rounded(g, -w / 2, -h / 2, w, h, 46)
  g.fillStyle = '#2fbf5a'
  rounded(g, -w / 2, -h / 2, w, 110, 46)
  g.fillRect(-w / 2, -h / 2 + 60, w, 50)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = '#ffffff'
  g.font = `900 46px ${UI}`
  g.fillText(lines.gig, 0, -h / 2 + 56)
  g.fillStyle = '#3a3f4b'
  g.font = `700 34px ${UI}`
  g.fillText(lines.route, 0, -h / 2 + 165)
  g.fillStyle = '#111111'
  g.font = `900 120px ${UI}`
  g.fillText(lines.fee, 0, -h / 2 + 285)
  g.fillStyle = '#7a8090'
  g.font = `600 30px ${UI}`
  g.fillText(lines.typical, 0, -h / 2 + 375)
  const pressed = times.some((when) => t >= when && t < when + 0.18)
  for (const [name, x, bg, fg] of [
    ['decline', -150, '#e5e7eb', '#e8262b'],
    ['accept', 150, '#2fbf5a', '#ffffff'],
  ]) {
    const down = pressed && press === name
    g.save()
    g.translate(x, h / 2 - 110)
    g.scale(down ? 0.9 : 1, down ? 0.9 : 1)
    g.fillStyle = down ? (name === 'decline' ? '#e8262b' : '#1f9a46') : bg
    rounded(g, -125, -55, 250, 110, 28)
    g.fillStyle = down && name === 'decline' ? '#ffffff' : fg
    g.font = `900 40px ${UI}`
    g.fillText(name === 'decline' ? lines.decline : lines.accept, 0, 2)
    g.restore()
  }
  g.restore()
}

export default {
  /** Dings, the buttons, the aura drone, the sonic boom, the rocket whistle, space, the star, the panic taps. */
  sounds() {
    return [
      { at: 0.3, sound: 'ding', gain: 0.25, notes: [88, 93] },
      { at: 0.33, sound: 'ding', gain: 0.18, notes: [86, 91] },
      { at: 0.36, sound: 'ding', gain: 0.15, notes: [84, 89] },
      { at: 1.0, sound: 'tap', gain: 0.15 },
      { at: 1.0, sound: 'ding', gain: 0.12, notes: [96] },
      { at: 2.45, sound: 'tap', gain: 0.18 },
      { at: 2.47, sound: 'slide', from: 400, to: 150, length: 0.25, gain: 0.12 },
      { at: 2.75, sound: 'twinkle', gain: 0.12 },
      { at: 2.9, sound: 'drone', length: 1.45, note: 33, gain: 0.3 },
      { at: 3.6, sound: 'riser', length: 0.7, gain: 0.22 },
      { at: PASS - 0.15, sound: 'whoosh', length: 0.2, from: 1000, to: 8000, gain: 0.5 },
      { at: PASS, sound: 'sonicBoom', gain: 1, wet: 0.4 },
      { at: LAUNCH, sound: 'slide', from: 300, to: 2400, length: 1.5, gain: 0.14 },
      { at: 5.95, sound: 'whoosh', length: 0.3, from: 400, to: 6000, gain: 0.35 },
      { at: 6.0, sound: 'pad', notes: [41, 48, 53, 56], length: 2.2, gain: 0.12, cutoff: 1400, wet: 0.5 },
      { at: 6.05, sound: 'slide', from: 900, to: 180, length: 1.2, gain: 0.12 },
      { at: 7.0, sound: 'boom', gain: 0.7 },
      { at: STAR, sound: 'twinkle', gain: 0.22, wet: 0.5 },
      { at: 8.0, sound: 'whoosh', length: 0.5, from: 200, to: 900, gain: 0.12 },
      ...PRESSES.flatMap((at) => [
        { at, sound: 'tap', gain: 0.2 },
        { at: at + 0.02, sound: 'ding', gain: 0.12, notes: [93] },
      ]),
      { at: 1.0, voice: 'scene4-accepted' },
      { at: 3.2, voice: 'scene4-nah' },
      { at: 6.05, voice: 'scene4-scream' },
      { at: PRESSES[0], voice: 'scene4-panic' },
    ]
  },
  build(segment) {
    const lines = segment.lines
    const rand = rng(41)
    const scene = new THREE.Scene()
    const fog = new THREE.Fog('#f6a670', 30, 140)
    const black = new THREE.Color('#000004')
    const dome = sky(scene, '#4a2c7a', '#ffa262')
    const sun = glowSprite('#ffb066')
    sun.material.fog = false
    sun.scale.setScalar(70)
    scene.add(at(sun, -30, 14, -170))
    lights(scene, {
      sun: '#ffb56b',
      sunIntensity: 2.2,
      from: [-40, 14, -30],
      skyColor: '#ffc9a0',
      groundColor: '#6a4a6a',
      fill: 1.3,
      area: 26,
    })
    scene.add(at(new THREE.PointLight('#ffd8b8', 12, 14), 1.5, 3.2, 6))
    scene.add(snowGround(rand, { flat: 14 }))

    // The motorway, the truck stop, a lorry, the fuel price and the forest
    scene.add(at(box(240, 0.1, 8, C.asphalt, { shadow: false }), 0, 0.05, 6))
    for (let x = -118; x < 120; x += 6) scene.add(at(box(2.6, 0.02, 0.18, C.line, { shadow: false }), x, 0.11, 6))
    scene.add(at(box(34, 0.1, 15, '#4a4e57', { shadow: false }), 0, 0.05, -5.5))
    const stop = at(new THREE.Group(), -1, 0, -9)
    stop.add(at(box(15, 0.6, 8, '#eeeeee'), 0, 5.3, 0))
    stop.add(at(box(15.1, 0.25, 8.1, '#d23b2b'), 0, 5.0, 0))
    for (const px of [-6.5, 6.5]) for (const pz of [-3.2, 3.2]) stop.add(at(box(0.35, 5, 0.35, '#dddddd'), px, 2.5, pz))
    for (const px of [-3, 3]) stop.add(at(box(0.9, 1.7, 0.6, '#3d7be0'), px, 0.85, 0))
    stop.add(at(building(rand, { w: 14, h: 4.5, d: 6, color: '#d8d2c4', lit: 0.6 }), 0, 0, -8))
    scene.add(stop)
    scene.add(at(truck(), -14, 0.1, -4))
    scene.add(at(pole(4.4), 8, 0.1, -3))
    scene.add(at(sign(lines.diesel, { w: 2.6, h: 0.8, bg: '#111111', fg: '#ffd84d', neon: true }), 8, 4.6, -2.95))
    for (const x of [-7, 11]) scene.add(at(lamp(), x, 0.1, -1.5))
    for (const parked of [
      [6, -7, '#9aa3ad'],
      [10.5, -7, '#2b7de9'],
    ]) {
      const c = car({ color: parked[2], snowy: true })
      c.root.rotation.y = -Math.PI / 2
      scene.add(at(c.root, parked[0], 0.1, parked[1]))
    }
    for (let n = 0; n < 60; n++) {
      scene.add(at(pine(rand, { height: rand.range(6, 11) }), rand.range(-80, 80), 0, rand.range(-70, -24)))
    }

    // The three drivers, each with a phone
    const npc = character({ shirt: '#8a8f98', pants: '#5a5f68', hood: true, hair: 'none' })
    const bro = character({ shirt: '#f4f4f4', tank: true, skin: C.skinTan, pants: '#2d2d2d' })
    const scared = character({ shirt: '#6a8caf', glasses: true, pants: '#4a4a4a' })
    scared.root.scale.setScalar(0.86)
    for (const [ch, x] of [
      [npc, DRIVERS.npc],
      [bro, DRIVERS.bro],
      [scared, DRIVERS.scared],
    ]) {
      const handset = at(box(0.13, 0.24, 0.04, '#121214'), 0, -0.05, 0.12)
      handset.rotation.x = 1.2
      ch.handR.add(handset)
      scene.add(at(ch.root, x, 0.1, 0))
    }
    scene.add(at(sign('NPC', { w: 0.9, h: 0.36, bg: '#111111', fg: '#ffffff' }), DRIVERS.npc, 2.75, 0))
    const worn = at(box(0.46, 0.11, 0.03, '#0b0b0d', { shadow: false }), 0, 0.31, 0.265)
    bro.head.add(worn)
    const heldShake = at(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.3, 8), '#ff7ab8'), 0, -0.05, 0.08)
    bro.handL.add(heldShake)
    const bulge = at(box(0.32, 0.26, 0.34, C.skinTan), 0, -0.22, 0.04)
    bro.armR.add(bulge)
    const love = heart()
    love.scale.setScalar(0.32)
    scene.add(love)
    const aura = glowSprite('#8a6bff')
    aura.material.fog = false
    scene.add(aura)

    // What flies off him, and what he leaves behind
    const shades = box(0.46, 0.11, 0.03, '#0b0b0d')
    const flyingShake = mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.3, 8), '#ff7ab8')
    scene.add(shades, flyingShake)
    const crater = mesh(new THREE.CircleGeometry(0.9, 12).rotateX(-Math.PI / 2), '#3a3036', { shadow: false })
    scene.add(at(crater, 0, 0.11, 0.1))
    const smoke = Array.from({ length: 4 }, () => {
      const puff = glowSprite('#b9aeb4')
      puff.material.blending = THREE.NormalBlending
      scene.add(puff)
      return puff
    })
    const dust = burst(rng(42), {
      count: 220,
      origin: [0, 0.2, 0.1],
      start: LAUNCH,
      spread: 0.05,
      speed: [2, 6],
      up: [2, 6],
      floor: 0.12,
      geometry: new THREE.IcosahedronGeometry(0.05, 0),
      material: glow('#f3f0f6'),
    })
    scene.add(dust.object)

    // Our car, its light trail and the boom
    const ours = car({ color: C.ourRed, stripe: true })
    scene.add(ours.root)
    const trailMaterial = new THREE.MeshBasicMaterial({
      color: '#ff3040',
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    })
    const trail = at(new THREE.Mesh(new THREE.BoxGeometry(120, 0.5, 1.2), trailMaterial), 0, 0.8, LANE_Z)
    scene.add(trail)
    const ring = boomRing()
    scene.add(at(ring.object, 0, 1, LANE_Z))

    // Space, high above
    const space = at(new THREE.Group(), 0, SPACE, 0)
    const earth = at(mesh(jitter(new THREE.IcosahedronGeometry(60, 3), 0.02, 3), '#2f6fd6'), 0, -60, -30)
    for (let n = 0; n < 9; n++) {
      const land = mesh(jitter(new THREE.IcosahedronGeometry(1, 1), 0.3, n), '#3fa34d')
      const a = rand.range(-1.2, 1.2)
      const b = rand.range(0.2, 1.3)
      land.position.set(Math.sin(a) * Math.sin(b) * 60, Math.cos(b) * 60, Math.cos(a) * Math.sin(b) * 60)
      land.lookAt(0, 0, 0)
      land.scale.set(rand.range(6, 12), rand.range(4, 9), 1.2)
      earth.add(land)
    }
    space.add(earth, stars(rand, { radius: 300 }))
    const satellite = at(new THREE.Group(), 5, 3, -14)
    satellite.add(box(0.8, 0.8, 1.2, '#c9ccd1'))
    for (const side of [-1, 1]) satellite.add(at(box(3, 0.05, 1, '#2b4c9a'), side * 1.9, 0, 0))
    space.add(satellite)
    const star = glowSprite('#fff3c4')
    star.material.fog = false
    space.add(at(star, 14, 14, -36))
    scene.add(space)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1200)
    const spot = new THREE.Vector3()
    return {
      scene,
      camera,
      update(t) {
        const inSpace = t >= 6 && t < 8
        scene.fog = inSpace ? null : fog
        scene.background = inSpace ? black : null
        dome.visible = !inSpace
        sun.visible = !inSpace
        earth.rotation.y = t * 0.05
        satellite.rotation.set(t * 0.3, t * 0.5, 0)

        // The NPC: checks the phone, accepts, then idles like an NPC
        const idle = t > 1.5 ? [0, Math.sign(Math.sin(t * 2.5)) * 0.35, 0] : POSES.phone.head
        pose(npc, { ...POSES.phone, armL: [-1.05 + (t > 1 && t < 1.25 ? 0.25 : 0), 0, -0.25], head: idle })

        // The gym bro: phone, laugh, DECLINE, bicep heart, launch, space
        const height = broHeight(t)
        bulge.scale.setScalar(t >= 2.6 && t < PASS ? 1 + 0.35 * Math.abs(Math.sin((t - 2.6) * 9)) : 1)
        worn.visible = t < LAUNCH
        heldShake.visible = t < LAUNCH
        if (t < 6) {
          bro.root.visible = true
          bro.root.position.set(DRIVERS.bro, 0.1 + height, 2 * Math.max(0, t - LAUNCH))
          bro.root.rotation.set(7 * Math.max(0, t - LAUNCH), 0, 0)
          bro.root.scale.setScalar(1)
          if (t < 2.0) pose(bro, POSES.phone)
          else if (t < 2.6)
            pose(bro, { ...POSES.phone, torso: [-0.25 + 0.08 * Math.sin(t * 40), 0, 0], head: [-0.4, 0, 0] })
          else if (t < LAUNCH) pose(bro, POSES.bicepHeart)
          else pose(bro, { armR: [0, 0, -2.6 + Math.sin(t * 30)], armL: [0, 0, 2.6 - Math.sin(t * 30)] })
        } else if (t < STAR) {
          const k = progress(t, 6, STAR)
          bro.root.position.set(-8 + k * 22, SPACE - 8 + k * 22, 6 - k * 42)
          bro.root.rotation.set(t * 6, t * 3, 0)
          bro.root.scale.setScalar(1 - 0.85 * k)
        } else bro.root.visible = false
        star.visible = t >= STAR
        star.scale.setScalar((3 + Math.sin(t * 20)) * ease.outBack(progress(t, STAR, STAR + 0.3)))

        // The heart at his chest and the aura behind him
        love.visible = t >= 2.75 && t < PASS
        love.position.set(DRIVERS.bro + 0.35, 1.75, 0.55)
        love.rotation.y = Math.sin(t * 3) * 0.3
        love.scale.setScalar(0.32 * pop(t, 2.75, 0.3) * (1 + 0.08 * Math.sin(t * 12)))
        aura.visible = t >= 2.9 && t < PASS
        aura.position.set(DRIVERS.bro, 1.6, -0.6)
        aura.scale.setScalar((4.5 + 0.4 * Math.sin(t * 7)) * ease.outCubic(progress(t, 2.9, 3.3)))

        // His sunglasses fall into the crater; his shake flies off to the side
        const tau = Math.max(0, t - LAUNCH)
        shades.visible = t >= LAUNCH
        const shadesLand = fallTime(2.12 - 0.13, 3)
        const shadesFall = Math.min(tau, shadesLand)
        shades.position.set(
          0.15 * shadesFall,
          Math.max(0.13, 2.12 + 3 * shadesFall - 4.9 * shadesFall * shadesFall),
          0.27 + 0.4 * shadesFall,
        )
        shades.rotation.set(tau < shadesLand ? tau * 9 : Math.PI / 2, 0.3, 0)
        flyingShake.visible = t >= LAUNCH
        const shakeLand = fallTime(1.1 - 0.25, 6)
        const shakeFlight = Math.min(tau, shakeLand)
        flyingShake.position.set(
          0.55 + 2.5 * shakeFlight,
          Math.max(0.25, 1.1 + 6 * shakeFlight - 4.9 * shakeFlight * shakeFlight),
          0.2 + 1.2 * shakeFlight,
        )
        flyingShake.rotation.set(tau < shakeLand ? tau * 11 : Math.PI / 2, 0, tau < shakeLand ? tau * 7 : 0.4)
        crater.visible = t >= LAUNCH
        crater.scale.setScalar(ease.outBack(progress(t, LAUNCH, LAUNCH + 0.25)))
        smoke.forEach((puff, i) => {
          const life = (Math.max(0, t - LAUNCH) * 0.6 + i / smoke.length) % 1
          puff.visible = t >= LAUNCH + 0.2
          puff.position.set(0.1 + Math.sin(i * 2 + t) * 0.2, 0.25 + life * 1.6, 0.25)
          puff.scale.setScalar(0.4 + life * 0.9)
          puff.material.opacity = 0.55 * (1 - life)
        })
        dust.update(t)

        // The scared driver: phone, a flinch, looks up, then presses ACCEPT and trembles
        const fright = 0.25 * Math.sin(Math.PI * progress(t, PASS, PASS + 0.3))
        if (t < 8)
          pose(scared, { ...POSES.phone, lift: fright, head: t > PASS + 0.2 ? [-0.9, 0, 0] : POSES.phone.head })
        else {
          const tap = PRESSES.some((when) => t >= when && t < when + 0.15) ? 0.3 : 0
          pose(scared, { ...POSES.phone, armL: [-1.05 + tap, 0, -0.25], lift: Math.sin(t * 60) * 0.012 })
        }

        // Our car at light speed, its trail and the boom
        const cx = (t - PASS) * 320
        ours.root.visible = Math.abs(cx) < 90
        ours.root.position.set(cx, 0.1, LANE_Z)
        ours.spin(cx)
        trail.visible = t >= PASS - 0.15 && t < PASS + 0.6
        trailMaterial.opacity = 0.85 * (1 - progress(t, PASS, PASS + 0.6))
        ring.update(t, PASS, 0.6, 16)

        // The camera
        let position
        let target
        if (t < 1.8) {
          const k = ease.inOutQuad(progress(t, 0, 1.8))
          position = mixed([0, 2.0, 10.5], [0, 1.95, 9.2], k)
          target = [0, 1.4, 0]
        } else if (t < 2.6) {
          position = [0.2, 2.0, 3.0]
          target = [0, 1.85, 0]
        } else if (t < PASS) {
          const k = progress(t, 2.6, PASS)
          position = [0.6 - 0.2 * k, 0.9, 3.4 - 0.4 * k]
          target = [0, 2.0, 0]
        } else if (t < 6) {
          position = [0, 1.4, 9.5]
          target = [0, 1.6 + height * 0.6, 0]
        } else if (t < 8) {
          position = [0, SPACE + 2, 16]
          target = [5, SPACE + 5, -12]
        } else if (t < 8.9) {
          position = [0.4, 1.3, 5.2]
          target = [0, 0.6, 0]
        } else {
          position = [1.6, 1.75, 2.9]
          target = [DRIVERS.scared, 1.55, 0]
        }
        const [sx, sy, sz] = shake(t, PASS, 0.6, 0.3)
        camera.position.set(position[0] + sx, position[1] + sy, position[2] + sz)
        camera.lookAt(...target)
      },
      overlay(g, t) {
        banner(g, t, lines.offer, { t0: 0.25, t1: 1.8, y: 430 })
        if (t >= 0.3 && t < 1.2) {
          for (const ch of [npc, bro, scared]) {
            ch.head.getWorldPosition(spot)
            spot.y += 1.1
            const [x, y] = toScreen(spot, camera)
            outlined(g, lines.ding, x, y, 46 * pop(t, 0.3, 0.2), { fill: '#ffe14d', line: 8 })
          }
        }
        if (t >= 1.0 && t < 1.8) {
          npc.head.getWorldPosition(spot)
          const [x, y] = toScreen(spot, camera)
          caption(g, t, lines.accepted, {
            t0: 1.0,
            t1: 1.8,
            x: Math.max(220, x),
            y: y + 150,
            size: 52,
            fill: '#9fe0ff',
          })
        }

        // The gig card on the gym bro's phone, his laugh, DECLINE
        if (t >= 1.8 && t < 2.75) {
          const s = 0.62 * pop(t, 1.8, 0.2) * (1 - ease.inCubic(progress(t, 2.55, 2.75)))
          gigCard(g, t, lines, { scale: s, press: 'decline', times: [2.45] })
        }
        if (t >= 2.0 && t < 2.45) {
          bro.head.getWorldPosition(spot)
          const [x, y] = toScreen(spot, camera)
          for (let i = 0; i < 2; i++) {
            const jitter = Math.sin(t * 50 + i) * 6
            outlined(g, lines.laugh, x + (i ? 210 : -210) + jitter, y - 140 + i * 40, 70, { fill: '#ffffff', line: 10 })
          }
        }
        caption(g, t, lines.nah, { t0: 3.2, t1: PASS, y: 1360, size: 100 })

        speedLines(g, t, t > PASS - 0.2 && t < PASS + 0.4 ? 1 : 0, { seed: 13 })
        flash(g, t >= PASS ? 0.9 * (1 - progress(t, PASS, PASS + 0.35)) : 0)
        flash(g, t >= 5.9 && t < 6.15 ? 1 - Math.abs(t - 6.0) / 0.15 : 0)

        // Space: the scream follows him and fades, then he twinkles
        if (t >= 6.05 && t < STAR) {
          bro.head.getWorldPosition(spot)
          const [, y] = toScreen(spot, camera)
          const k = progress(t, 6.05, STAR)
          outlined(g, lines.scream, 540, y - 120, 130 * (1 - 0.7 * k), {
            fill: '#ffe14d',
            alpha: 1 - k * 0.6,
          })
        }
        if (t >= STAR && t < 8) {
          star.getWorldPosition(spot)
          const [x, y] = toScreen(spot, camera)
          sparkle(g, x, y, 60 + 25 * Math.sin(t * 20), 0.9)
        }
        if (t >= 7 && t < 8) {
          const s = pop(t, 7, 0.25)
          g.save()
          g.translate(540, 1150)
          g.scale(s, s)
          outlined(g, lines.aura, 0, 0, 150, { fill: '#ff3b3b', line: 24 })
          g.restore()
        }
        caption(g, t, lines.didNot, { t0: 7.35, t1: 8, y: 1330, size: 60, italic: true })

        // The scared driver presses ACCEPT again and again, sweating
        if (t >= 8.9) {
          gigCard(g, t, lines, { scale: 0.5 * pop(t, 8.9, 0.15), press: 'accept', times: PRESSES, y: 1290 })
          scared.head.getWorldPosition(spot)
          const [x, y] = toScreen(spot, camera)
          for (let i = 0; i < 3; i++) {
            const k = (t * 1.6 + i / 3) % 1
            g.save()
            g.globalAlpha = 1 - k
            g.fillStyle = '#9fd8ff'
            g.beginPath()
            const dx = x + [-170, 160, 190][i]
            const dy = y - 120 + k * 160
            g.moveTo(dx, dy - 26)
            g.quadraticCurveTo(dx + 18, dy, dx, dy + 14)
            g.quadraticCurveTo(dx - 18, dy, dx, dy - 26)
            g.fill()
            g.restore()
          }
          lines.panic.forEach((word, i) => {
            caption(g, t, word, {
              t0: PRESSES[i],
              t1: 10,
              x: [380, 700, 540][i],
              y: [420, 540, 660][i],
              size: [70, 86, 120][i],
            })
          })
        }
      },
    }
  },
}
