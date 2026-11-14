import * as THREE from 'three'
import { progress, track } from '../kit/anim.js'
import { character, POSES, pose } from '../kit/character.js'
import { burst, flash } from '../kit/fx.js'
import { at, box, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { rng } from '../kit/rng.js'
import { liveTexture } from '../kit/sign.js'
import { caption, FONT, UI } from '../kit/text.js'
import { jitter, lights } from '../kit/world.js'
import { NUMBERS } from '../timeline.js'

// Scene 2, "Money printer" (rough set): hour 31 of the hackathon. The laptop turns the starter's loss into our
// margin and prints euro notes until the hall is full.
// Beats (local seconds): 0–2 the loss on the screen · 2–2.95 a slow Enter · 3–3.4 the number spins and flips ·
// 4–7 notes fill the hall, the sleepers float up, the cans fall · 7–8.5 "Chat… is this real?", "we're so back."

function drawScreen(g, state, w, h) {
  g.fillStyle = '#0b0f14'
  g.fillRect(0, 0, w, h)
  const win = state.phase === 'win'
  g.fillStyle = win ? '#3dff7a' : '#9fb3c8'
  g.fillRect(40, 40, 22, 22)
  g.fillRect(90, 40, 22, 22)
  if (win) {
    g.fillRect(36, 84, 80, 12)
    g.fillRect(28, 72, 12, 14)
    g.fillRect(112, 72, 12, 14)
  } else g.fillRect(40, 84, 72, 12)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = '#7f8ea3'
  g.font = `700 30px ${UI}`
  g.fillText('MARGIN / WEEK', w / 2, h * 0.36)
  const colours = { loss: '#ff4545', spin: '#ffffff', win: '#3dff7a' }
  const texts = { loss: NUMBERS.starterLoss, spin: state.spin, win: NUMBERS.ourMargin }
  g.fillStyle = colours[state.phase]
  g.font = `900 92px ${FONT}`
  g.fillText(texts[state.phase], w / 2, h * 0.62)
}

export default {
  build(segment) {
    const lines = segment.lines
    const rand = rng(21)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0c0a18')
    scene.fog = new THREE.Fog('#0c0a18', 12, 40)
    lights(scene, {
      skyColor: '#6a5acd',
      groundColor: '#1b1530',
      fill: 0.9,
      sun: '#c9b8ff',
      sunIntensity: 1.1,
      from: [5, 12, 9],
      area: 12,
    })
    scene.add(
      at(new THREE.PointLight('#ff3ea5', 40, 16), -5, 4, -3),
      at(new THREE.PointLight('#2ff3ff', 40, 16), 5, 4, -3),
    )

    // The hall
    scene.add(at(box(40, 0.2, 40, '#2a2740', { shadow: false }), 0, -0.1, 0))
    scene.add(at(box(40, 9, 0.4, '#18152a'), 0, 4.5, -7))
    const led = new THREE.MeshBasicMaterial({ color: '#ff3ea5', toneMapped: false })
    scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(36, 0.14, 0.1), led), 0, 6, -6.75))
    scene.add(at(box(3.4, 0.1, 1.5, '#d9d4c7'), 0, 1.0, -0.2))
    for (const x of [-1.55, 1.55])
      for (const z of [-0.85, 0.45]) scene.add(at(box(0.08, 1.0, 0.08, C.metal), x, 0.5, z))
    scene.add(at(box(0.7, 0.08, 0.7, '#3b3f46'), 0, 0.56, 1.25))
    scene.add(
      at(box(0.7, 0.07, 0.7, '#e3c48d'), -1.0, 1.09, -0.3),
      at(box(0.7, 0.07, 0.7, '#d9b77a'), -0.95, 1.16, -0.25),
    )

    // The laptop and its screen
    const laptop = at(new THREE.Group(), 0, 1.05, -0.15)
    laptop.add(at(box(0.95, 0.05, 0.65, '#c3c7cf'), 0, 0.025, 0))
    const lid = at(new THREE.Group(), 0, 0.05, -0.3)
    lid.rotation.x = -0.22
    lid.add(at(box(0.95, 0.64, 0.04, '#c3c7cf'), 0, 0.32, 0))
    const screen = liveTexture(640, 420, drawScreen)
    const material = new THREE.MeshBasicMaterial({ map: screen.texture, toneMapped: false })
    lid.add(at(new THREE.Mesh(new THREE.PlaneGeometry(0.86, 0.56), material), 0, 0.32, 0.021))
    laptop.add(lid)
    scene.add(laptop)

    // The developer and the sleepers
    const dev = character({ shirt: C.hoodieRed, hood: true })
    dev.root.rotation.y = Math.PI
    scene.add(at(dev.root, 0, -0.32, 1.25))
    const sleepers = []
    for (const [x, z, bag, shirt] of [
      [-3.3, 0.6, '#ff8a3d', '#2b7de9'],
      [3.2, 1.3, '#2b7de9', '#6a4c93'],
    ]) {
      const holder = at(new THREE.Group(), x, 0, z)
      const beanbag = mesh(jitter(new THREE.IcosahedronGeometry(1, 1), 0.25, x), bag)
      beanbag.scale.set(1, 0.5, 1)
      holder.add(at(beanbag, 0, 0.45, 0))
      const sleeper = character({ shirt, hood: true })
      sleeper.root.rotation.x = -1.15
      pose(sleeper, {
        armL: [0.3, 0, 0.4],
        armR: [0.3, 0, -0.4],
        head: [0.3, 0, 0.2],
        legL: [-0.4, 0, 0],
        legR: [-0.4, 0, 0],
      })
      holder.add(at(sleeper.root, 0, 0.55, 0.25))
      scene.add(holder)
      sleepers.push(holder)
    }

    // The cans, and the money
    const cans = []
    const canShape = new THREE.CylinderGeometry(0.07, 0.07, 0.24, 8)
    for (let row = 0; row < 4; row++) {
      for (let i = 0; i < 4 - row; i++) {
        const can = mesh(canShape, ['#c0c6cc', '#1f8fff', '#ff4f8b'][(row + i) % 3])
        const home = [1.05 + i * 0.15 + row * 0.075, 1.17 + row * 0.24, -0.4]
        cans.push({ can, home, delay: rand() * 0.3 + row * 0.05, vx: rand.range(0.5, 2), vz: rand.range(0.5, 2.5) })
        scene.add(can)
      }
    }
    const money = burst(rng(22), {
      count: 1200,
      origin: (_when, r) => [r.range(-0.3, 0.3), 1.5, -0.1],
      start: 4,
      spread: 3,
      speed: [0.8, 3],
      up: [3, 8],
      floor: 0.02,
      geometry: new THREE.BoxGeometry(0.34, 0.012, 0.17),
      material: mat('#ffffff'),
      colors: ['#6fbf73', '#8fd694', '#5aa65e'],
      flat: true,
    })
    scene.add(money.object)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.05, 200)
    return {
      scene,
      camera,
      update(t) {
        const phase = t < 3 ? 'loss' : t < 3.4 ? 'spin' : 'win'
        screen.set({
          phase,
          spin: phase === 'spin' ? `€${((Math.floor(t * 30) * 7919) % 99999).toLocaleString('en')}` : '',
        })
        led.color.setHSL((t * 0.15) % 1, 1, 0.55)
        pose(dev, {
          ...POSES.sit,
          armL: [-1.25, 0, -0.15],
          armR: track(t, [
            [2.0, [-1.25, 0, 0.15]],
            [2.4, [-2.3, 0, 0.15], 'outQuad'],
            [2.95, [-1.2, 0, 0.15], 'inQuad'],
          ]),
          head: t < 6.9 ? [0.15, 0, 0] : [-0.05, 0, 0],
        })
        for (const [i, holder] of sleepers.entries()) {
          holder.position.y = 1.4 * progress(t, 4.6, 7) + Math.sin(t * 2 + i) * 0.08 * progress(t, 4.6, 5)
        }
        for (const { can, home, delay, vx, vz } of cans) {
          const tau = Math.max(0, t - 5 - delay)
          can.position.set(home[0] + vx * tau, Math.max(0.07, home[1] - 4.9 * tau * tau), home[2] + vz * tau)
          can.rotation.set(vz * tau * 3, 0, -vx * tau * 3)
        }
        money.update(t)

        let position
        let target
        if (t < 2)
          [position, target] = [
            [0, 1.45, 1.0 - t * 0.05],
            [0, 1.41, -0.52],
          ]
        else if (t < 3)
          [position, target] = [
            [0.95, 1.95, 2.3],
            [0, 1.15, 0.2],
          ]
        else if (t < 4)
          [position, target] = [
            [0, 1.45, 0.95],
            [0, 1.41, -0.52],
          ]
        else if (t < 7) {
          const k = progress(t, 4, 7)
          ;[position, target] = [
            [Math.sin(k * 0.6) * 3, 3.6 + k * 0.6, 9.5 - k * 1.2],
            [0, 1.6, 0],
          ]
        } else
          [position, target] = [
            [0.25, 1.95, -1.1],
            [0, 1.62, 1.25],
          ]
        camera.position.set(...position)
        camera.lookAt(...target)
      },
      overlay(g, t) {
        flash(g, t >= 3.4 ? 0.5 * (1 - progress(t, 3.4, 3.7)) : 0)
        caption(g, t, lines.chat, { t0: 6.95, t1: 8.5, y: 1250, size: 92 })
        caption(g, t, lines.back, { t0: 7.6, t1: 8.5, y: 1420, size: 64, italic: true, fill: '#cfe3ff' })
      },
    }
  },
}
