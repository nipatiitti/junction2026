import * as THREE from 'three'
import { ease, lerp, progress, slowmo, track } from '../kit/anim.js'
import { car } from '../kit/car.js'
import { character, POSES, pose } from '../kit/character.js'
import { boomRing, burst, flash, shake, snowfall, speedLines } from '../kit/fx.js'
import { at, box, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { sign } from '../kit/sign.js'
import { caption, phone } from '../kit/text.js'
import { bunting, lights, pine, pole, sky, snowbank, snowGround } from '../kit/world.js'

// Scene 1, "I am speed": a car dealer gets a price before he finishes typing, then our car blasts past him.
// Beats (local seconds): 0–2 he types · 2.0–2.25 the price tag drops and lands · 3.0 our car comes in ·
// 3.45–4.95 slow motion, the developer leans out: "I am speed." · 4.95 sonic boom · 5.8–8.5 his hair stands up, he
// whispers. The texts are in timeline.js.

const LANE_Z = 2.4 // where the car drives, between the dealer and the camera
const SLOW = [3.45, 4.95, 0.06] // slow motion: from, to, clock rate
const clock = (t) => slowmo(t, ...SLOW)
const carAt = (u) => 120 * (u - 3.5) // x of the car at story time u; it passes x = 0 as the slow motion starts

export default {
  build(segment) {
    const lines = segment.lines
    const rand = rng(11)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog('#dcebf7', 45, 170)
    sky(scene, '#4f97e0', '#e6f3ff')
    lights(scene, { from: [-16, 18, 14], area: 28, sunIntensity: 2.6 })
    scene.add(snowGround(rand, { flat: 24 }))

    // The lot and the dealership
    scene.add(at(box(46, 0.12, 24, C.asphalt, { shadow: false }), 0, 0.06, -5))
    for (let x = -18.9; x <= 19; x += 4.2) scene.add(at(box(0.12, 0.02, 4.6, C.line, { shadow: false }), x, 0.13, -6.8))
    const hall = at(new THREE.Group(), 0, 0, -17)
    hall.add(at(box(26, 6, 9, C.wall), 0, 3, 0))
    hall.add(at(box(19, 3.8, 0.2, C.glass), 0, 2.3, 4.55))
    hall.add(at(box(26.6, 0.5, 9.6, C.roof), 0, 6.25, 0))
    for (const x of [-5, 5]) hall.add(at(box(0.15, 1.6, 0.15, C.metal), x, 7, 3.05))
    hall.add(at(box(12.3, 2.1, 0.2, '#8a1218'), 0, 7.7, 3.05))
    hall.add(at(sign(lines.dealership, { w: 12, h: 1.9, bg: '#c81d25', fg: '#ffffff' }), 0, 7.7, 3.2))
    hall.add(at(sign(lines.banner, { w: 7, h: 1.3, bg: '#f5c518', fg: '#c81d25' }), 0, 4.75, 4.7))
    scene.add(hall)
    const colours = ['#2b7de9', '#f2f2f2', '#1d1f24', '#9aa3ad', '#2e8b57', '#f5c518', '#7b4bb7', '#c0c6cc', '#ff8a3d']
    colours.forEach((colour, i) => {
      const parked = car({ color: colour })
      parked.root.rotation.y = -Math.PI / 2
      scene.add(at(parked.root, -16.8 + i * 4.2, 0.12, -6.8))
    })
    const flags = []
    for (const side of [-1, 1]) {
      scene.add(at(pole(5.2), side * 15, 0, 1))
      flags.push(bunting([side * 13, 6.4, -12.4], [side * 15, 5.1, 1]))
      flags.push(bunting([0, 6.6, -12.4], [side * 15, 5.1, 1], { sag: 1.2 }))
    }
    flags.push(bunting([-13, 6.4, -12.4], [13, 6.4, -12.4], { count: 30, sag: 0.6 }))
    for (const flag of flags) scene.add(flag)

    // Forest and snowbanks around the lot
    for (let n = 0; n < 70; n++) {
      scene.add(at(pine(rand, { height: rand.range(6, 12) }), rand.range(-70, 70), 0, rand.range(-75, -24)))
    }
    for (const side of [-1, 1]) {
      for (let n = 0; n < 14; n++) {
        scene.add(at(pine(rand, { height: rand.range(5, 10) }), side * rand.range(26, 60), 0, rand.range(-24, 14)))
      }
      for (let n = 0; n < 6; n++) {
        const bank = snowbank(rand, { w: rand.range(3, 6), h: rand.range(0.6, 1.2), d: rand.range(2, 3) })
        scene.add(at(bank, side * rand.range(23.5, 25), 0, rand.range(-16, 6)))
      }
    }
    const snow = snowfall(rand, { count: 500, size: [30, 14, 26], speed: 0.6, flake: 0.05 })
    scene.add(snow.object)

    // The dealer, his phone and the price tag
    const dealer = character({
      shirt: C.leather,
      hair: 'mullet',
      hairColor: '#7a5230',
      mustache: true,
      chain: true,
    })
    at(dealer.root, 0.3, 0.12, 0)
    const handset = at(box(0.14, 0.26, 0.04, '#121214'), 0, -0.05, 0.12)
    handset.rotation.x = 1.25
    dealer.handR.add(handset)
    scene.add(dealer.root)
    const tag = new THREE.Group()
    tag.add(at(box(2.0, 1.2, 0.14, '#f5c518'), 0, 0, -0.08))
    tag.add(at(sign(lines.price, { w: 1.8, h: 0.95, bg: '#fff4c2', fg: '#c81d25' }), 0, -0.05, 0))
    tag.add(at(mesh(new THREE.TorusGeometry(0.11, 0.04, 6, 14), '#333333'), -0.78, 0.42, 0.01))
    tag.add(at(box(0.03, 10, 0.03, '#444444'), -0.78, 5.45, 0))
    tag.visible = false
    scene.add(tag)

    // Our car with the developer in it
    const ours = car({ color: C.ourRed, stripe: true })
    const dev = character({ shirt: C.hoodieRed, hood: true, sunglasses: true })
    dev.root.scale.setScalar(0.7)
    dev.root.rotation.y = Math.PI / 2
    ours.seat.add(at(dev.root, 0, -0.09, 0))
    scene.add(ours.root)
    const ring = boomRing()
    ring.object.rotation.y = Math.PI / 2
    scene.add(ring.object)
    const spray = burst(rng(12), {
      count: 500,
      origin: (u, r) => [carAt(u) - 2, 0.3, LANE_Z + r.range(-0.9, 0.9)],
      start: 2.9,
      spread: 1.3,
      dir: [-1, 0, 0.15],
      cone: 1.4,
      speed: [3, 12],
      up: [2, 6],
      floor: 0.15,
      geometry: new THREE.IcosahedronGeometry(0.11, 0),
      material: mat(C.snow),
      clock,
    })
    scene.add(spray.object)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1000)
    const look = new THREE.Vector3()
    const dealerFocus = new THREE.Vector3()
    const carFocus = new THREE.Vector3()

    return {
      scene,
      camera,
      update(t) {
        const u = clock(t)
        snow.update(t)
        for (const flag of flags) flag.update(t)

        // The dealer types, flinches at the tag, looks at it, follows the car, then freezes leaning back
        const bob = Math.sin(t * 28) * 0.05
        pose(dealer, {
          armR:
            t < 2.25
              ? POSES.phone.armR
              : track(t, [
                  [2.25, POSES.phone.armR],
                  [2.4, [-0.3, 0, -2.4], 'outQuad'],
                  [2.9, [-0.45, 0, 0.1]],
                ]),
          armL:
            t < 2.25
              ? [POSES.phone.armL[0] + bob, 0, -0.25]
              : track(t, [
                  [2.25, POSES.phone.armL],
                  [2.4, [-0.3, 0, 2.4], 'outQuad'],
                  [2.9, [0, 0, 0.05]],
                ]),
          head: track(t, [
            [0, POSES.phone.head],
            [2.25, POSES.phone.head],
            [2.4, [-0.15, 0, 0]],
            [2.75, [0.1, -0.55, 0]],
            [3.2, [0.1, -0.55, 0]],
            [3.4, [0, -0.9, 0]],
            [3.5, [0, 0, 0]],
          ]),
          torso: track(t, [
            [4.95, [0, 0, 0]],
            [5.15, [-0.2, 0, 0], 'outBack'],
          ]),
          lift: 0.3 * Math.sin(Math.PI * progress(t, 2.25, 2.55)),
        })
        dealer.mullet.rotation.x =
          t < 4.95 ? 0.5 * progress(t, 3.3, 4.95) : 0.5 + 2.3 * ease.outElastic(progress(t, 4.95, 5.6))
        dealer.eyes.scale.y = 1 + 0.9 * progress(t, 4.95, 5.05)

        // The price tag drops, bounces, and swings when the boom hits it
        tag.visible = t >= 2
        const settle = progress(t, 2.25, 2.7)
        tag.position.set(
          -0.5,
          lerp(13, 1.0, ease.inQuad(progress(t, 2, 2.25))) + Math.sin(settle * Math.PI * 3) * 0.25 * (1 - settle),
          1.7,
        )
        tag.rotation.set(0, t > 4.95 ? -0.6 * ease.outBack(progress(t, 4.95, 5.4)) : 0, 0.08 + Math.sin(t * 2.2) * 0.04)

        // Our car; in the slow motion the developer leans out of the window
        const x = carAt(u)
        ours.root.visible = x > -75 && x < 110
        ours.root.position.set(x, 0.12, LANE_Z)
        ours.spin(x)
        ours.body.rotation.z = t > 4.95 && t < 5.3 ? 0.05 : 0
        const lean = ease.inOutQuad(progress(t, 3.5, 3.85) * (1 - progress(t, 4.75, 4.95)))
        pose(dev, {
          torso: [0, 0, 0.75 * lean],
          head: [0, -1.25 * lean, 0],
          armR: [0, 0, -1.4 * lean],
          ...POSES.sit,
        })
        ring.object.position.set(carAt(clock(4.95)) + 1.5, 0.9, LANE_Z)
        ring.update(t, 4.95, 0.7, 14)
        spray.update(t)

        // Camera: on the dealer, whips to the car and follows it, whips back, then pushes in on his face
        dealerFocus.set(0.3, t < 5.8 ? 1.5 : lerp(1.5, 2.05, progress(t, 5.8, 6.6)), 0)
        carFocus.set(x, 1.1, LANE_Z)
        const follow = ease.inOutQuad(progress(t, 3.05, 3.4)) * (1 - ease.inOutQuad(progress(t, 5.05, 5.7)))
        look.copy(dealerFocus).lerp(carFocus, follow)
        const [cx, cy, cz] = track(t, [
          [0, [0.9, 1.85, 6.6]],
          [2.0, [0.6, 1.75, 5.6]],
          [3.0, [0.6, 1.75, 5.6]],
          [3.4, [1.2, 1.55, 8.4]],
          [4.95, [1.6, 1.5, 7.6]],
          [5.6, [0.5, 1.9, 4.6]],
          [8.5, [0.35, 2.1, 2.5]],
        ])
        const [sx, sy, sz] = shake(t, 2.25, 0.4, 0.12)
        const [bx, by, bz] = shake(t, 4.95, 0.7, 0.3, { seed: 5 })
        camera.position.set(cx + follow * x * 0.3 + sx + bx, cy + sy + by, cz + sz + bz)
        camera.lookAt(look)
      },
      overlay(g, t) {
        if (t < 2.9) {
          const typed = lines.typing.slice(
            0,
            Math.min(lines.typedWhenHit, Math.floor(progress(t, 0.25, 2.25) * lines.typedWhenHit)),
          )
          const cursor = t < 2.25 && Math.floor(t * 4) % 2 === 0 ? '|' : ''
          const rows = [{ text: `${typed}${cursor}` || '|', t0: 0.15, side: 'right', bg: '#2b7de9', fg: '#ffffff' }]
          rows.push({ text: lines.reply, t0: 2.25, side: 'left', bg: '#34c759', fg: '#ffffff' })
          phone(g, t, {
            y: 1180,
            h: 420,
            scale: 0.75 * (1 - ease.inQuad(progress(t, 2.6, 2.9))),
            rows,
            title: 'Customers',
          })
        }
        flash(g, t >= 2.25 ? 0.35 * (1 - progress(t, 2.25, 2.45)) : 0)
        speedLines(
          g,
          t,
          track(t, [
            [3.0, 0],
            [3.25, 0.9],
            [3.45, 0.35],
            [4.95, 0.35],
            [5.05, 1],
            [5.6, 0],
          ]),
          { seed: 5 },
        )
        flash(g, t >= 4.95 ? 0.7 * (1 - progress(t, 4.95, 5.25)) : 0)
        caption(g, t, lines.speed, { t0: 3.7, t1: 4.95, y: 1330, size: 100 })
        caption(g, t, lines.whisper, { t0: 6.6, t1: 8.5, y: 1380, size: 76, italic: true, type: 0.5 })
      },
    }
  },
}
