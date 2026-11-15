import * as THREE from 'three'
import { clamp, ease, lerp, pop, progress, track } from '../../kit/anim.js'
import { pose } from '../../kit/character.js'
import { sparkle } from '../../kit/fx.js'
import { at, box, mat, mesh } from '../../kit/materials.js'
import { rng } from '../../kit/rng.js'
import { liveTexture, sign } from '../../kit/sign.js'
import { outlined, toScreen } from '../../kit/text.js'
import { captions, voiceCues } from '../lines.js'
import { developer, hall } from '../sets.js'
import { SANS } from '../ui.js'

// Joke 1, the hook: four developers tip pots of spaghetti at a wall, in slow motion: 63 strategies, each a bundle of
// thin cooked strands. They slap the wall with a splash of tomato sauce, slide down one by one while a counter on the
// wall runs down, and one sticks: ts:lean, a single strand. The floor is clean until the first ones slide off. The
// texts are in timeline.js. Beats (local seconds):
//   0–1.9    the first frame is already mid-throw; the bundles fly at the wall and slap it from 1.2
//   1.9–5.4  they slide down (the last is on the floor by 6.7); the named ones get an ELIMINATED stamp; the
//            counter runs from 63 to 1
//   6.6–9.0  one still sticks; push in on its tag, ts:lean; sparkles

const COUNT = 63
const STRANDS = 3 // strands in a bundle
const WALL = -3 // z of the wall's face
const WINNER = [1.7, 2.75] // where ts:lean sticks, x and y on the wall
const SLIDES = [1.9, 5.4]
const NAMED_AT = [3.0, 3.6, 4.2, 4.8]
/** Where the four developers stand, and when each tips the pot (the first two before the first frame). */
const DEVS = [
  { x: -4.3, z: 1.0, shirt: '#d6262c', tip: -0.5 },
  { x: -3.1, z: 2.0, shirt: '#2563eb', tip: -0.25 },
  { x: -4.7, z: 2.9, shirt: '#16a34a', tip: 0.0 },
  { x: -3.0, z: 3.6, shirt: '#7c3aed', tip: 0.25 },
]

/** A cooked strand: a long thin tube that wanders in a plane (z = 0), about 1.9 long. */
export function strandGeometry(seed) {
  const rand = rng(seed)
  const points = []
  let angle = rand.range(-0.4, 0.4)
  let x = -0.95
  let y = 0
  for (let i = 0; i <= 14; i++) {
    points.push(new THREE.Vector3(x, y, rand.range(-0.01, 0.01)))
    angle += rand.range(-0.55, 0.55)
    x += Math.cos(angle) * 0.14
    y += Math.sin(angle) * 0.14
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 96, 0.016, 6, false)
}

/** A splash of tomato sauce: a round blob with soft lobes, flat on the wall. */
export function splatGeometry(seed) {
  const rand = rng(seed)
  const shape = new THREE.Shape()
  const n = 40
  const [p1, p2, p3] = [rand() * 6.28, rand() * 6.28, rand() * 6.28]
  const [a1, a2] = [rand.range(0.12, 0.24), rand.range(0.05, 0.12)]
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2
    const r = 1 + a1 * Math.sin(3 * a + p1) + a2 * Math.sin(5 * a + p2) + 0.05 * Math.sin(9 * a + p3)
    if (i === 0) shape.moveTo(Math.cos(a) * r, Math.sin(a) * r)
    else shape.lineTo(Math.cos(a) * r, Math.sin(a) * r)
  }
  return new THREE.ShapeGeometry(shape)
}

/** A cooking pot with two handles, its opening up. */
export function pot() {
  const group = new THREE.Group()
  const steel = mat('#b8c0ca', { side: THREE.DoubleSide })
  group.add(mesh(new THREE.CylinderGeometry(0.3, 0.26, 0.42, 16, 1, true), steel))
  group.add(at(mesh(new THREE.CircleGeometry(0.26, 16).rotateX(-Math.PI / 2), steel), 0, -0.2, 0))
  for (const side of [-1, 1]) group.add(at(box(0.16, 0.05, 0.08, '#4b5563'), side * 0.36, 0.14, 0))
  // the last spaghetti in the pot
  group.add(at(mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.06, 16), mat('#efcf7d')), 0, 0.02, 0))
  return group
}

function counterPainter(g, { n }, w, h) {
  g.fillStyle = '#ecebf3'
  g.fillRect(0, 0, w, h)
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = n === 1 ? '#16a34a' : '#dc2626'
  g.font = `800 ${Math.round(h * 0.62)}px ${SANS}`
  g.fillText(String(n), w / 2, h * 0.42)
  g.fillStyle = '#1d1f24'
  g.font = `800 ${Math.round(h * 0.16)}px ${SANS}`
  g.fillText('LEFT', w / 2, h * 0.85)
}

export default {
  sounds(segment) {
    const cues = [
      ...voiceCues(segment),
      { at: 0, sound: 'whoosh', length: 1.6, from: 250, to: 1200, gain: 0.35 },
      { at: SLIDES[0], sound: 'slot', length: SLIDES[1] - SLIDES[0], gain: 0.05 },
      { at: 6.6, sound: 'riser', length: 0.6, gain: 0.12 },
      { at: 6.8, sound: 'twinkle', gain: 0.25 },
    ]
    for (let i = 0; i < 9; i++) cues.push({ at: 1.2 + i * 0.08, sound: 'splat', gain: 0.5 - i * 0.03 })
    for (const at of NAMED_AT) cues.push({ at, sound: 'boom', gain: 0.18, length: 0.3 })
    return cues
  },

  build(segment) {
    const scene = new THREE.Scene()
    hall(scene, { hour: 'HOUR 31' })
    const rand = rng(63)

    // the wall the spaghetti hits, with the counter
    scene.add(at(box(7.6, 5.4, 0.2, '#ecebf3'), 1.6, 2.7, WALL - 0.1))
    const counter = liveTexture(256, 256, counterPainter)
    counter.set({ n: COUNT })
    scene.add(
      at(
        new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1), new THREE.MeshBasicMaterial({ map: counter.texture })),
        4.75,
        4.6,
        WALL + 0.01,
      ),
    )

    // the four developers, each tipping a pot held out in both hands
    const devs = DEVS.map((spec) => {
      const person = developer({ shirt: spec.shirt })
      const facing = Math.atan2(1.6 - spec.x, WALL - spec.z)
      person.root.position.set(spec.x, 0, spec.z)
      person.root.rotation.y = facing
      const held = pot()
      held.position.set(0, 0.42, 0.66)
      person.torso.add(held)
      scene.add(person.root)
      // where the pot's opening is in the world when it tips: the strands leave from there
      const mouth = new THREE.Vector3(spec.x + Math.sin(facing) * 0.95, 1.55, spec.z + Math.cos(facing) * 0.95)
      return { person, held, mouth, ...spec }
    })

    // 63 bundles of strands in six shapes, and a splash of sauce where each one lands
    const shapes = [1, 2, 3, 4, 5, 6].map(strandGeometry)
    const noodle = new THREE.MeshStandardMaterial({ color: '#f0cf7a', roughness: 0.38, metalness: 0 })
    const perShape = Math.ceil((COUNT * STRANDS) / shapes.length)
    const instanced = shapes.map((g) => {
      const m = new THREE.InstancedMesh(g, noodle, perShape)
      m.frustumCulled = false
      m.castShadow = true
      scene.add(m)
      return m
    })
    const sauce = new THREE.MeshStandardMaterial({ color: '#d8462a', roughness: 0.25, metalness: 0 })
    const splats = []
    const bundles = []
    for (let i = 0; i < COUNT; i++) {
      const winner = i === COUNT - 1
      const dev = devs[i % devs.length]
      const target = winner ? [...WINNER] : [rand.range(-1.7, 4.9), rand.range(0.8, 4.9)]
      // none lands on the counter in the top right corner
      if (target[0] > 3.8 && target[1] > 3.65) target[1] -= 1.4
      const launch = dev.tip + 0.1 + rand() * 0.25
      const hit = 1.2 + rand() * 0.7
      const spin = [rand.range(-5, 5), rand.range(-5, 5), rand.range(-5, 5)]
      const turn = rand() * Math.PI
      const arc = rand.range(0.6, 1.4)
      const drop = rand.range(6, 10)
      const offsets = Array.from({ length: STRANDS }, () => [
        rand.range(-0.08, 0.08),
        rand.range(-0.08, 0.08),
        rand() * 0.6,
      ])
      // the one that sticks is a single strand
      const slide = winner ? Infinity : 0
      bundles.push({
        dev,
        target,
        launch,
        hit,
        spin,
        turn,
        arc,
        slide,
        drop,
        offsets: winner ? [[0, 0, 0.3]] : offsets,
        winner,
      })
      const splat = mesh(splatGeometry(i + 7), sauce, { shadow: false })
      splat.scale.setScalar(0.001)
      splat.rotation.z = rand() * Math.PI
      splat.position.set(
        target[0] + rand.range(-0.1, 0.1),
        target[1] + rand.range(-0.1, 0.1),
        WALL + 0.012 + i * 0.0002,
      )
      scene.add(splat)
      splats.push({ splat, size: rand.range(0.12, 0.22) })
    }
    // the named losers slide off while the camera is close; the others before and after them
    const losers = bundles.map((_, i) => i).filter((i) => !bundles[i].winner)
    const named = losers.slice(0, segment.tags.length)
    named.forEach((i, k) => {
      bundles[i].target = [0.1 + k * 1.15, 2.2 + (k % 2) * 1.1]
      splats[i].splat.position.set(bundles[i].target[0], bundles[i].target[1], splats[i].splat.position.z)
      bundles[i].slide = NAMED_AT[k]
    })
    const others = losers.slice(segment.tags.length)
    others.forEach((i, rank) => {
      bundles[i].slide = SLIDES[0] + rank * ((SLIDES[1] - SLIDES[0]) / (others.length - 1))
    })
    const tags = [...segment.tags, segment.winner].map((text, k) => {
      const winner = k === segment.tags.length
      const tag = sign(text, {
        w: winner ? 1.3 : 1.05,
        h: winner ? 0.36 : 0.28,
        bg: winner ? '#13a35a' : '#ffffff',
        fg: winner ? '#ffffff' : '#1d1f24',
      })
      scene.add(tag)
      return { tag, i: winner ? COUNT - 1 : named[k], winner }
    })

    const camera = new THREE.PerspectiveCamera(40, 16 / 10, 0.05, 120)
    const screen = (v) => toScreen(v, camera, 1920, 1200)
    const dummy = new THREE.Object3D()
    /** Where a bundle is at time t: in the air from its pot, flat on the wall, or sliding down to the floor. */
    const where = (b, t) => {
      if (t < b.hit) {
        const u = clamp((t - b.launch) / (b.hit - b.launch))
        const p = [
          lerp(b.dev.mouth.x, b.target[0], u),
          lerp(b.dev.mouth.y, b.target[1], u) + Math.sin(Math.PI * u) * b.arc,
          lerp(b.dev.mouth.z, WALL + 0.05, u),
        ]
        return { p, r: [b.spin[0] * u, b.spin[1] * u, b.spin[2] * u + b.turn * u], flying: t >= b.launch }
      }
      const fall = Math.max(0, t - b.slide)
      const y = Math.max(0.05, b.target[1] - 0.5 * b.drop * fall * fall)
      const lying = y <= 0.05
      return {
        p: [b.target[0], y, lying ? WALL + 0.4 : WALL + 0.04],
        r: lying ? [Math.PI / 2, 0, b.turn] : [0, 0, b.turn],
        flying: true,
      }
    }
    const marks = []

    return {
      scene,
      camera,
      update(t) {
        const counts = shapes.map(() => 0)
        let stuck = 0
        let flying = 0
        bundles.forEach((b, i) => {
          const { p, r, flying: out } = where(b, t)
          if (t >= b.hit && t < b.slide) stuck++
          if (t < b.hit) flying++
          b.offsets.forEach(([ox, oy, twist], s) => {
            dummy.position.set(p[0] + ox, p[1] + oy, p[2] + (t < b.hit ? ox : 0))
            dummy.rotation.set(r[0], r[1], r[2] + twist)
            dummy.scale.setScalar(out ? 1 : 0.001)
            dummy.updateMatrix()
            const shape = (i * STRANDS + s) % shapes.length
            instanced[shape].setMatrixAt(counts[shape]++, dummy.matrix)
          })
          const { splat, size } = splats[i]
          splat.scale.setScalar(Math.max(0.001, size * pop(t, b.hit, 0.15)))
        })
        // draw only the strands set above: an instance left unset would stand on the floor at the origin
        instanced.forEach((m, k) => {
          m.count = counts[k]
          m.instanceMatrix.needsUpdate = true
        })
        counter.set({ n: t < 1.2 ? COUNT : Math.max(1, stuck + flying) })

        marks.length = 0
        for (const { tag, i, winner } of tags) {
          const { p } = where(bundles[i], t)
          tag.position.set(p[0] + 0.15, p[1] + 0.3, p[2] + 0.05)
          tag.visible = t >= bundles[i].launch && p[1] > 0.06
          marks.push({ i, winner, p })
        }

        // the developers tip their pots: arms up and forward, the pot turning over; then they cheer a little
        devs.forEach((dev, k) => {
          const tip = ease.outCubic(progress(t, dev.tip, dev.tip + 0.5)) * (1 - ease.inOutQuad(progress(t, 2.4, 3.4)))
          pose(dev.person, {
            armL: [-1.35 - 0.5 * tip, 0, -0.12],
            armR: [-1.35 - 0.5 * tip, 0, 0.12],
            torso: [0.08 + 0.12 * tip, 0, 0],
            head: [-0.1 * tip, 0, 0],
            lift: 0.04 * Math.abs(Math.sin(t * 4 + k)) * progress(t, 3.4, 4),
          })
          dev.held.position.set(0, 0.42 + 0.22 * tip, 0.66 + 0.06 * tip)
          dev.held.rotation.x = 1.6 * tip
        })

        // the camera: wide, then in on the wall, then on the one that sticks
        const eye = track(t, [
          [0, [-0.9, 3.1, 12.6]],
          [1.6, [-0.6, 2.95, 11.2], 'outQuad'],
          [2.6, [1.5, 2.85, 4.6], 'inOutQuad'],
          [6.6, [1.6, 2.85, 4.1]],
          [8.0, [WINNER[0] + 0.1, WINNER[1] + 0.2, WALL + 2.4], 'inOutCubic'],
        ])
        const look = track(t, [
          [0, [-0.5, 2.1, -1.2]],
          [2.6, [1.6, 2.75, WALL], 'inOutQuad'],
          [6.6, [1.6, 2.75, WALL]],
          [8.0, [WINNER[0] + 0.1, WINNER[1] + 0.1, WALL], 'inOutCubic'],
        ])
        camera.position.set(...eye)
        camera.lookAt(...look)
      },
      overlay(g, t) {
        // ELIMINATED on each named bundle as it starts to slide
        for (const { i, winner, p } of marks) {
          const b = bundles[i]
          if (winner || t < b.slide) continue
          const k = pop(t, b.slide, 0.2)
          if (k <= 0 || p[1] <= 0.06) continue
          const [x, y] = screen(new THREE.Vector3(p[0] + 0.15, p[1] + 0.3, p[2]))
          g.save()
          g.translate(x, y)
          g.rotate(-0.18)
          g.scale(k, k)
          g.strokeStyle = '#e8262b'
          g.lineWidth = 8
          g.strokeRect(-150, -36, 300, 72)
          g.restore()
          outlined(g, 'ELIMINATED', x, y - 4, 44, { fill: '#dc2626', stroke: '#ffffff', line: 8, alpha: k, font: SANS })
        }
        // sparkles round the one that sticks
        if (t > 6.6) {
          const [x, y] = screen(new THREE.Vector3(WINNER[0], WINNER[1] + 0.2, WALL + 0.1))
          const a = ease.outQuad(progress(t, 6.6, 6.9))
          for (let k = 0; k < 5; k++) {
            const angle = t * 1.6 + (k * Math.PI * 2) / 5
            sparkle(g, x + Math.cos(angle) * 300, y + Math.sin(angle) * 150, 26 + 10 * Math.sin(t * 7 + k), a)
          }
        }
        captions(g, t, segment)
      },
    }
  },
}
