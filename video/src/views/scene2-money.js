import * as THREE from 'three'
import { ease, lerp, pop, progress, track } from '../kit/anim.js'
import { character, POSES, pose } from '../kit/character.js'
import { burst, flash, shake } from '../kit/fx.js'
import { at, box, glow, mat, mesh } from '../kit/materials.js'
import { C } from '../kit/palette.js'
import { noise, rng } from '../kit/rng.js'
import { liveTexture, sign } from '../kit/sign.js'
import { caption, FONT, liveChat, outlined, toScreen, UI } from '../kit/text.js'
import { jitter, lights } from '../kit/world.js'
import { NUMBERS } from '../timeline.js'

// Scene 2, "Money printer": hour 31 of the hackathon. One slow Enter turns the starter's loss into our margin, the
// laptop starts printing notes, and the money fills the hall. The texts are in timeline.js.
// Beats (local seconds):
//   0–1.8     over his shoulder: the loss in red on the screen, the team asleep around him
//   1.8–2.95  slow motion: he lifts one finger… and slams Enter at 2.95
//   2.95–3.3  the number spins like a slot machine and lands on our margin; at 3.6 the laptop starts to rumble
//   3.9–7.0   wide: notes shoot out of the laptop, cover the floor and rise; the sleepers float up; "BRRRR"
//   7.0–7.9   through the laptop's webcam: "Chat… is this real?" with the stream chat
//   7.9–8.5   a sleeper floating on the money: "we're so back."

const ENTER = 2.95 // the Enter key hits
const LAND = 3.3 // the number lands on our margin
const RUMBLE = 3.6 // the laptop starts printing
const HALL = { x: 8.3, back: -6.8, front: 12.3 } // the floor that the money covers
const level = (t) => 1.05 * ease.inOutQuad(progress(t, 4.8, 7.2)) // how high the money stands in the hall
const reach = (t) => 15 * ease.outQuad(progress(t, 4.0, 5.3)) // how far from the table the notes cover the floor
const mixed = (a, b, k) => a.map((x, i) => lerp(x, b[i], k))

function spinText(t) {
  const n = (Math.floor(t * 30) * 7919 + 12345) % 99999
  return `€${Math.floor(n / 1000)},${String(n % 1000).padStart(3, '0')}`
}

function screenPainter(label) {
  return (g, state, w, h) => {
    const colour = { loss: '#ff4545', spin: '#ffffff', win: '#3dff7a' }[state.phase]
    g.fillStyle = '#0b0f14'
    g.fillRect(0, 0, w, h)
    // the pixel face: sad on the loss, gasping in the spin, grinning on the win
    g.fillStyle = colour
    g.fillRect(36, 30, 26, 26)
    g.fillRect(96, 30, 26, 26)
    if (state.phase === 'win') {
      g.fillRect(30, 92, 100, 14)
      g.fillRect(20, 78, 14, 14)
      g.fillRect(126, 78, 14, 14)
    } else if (state.phase === 'loss') {
      g.fillRect(36, 84, 88, 14)
      g.fillRect(26, 98, 14, 14)
      g.fillRect(120, 98, 14, 14)
    } else g.fillRect(58, 76, 44, 34)
    g.textAlign = 'center'
    g.textBaseline = 'middle'
    g.fillStyle = '#7f8ea3'
    g.font = `700 30px ${UI}`
    g.fillText(label, w / 2, h * 0.4)
    const text = { loss: NUMBERS.starterLoss, spin: state.spin, win: NUMBERS.ourMargin }[state.phase]
    g.save()
    g.translate(w / 2, h * 0.64)
    g.scale(state.bump, state.bump)
    g.fillStyle = colour
    g.font = `900 92px ${FONT}`
    g.fillText(text, 0, 0)
    g.restore()
    // a small chart that falls on the loss and shoots up on the win
    g.strokeStyle = colour
    g.lineWidth = 6
    g.beginPath()
    for (let i = 0; i <= 12; i++) {
      const k = i / 12
      const x = 40 + k * (w - 80)
      const y = h - 34 - (state.phase === 'win' ? k * k * 70 : (1 - k) * 40 + Math.sin(i * 1.7) * 8)
      if (i === 0) g.moveTo(x, y)
      else g.lineTo(x, y)
    }
    g.stroke()
  }
}

function codeScreen(g, _state, w, h) {
  g.fillStyle = '#0b1a2a'
  g.fillRect(0, 0, w, h)
  const rand = rng(5)
  for (let i = 0; i < 9; i++) {
    g.fillStyle = rand.pick(['#3dff7a', '#6bd5ff', '#ff6b9a', '#ffd36b'])
    g.fillRect(16 + rand() * 30, 14 + i * 16, 60 + rand() * 140, 8)
  }
}

/** Three z's that float up from x, y and fade. */
function snore(g, t, x, y) {
  for (let i = 0; i < 3; i++) {
    const k = (t * 0.8 + i / 3) % 1
    outlined(g, 'z', x + 26 * i + k * 30, y - k * 90, 38 + i * 12, { fill: '#cfe3ff', line: 7, alpha: 1 - k })
  }
}

export default {
  build(segment) {
    const lines = segment.lines
    const rand = rng(21)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#14112a')
    scene.fog = new THREE.Fog('#14112a', 18, 55)
    lights(scene, {
      skyColor: '#8a7cff',
      groundColor: '#2a2240',
      fill: 1.3,
      sun: '#d9ceff',
      sunIntensity: 1.4,
      from: [4, 12, 10],
      area: 14,
    })
    const pink = at(new THREE.PointLight('#ff3ea5', 80, 20), -6, 4.5, -2)
    const cyan = at(new THREE.PointLight('#2ff3ff', 80, 20), 6, 4.5, -2)
    const screenLight = at(new THREE.PointLight('#ff6b6b', 2.5, 2.5), 0, 1.42, -0.4)
    const warm = at(new THREE.PointLight('#ffe0c0', 5, 6), 1.2, 2.8, -1.2)
    scene.add(pink, cyan, screenLight, warm)

    // The hall: walls, LED strips, the HOUR sign and a banner
    scene.add(at(box(40, 0.2, 40, '#33304a', { shadow: false }), 0, -0.1, 2))
    scene.add(at(box(17.8, 9, 0.4, '#1d1a30'), 0, 4.5, -7))
    scene.add(at(box(17.8, 9, 0.4, '#1d1a30'), 0, 4.5, 12.6))
    for (const side of [-1, 1]) scene.add(at(box(0.4, 9, 20, '#1d1a30'), side * 8.9, 4.5, 2.8))
    const led = new THREE.MeshBasicMaterial({ color: '#ff3ea5', toneMapped: false })
    for (const z of [-6.75, 12.35]) scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(17, 0.14, 0.1), led), 0, 6, z))
    for (const side of [-1, 1])
      scene.add(at(new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.14, 19), led), side * 8.65, 6, 2.8))
    scene.add(at(sign(lines.hour, { w: 4.4, h: 1.2, bg: '#120a1e', fg: '#ff3ea5', neon: true }), -3.8, 3.3, -6.78))
    scene.add(at(sign(lines.banner, { w: 4.4, h: 1.2, bg: '#2b1d5c', fg: '#ffffff' }), 3.8, 3.3, -6.78))
    const exit = at(sign('EXIT', { w: 1.2, h: 0.45, bg: '#0a3d1a', fg: '#4dff88', neon: true }), 5.5, 3, 12.38)
    exit.rotation.y = Math.PI
    scene.add(exit)

    // The main table: laptop, chair, pizza boxes, an energy drink and the can pyramid
    scene.add(at(box(3.4, 0.1, 1.5, '#d9d4c7'), 0, 1.0, -0.2))
    for (const x of [-1.55, 1.55])
      for (const z of [-0.85, 0.45]) scene.add(at(box(0.08, 1.0, 0.08, C.metal), x, 0.5, z))
    scene.add(at(box(0.7, 0.08, 0.7, '#3b3f46'), 0, 0.56, 1.25))
    scene.add(
      at(box(0.7, 0.07, 0.7, '#e3c48d'), -1.0, 1.09, -0.3),
      at(box(0.7, 0.07, 0.7, '#d9b77a'), -0.95, 1.16, -0.25),
    )
    scene.add(at(mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.24, 8), '#1f8fff'), -0.62, 1.17, 0.3))
    const laptop = at(new THREE.Group(), 0, 1.05, -0.15)
    laptop.add(at(box(0.95, 0.05, 0.65, '#c3c7cf'), 0, 0.025, 0))
    const enterKey = at(box(0.12, 0.006, 0.08, glow('#3dff7a'), { shadow: false }), 0.28, 0.053, 0.12)
    laptop.add(enterKey)
    const lid = at(new THREE.Group(), 0, 0.05, -0.3)
    lid.rotation.x = -0.22
    lid.add(at(box(0.95, 0.64, 0.04, '#c3c7cf'), 0, 0.32, 0))
    const screen = liveTexture(640, 420, screenPainter(lines.screenLabel))
    const face = new THREE.MeshBasicMaterial({ map: screen.texture, toneMapped: false })
    lid.add(at(new THREE.Mesh(new THREE.PlaneGeometry(0.86, 0.56), face), 0, 0.32, 0.021))
    laptop.add(lid)
    scene.add(laptop)
    const cans = []
    const canShape = new THREE.CylinderGeometry(0.07, 0.07, 0.24, 8)
    for (let row = 0; row < 4; row++) {
      for (let i = 0; i < 4 - row; i++) {
        const can = mesh(canShape, ['#c0c6cc', '#1f8fff', '#ff4f8b'][(row + i) % 3])
        const home = [1.05 + i * 0.15 + row * 0.075, 1.17 + row * 0.24, -0.4]
        cans.push({
          can,
          home,
          delay: rand() * 0.3 + (3 - row) * 0.06,
          vx: rand.range(0.5, 2),
          vz: rand.range(0.5, 2.5),
        })
        scene.add(can)
      }
    }

    // Two desks at the back, one with a teammate asleep on it
    const code = liveTexture(256, 160, codeScreen)
    code.set({})
    for (const side of [-1, 1]) {
      const desk = at(new THREE.Group(), side * 4.4, 0, -4.6)
      desk.add(at(box(2.6, 0.1, 1.2, '#cfc9bb'), 0, 1.0, 0))
      for (const lx of [-1.2, 1.2])
        for (const lz of [-0.5, 0.5]) desk.add(at(box(0.07, 1.0, 0.07, C.metal), lx, 0.5, lz))
      desk.add(at(box(1.3, 0.8, 0.06, '#222228'), 0, 1.55, -0.35))
      const monitor = new THREE.MeshBasicMaterial({ map: code.texture, toneMapped: false })
      desk.add(at(new THREE.Mesh(new THREE.PlaneGeometry(1.18, 0.68), monitor), 0, 1.55, -0.315))
      desk.add(at(box(0.6, 0.08, 0.6, '#3b3f46'), 0, 0.56, 0.9))
      scene.add(desk)
    }
    const slumped = character({ shirt: '#2e8b57', hood: true })
    slumped.root.rotation.y = Math.PI
    pose(slumped, {
      ...POSES.sit,
      torso: [1.1, 0, 0],
      head: [0.3, 0, 0],
      armL: [-1.4, 0, -0.25],
      armR: [-1.4, 0, 0.25],
    })
    slumped.eyes.scale.y = 0.2
    scene.add(at(slumped.root, 4.4, -0.32, -3.7))

    // The developer, and two teammates asleep in beanbags
    const dev = character({ shirt: C.hoodieRed, hood: true, tired: true })
    dev.root.rotation.y = Math.PI
    scene.add(at(dev.root, 0, -0.32, 1.25))
    const sleepers = []
    for (const [x, z, bag, shirt] of [
      [-3.3, 0.6, '#ff8a3d', '#2b7de9'],
      [3.2, 1.6, '#2b7de9', '#6a4c93'],
    ]) {
      const holder = at(new THREE.Group(), x, 0, z)
      const beanbag = mesh(jitter(new THREE.IcosahedronGeometry(1, 1), 0.25, x), bag)
      beanbag.scale.set(1, 0.5, 1)
      holder.add(at(beanbag, 0, 0.45, 0))
      const sleeper = character({ shirt, hood: true })
      sleeper.root.rotation.x = -1.15
      sleeper.eyes.scale.y = 0.2
      pose(sleeper, {
        armL: [0.3, 0, 0.4],
        armR: [0.3, 0, -0.4],
        head: [0.3, 0, 0.2],
        legL: [-0.4, 0, 0],
        legR: [-0.4, 0, 0],
      })
      holder.add(at(sleeper.root, 0, 0.55, 0.25))
      scene.add(holder)
      sleepers.push({ holder, sleeper })
    }

    // The money: a fountain from the laptop, and a sea that covers the floor and rises
    const fountain = burst(rng(22), {
      count: 1500,
      origin: (_when, r) => [r.range(-0.35, 0.35), 1.72, -0.48],
      start: RUMBLE,
      spread: 2.8,
      speed: [0.6, 3.2],
      up: [4.5, 9],
      floor: 0.02,
      geometry: new THREE.BoxGeometry(0.34, 0.012, 0.17),
      material: mat('#ffffff'),
      colors: ['#6fbf73', '#8fd694', '#5aa65e'],
      flat: true,
    })
    scene.add(fountain.object)
    const sea = mesh(new THREE.BoxGeometry(1, 1, 1), '#5fae63', { shadow: false })
    sea.scale.set(HALL.x * 2, 0.001, HALL.front - HALL.back)
    sea.position.z = (HALL.front + HALL.back) / 2
    scene.add(sea)
    const carpetCount = 3200
    const carpet = new THREE.InstancedMesh(new THREE.BoxGeometry(0.46, 0.012, 0.23), mat('#ffffff'), carpetCount)
    carpet.frustumCulled = false
    const notes = []
    const noteRand = rng(23)
    const colour = new THREE.Color()
    for (let i = 0; i < carpetCount; i++) {
      const x = noteRand.range(-HALL.x, HALL.x)
      const z = noteRand.range(HALL.back, HALL.front)
      notes.push({
        x,
        z,
        distance: Math.hypot(x, z + 0.15),
        lift: noteRand() * 0.03,
        turn: noteRand() * Math.PI,
        tilt: [noteRand.range(-0.15, 0.15), noteRand.range(-0.15, 0.15)],
      })
      carpet.setColorAt(i, colour.set(noteRand.pick(['#6fbf73', '#8fd694', '#5aa65e', '#7cc47f'])))
    }
    scene.add(carpet)

    const camera = new THREE.PerspectiveCamera(50, 9 / 16, 0.05, 200)
    const dummy = new THREE.Object3D()
    const spot = new THREE.Vector3()
    return {
      scene,
      camera,
      update(t) {
        // The screen, its glow, the Enter key and the lights
        const phase = t < ENTER ? 'loss' : t < LAND ? 'spin' : 'win'
        const bump = 1 + 0.25 * (t >= LAND ? 1 - progress(t, LAND, LAND + 0.25) : 0)
        screen.set({ phase, spin: phase === 'spin' ? spinText(t) : '', bump: Math.round(bump * 100) / 100 })
        screenLight.color.set({ loss: '#ff6b6b', spin: '#ffffff', win: '#4dff88' }[phase])
        screenLight.intensity = t >= LAND ? 3.5 : 2.5
        enterKey.visible = t >= ENTER && t < ENTER + 0.4
        led.color.setHSL((0.1 * t + 0.35 * Math.max(0, t - LAND)) % 1, 1, 0.55)
        const party = t >= LAND ? 1 : 0
        pink.intensity = 80 + 40 * party * Math.sin(t * 8)
        cyan.intensity = 80 + 40 * party * Math.cos(t * 8)

        // The laptop rumbles while it prints
        const rumble = progress(t, RUMBLE, RUMBLE + 0.2) * (1 - progress(t, 7.0, 7.2))
        laptop.position.set(
          noise(t * 45, 3) * 0.015 * rumble,
          1.05 + Math.abs(noise(t * 45, 9)) * 0.012 * rumble,
          -0.15,
        )
        lid.rotation.x = -0.22 + noise(t * 40, 5) * 0.03 * rumble

        // The developer: types, lifts one finger, slams Enter, leans back, cheers, talks to chat
        let angles
        if (t < 1.8) {
          angles = {
            torso: [0.12, 0, 0],
            head: [0.3, 0, 0],
            armL: [-1.25, 0, -0.15],
            armR: [-1.25 + 0.05 * Math.sin(t * 25), 0, 0.15],
          }
        } else if (t < ENTER + 0.35) {
          angles = {
            torso: [0.05, 0, 0],
            armL: [-1.25, 0, -0.15],
            armR: track(t, [
              [1.8, [-1.25, 0, 0.15]],
              [2.6, [-2.7, 0, 0.2]],
              [2.82, [-2.75, 0, 0.2]],
              [ENTER, [-1.15, 0, 0.15], 'inQuad'],
            ]),
          }
        } else if (t < 3.9) {
          angles = {
            torso: [-0.25 * ease.outBack(progress(t, LAND, LAND + 0.3)), 0, 0],
            head: [-0.1, 0, 0],
            armL: [-1.15, 0, -0.15],
            armR: [-1.15, 0, 0.15],
          }
        } else if (t < 7) {
          const wave = Math.sin(t * 12) * 0.2
          angles = {
            torso: [-0.2, 0, Math.sin(t * 6) * 0.08],
            head: [-0.25, 0, 0],
            armR: [0, 0, -2.7 - wave],
            armL: [0, 0, 2.7 + wave],
          }
        } else angles = { torso: [0.1, 0, 0], head: [-0.15, 0, 0.12], armR: [-1.6, 0, 0.3], armL: [-1.2, 0, -0.2] }
        pose(dev, { ...POSES.sit, ...angles })
        dev.eyes.scale.y = t >= 7 && t < 7.9 ? 1.6 : 1

        // The cans fall when the rumble starts
        for (const { can, home, delay, vx, vz } of cans) {
          const tau = Math.max(0, t - RUMBLE - 0.15 - delay)
          can.position.set(home[0] + vx * tau, Math.max(0.07, home[1] - 4.9 * tau * tau), home[2] + vz * tau)
          can.rotation.set(vz * tau * 3, 0, -vx * tau * 3)
        }

        // The money
        fountain.update(t)
        const depth = level(t)
        const covered = reach(t)
        sea.visible = depth > 0.002
        sea.scale.y = Math.max(depth, 0.001)
        sea.position.y = depth / 2
        for (let i = 0; i < carpetCount; i++) {
          const note = notes[i]
          dummy.position.set(note.x, depth + 0.008 + note.lift, note.z)
          dummy.rotation.set(note.tilt[0], note.turn, note.tilt[1])
          dummy.scale.setScalar(note.distance < covered ? 1 : 0)
          dummy.updateMatrix()
          carpet.setMatrixAt(i, dummy.matrix)
        }
        carpet.instanceMatrix.needsUpdate = true
        const afloat = progress(t, 4.8, 5.5)
        for (const [i, { holder }] of sleepers.entries()) {
          holder.position.y = Math.max(0, depth - 0.08) + Math.sin(t * 2 + i) * 0.05 * afloat
          holder.rotation.z = Math.sin(t * 1.5 + i) * 0.06 * afloat
        }

        // The camera
        let position
        let target
        let fov = 50
        if (t < 1.8) {
          const k = ease.inOutQuad(progress(t, 0, 1.8))
          position = mixed([2.8, 2.9, 5.4], [0.8, 1.8, 1.65], k)
          target = mixed([0, 1.55, -0.6], [0, 1.42, -0.52], k)
        } else if (t < ENTER) {
          // low, beside the laptop, looking up at the finger
          const k = progress(t, 1.8, ENTER)
          position = [1.0 - 0.1 * k, 1.35, -0.75 + 0.15 * k]
          target = [0.25, 1.8, 1.0]
        } else if (t < 3.9) {
          position = [0, 1.45, 0.95 - 0.12 * progress(t, ENTER, 3.9)]
          target = [0, 1.41, -0.52]
          fov = 62
        } else if (t < 7) {
          const k = ease.inOutQuad(progress(t, 3.9, 7))
          position = mixed([0.4, 4.6, 10.8], [1.2, 6.8, 12.0], k)
          target = mixed([0, 1.3, -0.5], [0, 0.9, -1.2], k)
        } else if (t < 7.9) {
          // the laptop's webcam
          position = [0, 1.88, -0.6]
          target = [0, 1.5, 1.25]
          fov = 64
        } else {
          // close on the first sleeper's face, floating on the money
          const { holder, sleeper } = sleepers[0]
          holder.updateMatrixWorld(true)
          sleeper.head.getWorldPosition(spot)
          position = [spot.x + 0.9, spot.y + 1.0, spot.z + 1.6]
          target = [spot.x, spot.y + 0.2, spot.z]
        }
        const hit = shake(t, ENTER, 0.3, 0.05)
        const land = shake(t, LAND, 0.4, 0.07, { seed: 4 })
        const roar = t >= 3.9 && t < 7 ? 0.04 : 0
        camera.position.set(
          position[0] + hit[0] + land[0] + noise(t * 30, 1) * roar,
          position[1] + hit[1] + land[1] + noise(t * 30, 2) * roar,
          position[2] + hit[2] + land[2],
        )
        camera.lookAt(...target)
        if (camera.fov !== fov) {
          camera.fov = fov
          camera.updateProjectionMatrix()
        }
      },
      overlay(g, t) {
        if (t < 1.8 || t >= 7.9) {
          for (const [i, { sleeper }] of sleepers.entries()) {
            sleeper.head.getWorldPosition(spot)
            spot.y += 0.5
            const [x, y] = toScreen(spot, camera)
            if (x > 0 && x < 1000 && y > 320 && y < 1480) snore(g, t + i * 0.4, x, y)
          }
        }
        flash(g, t >= ENTER ? 0.35 * (1 - progress(t, ENTER, ENTER + 0.2)) : 0)
        flash(g, t >= LAND ? 0.55 * (1 - progress(t, LAND, LAND + 0.3)) : 0, '160,255,190')
        if (t >= RUMBLE + 0.1 && t < 5.9) {
          const shown = lines.brrr.slice(
            0,
            Math.max(1, Math.ceil(lines.brrr.length * progress(t, RUMBLE + 0.1, RUMBLE + 1))),
          )
          const s = pop(t, RUMBLE + 0.1, 0.2)
          g.save()
          g.translate(540 + noise(t * 40, 2) * 12, 560 + noise(t * 40, 6) * 12)
          g.rotate(-0.06)
          g.scale(s, s)
          outlined(g, shown, 0, 0, 120, { fill: '#7dff9a', line: 20, alpha: 1 - progress(t, 5.6, 5.9) })
          g.restore()
        }
        liveChat(g, t, lines.feed, { t0: 7.0, t1: 7.9, every: 0.11, viewers: lines.viewers })
        caption(g, t, lines.chat, { t0: 7.1, t1: 7.9, y: 1010, size: 84 })
        caption(g, t, lines.back, { t0: 7.95, t1: 8.5, y: 1250, size: 76, italic: true, fill: '#cfe3ff' })
      },
    }
  },
}
