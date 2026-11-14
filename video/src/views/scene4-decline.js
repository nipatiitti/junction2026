import * as THREE from 'three'
import { ease, pop, progress } from '../kit/anim.js'
import { car } from '../kit/car.js'
import { character, POSES, pose } from '../kit/character.js'
import { boomRing, flash, glowSprite, shake, speedLines } from '../kit/fx.js'
import { at, box, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { sign } from '../kit/sign.js'
import { banner, caption, outlined } from '../kit/text.js'
import { building, jitter, lights, pine, sky, snowGround, stars } from '../kit/world.js'

// Scene 4, "Nah, I'd win" (rough set): three gig drivers get our offer; the gym bro declines and is launched into
// space. Beats (local seconds): 0–2 the phones ding, the NPC accepts · 2–4.4 he laughs, bicep heart, "Nah, I'd win." ·
// 4.4 our car passes at light speed and launches him · 6–8 in space: "BOMBOCLAAAT", he becomes a star, −∞ AURA ·
// 8–10 the scared driver accepts again and again.

const SPACE = 800 // the space set floats this high above the parking lot
const PASS = 4.4 // when our car passes

function phoneProp() {
  const handset = at(box(0.13, 0.24, 0.04, '#121214'), 0, -0.05, 0.12)
  handset.rotation.x = 1.2
  return handset
}

export default {
  build(segment) {
    const lines = segment.lines
    const rand = rng(41)
    const scene = new THREE.Scene()
    const fog = new THREE.Fog('#f6a670', 30, 140)
    const black = new THREE.Color('#000004')
    const dome = sky(scene, '#4a2c7a', '#ffa262')
    lights(scene, {
      sun: '#ffb56b',
      sunIntensity: 2.4,
      from: [-30, 9, 14],
      skyColor: '#ffc9a0',
      groundColor: '#6a4a6a',
      fill: 1.0,
      area: 24,
    })
    scene.add(snowGround(rand, { flat: 12 }))

    // The motorway and the truck stop
    scene.add(at(box(240, 0.1, 8, C.asphalt, { shadow: false }), 0, 0.05, 6))
    for (let x = -118; x < 120; x += 6) scene.add(at(box(2.6, 0.02, 0.18, C.line, { shadow: false }), x, 0.11, 6))
    const stop = at(new THREE.Group(), -1, 0, -9)
    stop.add(at(box(15, 0.6, 8, '#eeeeee'), 0, 5.3, 0))
    stop.add(at(box(15.1, 0.25, 8.1, '#d23b2b'), 0, 5.0, 0))
    for (const px of [-6.5, 6.5]) for (const pz of [-3.2, 3.2]) stop.add(at(box(0.35, 5, 0.35, '#dddddd'), px, 2.5, pz))
    for (const px of [-3, 3]) stop.add(at(box(0.9, 1.7, 0.6, '#3d7be0'), px, 0.85, 0))
    stop.add(at(building(rand, { w: 14, h: 4.5, d: 6, color: '#d8d2c4', lit: 0.6 }), 0, 0, -8))
    scene.add(stop)
    for (let n = 0; n < 50; n++) {
      scene.add(at(pine(rand, { height: rand.range(6, 11) }), rand.range(-80, 80), 0, rand.range(-70, -22)))
    }

    // The three drivers
    const npc = character({ shirt: '#8a8f98', pants: '#5a5f68', hood: true, hair: 'none' })
    const bro = character({ shirt: '#f4f4f4', tank: true, skin: C.skinTan, sunglasses: true, pants: '#2d2d2d' })
    const scared = character({ shirt: '#6a8caf', glasses: true, pants: '#4a4a4a' })
    scared.root.scale.setScalar(0.86)
    for (const [ch, x] of [
      [npc, -1.5],
      [bro, 0],
      [scared, 1.5],
    ]) {
      at(ch.root, x, 0.05, 0)
      ch.handR.add(phoneProp())
      scene.add(ch.root)
    }
    bro.handL.add(at(mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.3, 8), '#ff7ab8'), 0, -0.05, 0.08))
    scene.add(at(sign('NPC', { w: 0.9, h: 0.36, bg: '#111111', fg: '#ffffff' }), -1.5, 2.75, 0))

    // Our car and the boom
    const ours = car({ color: C.ourRed, stripe: true })
    scene.add(ours.root)
    const ring = boomRing()
    ring.object.rotation.y = Math.PI / 2
    scene.add(at(ring.object, 0, 1, 5.2))

    // Space, high above
    const space = at(new THREE.Group(), 0, SPACE, 0)
    const earth = at(mesh(jitter(new THREE.IcosahedronGeometry(60, 3), 0.02, 3), '#2f6fd6'), 0, -75, -40)
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
    space.add(star)
    scene.add(space)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.1, 1200)
    let broY = 0
    return {
      scene,
      camera,
      update(t) {
        const inSpace = t >= 6 && t < 8
        scene.fog = inSpace ? null : fog
        scene.background = inSpace ? black : null
        dome.visible = !inSpace

        pose(npc, { ...POSES.phone, armL: [-1.05 + (t > 1 && t < 1.3 ? 0.2 : 0), 0, -0.25] })
        if (t < 2) pose(bro, POSES.phone)
        else if (t < 2.6)
          pose(bro, { ...POSES.phone, torso: [-0.25 + 0.08 * Math.sin(t * 40), 0, 0], head: [-0.4, 0, 0] })
        else pose(bro, POSES.bicepHeart)
        const tau = Math.max(0, t - PASS - 0.05)
        broY = 30 * tau + 12 * tau * tau
        if (t < 6) {
          bro.root.visible = true
          bro.root.position.set(0, 0.05 + broY, 2 * tau)
          bro.root.rotation.set(7 * tau, 0, 0)
          bro.root.scale.setScalar(1)
          if (t > PASS) pose(bro, { armR: [0, 0, -2.6 + Math.sin(t * 30)], armL: [0, 0, 2.6 - Math.sin(t * 30)] })
        } else if (t < 7.3) {
          const k = progress(t, 6, 7.3)
          bro.root.position.set(-8 + k * 22, SPACE - 8 + k * 22, 6 - k * 42)
          bro.root.rotation.set(t * 6, t * 3, 0)
          bro.root.scale.setScalar(1 - 0.85 * k)
        } else bro.root.visible = false
        star.position.set(14, 14, -36)
        star.visible = t >= 7.3
        star.scale.setScalar((3 + Math.sin(t * 20)) * ease.outBack(progress(t, 7.3, 7.6)))
        satellite.rotation.set(t * 0.3, t * 0.5, 0)

        const fright = 0.25 * Math.sin(Math.PI * progress(t, PASS, PASS + 0.3))
        if (t < 8)
          pose(scared, { ...POSES.phone, lift: fright, head: t > PASS + 0.2 ? [-0.9, 0, 0] : POSES.phone.head })
        else
          pose(scared, {
            ...POSES.phone,
            armL: [-1.05 + 0.25 * Math.abs(Math.sin(t * 18)), 0, -0.25],
            lift: Math.sin(t * 60) * 0.01,
          })

        const cx = (t - PASS) * 320
        ours.root.visible = Math.abs(cx) < 90
        ours.root.position.set(cx, 0.1, 5.2)
        ours.spin(cx)
        ring.update(t, PASS, 0.6, 16)

        let position
        let target
        if (t < 2)
          [position, target] = [
            [0, 1.9, 10.5],
            [0, 1.35, 0],
          ]
        else if (t < PASS)
          [position, target] = [
            [0.15, 2.05, 3.3],
            [0, 1.85, 0],
          ]
        else if (t < 6)
          [position, target] = [
            [0, 1.4, 9.5],
            [0, 1.6 + broY * 0.6, 0],
          ]
        else if (t < 8)
          [position, target] = [
            [0, SPACE + 2, 16],
            [2, SPACE + 2, -12],
          ]
        else
          [position, target] = [
            [1.6, 1.75, 2.9],
            [1.5, 1.55, 0],
          ]
        const [sx, sy, sz] = shake(t, PASS, 0.6, 0.3)
        camera.position.set(position[0] + sx, position[1] + sy, position[2] + sz)
        camera.lookAt(...target)
      },
      overlay(g, t) {
        banner(g, t, lines.offer, { t0: 0.25, t1: 2.0, y: 430 })
        caption(g, t, lines.accepted, { t0: 1.0, t1: 2.0, y: 1300, size: 70, fill: '#9fe0ff' })
        caption(g, t, lines.nah, { t0: 2.5, t1: PASS, y: 1320, size: 100 })
        if (t >= 2.9 && t < PASS)
          outlined(g, '♥', 610, 1010, 150 * (1 + 0.1 * Math.sin(t * 12)), { fill: '#ff2d55', line: 14 })
        speedLines(g, t, t > PASS - 0.2 && t < PASS + 0.4 ? 1 : 0, { seed: 13 })
        flash(g, t >= PASS ? 0.9 * (1 - progress(t, PASS, PASS + 0.35)) : 0)
        if (t >= 6.05 && t < 7.5) {
          const k = progress(t, 6.05, 7.5)
          outlined(g, lines.scream, 540, 760 - k * 200, 130 * (1 - 0.65 * k), { fill: '#ffe14d', alpha: 1 - k * 0.5 })
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
        lines.panic.forEach((word, i) => {
          caption(g, t, word, {
            t0: 8.2 + i * 0.45,
            t1: 10,
            x: [380, 700, 540][i],
            y: [1080, 1230, 1400][i],
            size: [70, 86, 120][i],
          })
        })
      },
    }
  },
}
