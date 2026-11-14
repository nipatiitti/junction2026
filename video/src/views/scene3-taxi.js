import * as THREE from 'three'
import { ease, progress, track } from '../kit/anim.js'
import { car } from '../kit/car.js'
import { character, POSES, pose } from '../kit/character.js'
import { burst, flash, snowfall, speedLines } from '../kit/fx.js'
import { at, box, glow, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { sign } from '../kit/sign.js'
import { caption, phone } from '../kit/text.js'
import { building, lamp, lights, pole, sky, snowbank, snowGround } from '../kit/world.js'

// Scene 3, "Taxi is cooked" (rough set): 3 AM in Helsinki. The taxi apps ask over €40, we ask €6.70.
// Beats (local seconds): 0–2.5 the prices on the phone, "Bro…" · 2.5–4.5 €6.70 and the 6-7 hands ·
// 4.5–7 our car drifts in, a snow wave buries the black and green cars, the taxi meter bursts ·
// 7–9 the student gets in ("W chews."), Unc plays a tiny violin, our car drives off.

const STOP_X = 4.4
const carX = (t) =>
  track(t, [
    [4.5, 45],
    [5.5, STOP_X, 'outCubic'],
    [8.0, STOP_X],
    [9.0, -70, 'inQuad'],
  ])

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
      area: 22,
    })
    scene.add(at(new THREE.PointLight('#ff3ea5', 60, 18), 2, 4, -6))
    scene.add(snowGround(rand, { bump: 0.15 }))

    // The street, the kerb, tram rails and the houses
    scene.add(at(box(120, 0.1, 9, C.asphalt, { shadow: false }), 0, 0.05, 0.5))
    scene.add(at(box(120, 0.24, 3.4, '#5b6170'), 0, 0.12, -5.6))
    for (const z of [1.3, 2.7]) scene.add(at(box(120, 0.04, 0.12, '#9aa0aa', { shadow: false }), 0, 0.12, z))
    let x = -46
    while (x < 46) {
      const w = rand.range(7, 10)
      const colour = rand.pick(['#6b5d73', '#4f5d75', '#7a6a58', '#5d6b5e', '#8a7f8f'])
      scene.add(at(building(rand, { w, h: rand.range(9, 17), d: 8, color: colour, lit: 0.45 }), x + w / 2, 0, -11.4))
      x += w + 0.4
    }
    scene.add(at(sign(lines.shop, { w: 6, h: 1.2, bg: '#1a0612', fg: '#ff3ea5', neon: true }), 2, 4.4, -7.3))
    scene.add(at(box(5, 2.2, 0.1, glow('#ffcf7a')), 2, 1.5, -7.36))
    scene.add(at(pole(3.2), -9, 0.24, -4.6))
    scene.add(at(sign('TAXI', { w: 1.2, h: 0.5, bg: C.taxiYellow }), -9, 3.4, -4.55))
    for (const lx of [-14, 6, 20]) scene.add(at(lamp(), lx, 0.24, -4.5))
    const snow = snowfall(rand, { count: 1600, size: [40, 16, 30], speed: 2.2, flake: 0.06 })
    scene.add(snow.object)

    // The cars at the kerb, and the snow that will bury two of them
    const taxi = car({ color: C.taxiYellow, taxi: true })
    scene.add(at(taxi.root, -8.5, 0.1, -3.2))
    const mounds = []
    for (const [mx, colour] of [
      [-13.5, '#15161a'],
      [-18.5, '#2fbf5a'],
    ]) {
      scene.add(at(car({ color: colour }).root, mx, 0.1, -3.2))
      const mound = snowbank(rand, { w: 5.2, h: 2.1, d: 2.8 })
      mounds.push({ mound, base: mound.scale.clone() })
      scene.add(at(mound, mx, 0, -3.2))
    }

    // The student, Unc and his violin
    const student = character({ shirt: '#3c6e71', puffer: true, beanie: '#e8262b', pants: '#2b2b2b', hair: 'none' })
    student.handR.add(at(box(0.13, 0.24, 0.04, '#121214'), 0, -0.05, 0.12))
    student.handL.add(at(mesh(new THREE.CylinderGeometry(0.09, 0.06, 0.34, 7), '#c98b4b'), 0, -0.08, 0.1))
    scene.add(student.root)
    const unc = character({ shirt: '#8a7a5a', pants: '#55575c', hairColor: '#c9ccd1', glasses: true })
    const violin = at(box(0.18, 0.5, 0.08, '#8b4a2b'), 0, -0.05, 0.15)
    unc.handL.add(violin)
    unc.handR.add(at(box(0.02, 0.6, 0.02, '#d9c9a0'), 0, -0.05, 0.15))
    scene.add(unc.root)

    // Our car, the snow wave and the meter confetti
    const ours = car({ color: C.ourRed, stripe: true })
    scene.add(ours.root)
    const wave = burst(rng(32), {
      count: 600,
      origin: (when, r) => [carX(when) + 1.5, 0.2, -1.2 + r.range(-0.8, 0.8)],
      start: 5,
      spread: 0.6,
      dir: [-1, 0, -0.3],
      cone: 0.9,
      speed: [10, 22],
      up: [2, 5],
      floor: 0.12,
      geometry: new THREE.IcosahedronGeometry(0.14, 0),
      material: mat(C.snow),
    })
    const confetti = burst(rng(33), {
      count: 260,
      origin: [-9.2, 1.9, -3.2],
      start: 5.7,
      spread: 0.2,
      speed: [1, 4],
      up: [4, 8],
      floor: 0.12,
      geometry: new THREE.BoxGeometry(0.12, 0.01, 0.08),
      material: mat('#ffffff'),
      colors: ['#ff3ea5', '#f5c518', '#2b7de9', '#2fbf5a', '#ffffff'],
      flat: true,
    })
    scene.add(wave.object, confetti.object)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1000)
    return {
      scene,
      camera,
      update(t) {
        snow.update(t)
        wave.update(t)
        confetti.update(t)
        const cx = carX(t)
        ours.root.visible = cx > -60 && cx < 44
        ours.root.position.set(cx, 0.1, -1.2)
        ours.root.rotation.y =
          Math.PI +
          track(t, [
            [4.5, -0.8],
            [5.3, 0.35, 'outQuad'],
            [5.8, 0, 'outBack'],
          ])
        ours.spin(-cx)
        mounds.forEach(({ mound, base }, i) => {
          const k = ease.outBack(progress(t, 5.45 + i * 0.1, 5.9 + i * 0.1))
          mound.visible = k > 0
          mound.scale.copy(base).multiplyScalar(Math.max(k, 0.001))
        })

        // The student
        const walk = progress(t, 7, 7.6)
        student.root.visible = t < 7.6
        student.root.position.set(1.6 + walk * 1.8, 0.1, -1.6 + walk * 0.9)
        if (t < 2.5) pose(student, { ...POSES.phone, lift: Math.sin(t * 40) * 0.01 })
        else if (t < 4.5) pose(student, POSES.sixSeven(t))
        else pose(student, { armR: [-0.4, 0, 0], armL: [-1.2, 0, -0.2], head: [0, t < 7 ? 0.6 : 0, 0] })

        // Unc stands by his taxi, then sits on the kerb and plays
        if (t < 6.5) {
          unc.root.position.set(-7.2, 0.24, -4.6)
          pose(unc, { armR: [-0.9, 0, 0.6], armL: [-0.9, 0, -0.6], head: [0, 0.4 * progress(t, 4.6, 5.2), 0] })
          violin.visible = false
        } else {
          unc.root.position.set(-4.6, 0.24 - 0.55, -4.15)
          pose(unc, {
            ...POSES.sit,
            armL: [-1.6, 0, -0.5],
            armR: [-1.2 + 0.25 * Math.sin(t * 10), 0, 0.3],
            head: [0.3, 0, 0.2],
          })
          violin.visible = true
        }

        let position
        let target
        if (t < 2.5)
          [position, target] = [
            [2.4, 1.85, 2.4],
            [1.6, 1.75, -1.6],
          ]
        else if (t < 4.5) {
          const a = track(t, [
            [2.5, -0.5],
            [4.5, 0.9],
          ])
          ;[position, target] = [
            [1.6 + Math.sin(a) * 4.3, 1.55, -1.6 + Math.cos(a) * 4.3],
            [1.6, 1.45, -1.6],
          ]
        } else if (t < 7)
          [position, target] = [
            [9, 3.0, 8],
            [-4, 1.0, -2.5],
          ]
        else
          [position, target] = [
            [-2.6, 1.4, 0.4],
            [-4.6, 0.9, -4.15],
          ]
        camera.position.set(...position)
        camera.lookAt(...target)
      },
      overlay(g, t) {
        if (t < 3.4) {
          const rows = lines.prices.map(([who, price], i) => ({ text: `${who}  ${price}`, t0: 0.2 + i * 0.25 }))
          rows.push({ text: `${lines.ours[0]}  ${lines.ours[1]}`, t0: 2.5, bg: C.ourRed, fg: '#ffffff', size: 64 })
          phone(g, t, { y: 1120, scale: 0.72 * (1 - ease.inQuad(progress(t, 3.0, 3.4))), rows, title: lines.clock })
        }
        flash(g, t >= 2.5 ? 0.6 * (1 - progress(t, 2.5, 2.8)) : 0)
        caption(g, t, lines.bro, { t0: 1.5, t1: 2.5, y: 600, size: 80 })
        caption(g, t, lines.sixSeven, { t0: 3.2, t1: 4.45, y: 1320, size: 116 })
        speedLines(
          g,
          t,
          track(t, [
            [4.5, 0],
            [4.7, 0.8],
            [5.5, 0],
          ]),
          { seed: 9 },
        )
        caption(g, t, lines.chews, { t0: 7.2, t1: 8.9, y: 1340, size: 96 })
      },
    }
  },
}
