import * as THREE from 'three'
import { clamp, ease, lerp, pop, progress, track } from '../../kit/anim.js'
import { POSES, pose } from '../../kit/character.js'
import { sparkle } from '../../kit/fx.js'
import { at, box, mat, mesh } from '../../kit/materials.js'
import { rng } from '../../kit/rng.js'
import { liveTexture, sign } from '../../kit/sign.js'
import { outlined, toScreen } from '../../kit/text.js'
import { captions, voiceCues } from '../lines.js'
import { developer, hall } from '../sets.js'
import { SANS } from '../ui.js'

// Joke 1, the hook: the team throws 63 strategies at a wall like spaghetti, in slow motion. They slap the wall, slide
// down one by one while a counter on the wall runs down, and one sticks: ts:lean. The texts are in timeline.js.
// Beats (local seconds):
//   0–1.4    the first frame is already mid-throw: 63 strands fly at the wall, slowly; they slap it at 1.4
//   1.6–3.0  they slide down; the named ones get an ELIMINATED stamp; the counter runs from 63 to 1
//   3.0–4.0  one strand still sticks; push in on its tag, ts:lean; sparkles

const COUNT = 63
const THROWN = -0.6 // the throw left the pot before the first frame
const HIT = 1.4 // the strands reach the wall
const WALL = -3 // z of the wall's face
const POT = [-3.0, 1.95, 1.9]
const WINNER = [1.7, 2.75] // where ts:lean sticks, x and y on the wall
const SLIDE_FROM = 1.6

/** A strand of spaghetti: a wavy tube along x, about 1.7 long. */
function strandGeometry(seed) {
  const rand = rng(seed)
  const points = []
  for (let i = 0; i <= 8; i++)
    points.push(new THREE.Vector3(-0.85 + i * 0.21, rand.range(-0.09, 0.09), rand.range(-0.03, 0.03)))
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 32, 0.03, 5, false)
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
      { at: 0, sound: 'whoosh', length: 1.3, from: 300, to: 1400, gain: 0.35 },
      { at: HIT, sound: 'splat', gain: 0.55 },
      { at: HIT + 0.09, sound: 'splat', gain: 0.4 },
      { at: HIT + 0.2, sound: 'splat', gain: 0.35 },
      { at: SLIDE_FROM, sound: 'slot', length: 1.4, gain: 0.07 },
      { at: 3.05, sound: 'twinkle', gain: 0.25 },
      { at: 3.0, sound: 'riser', length: 0.9, gain: 0.12 },
    ]
    return cues
  },

  build(segment) {
    const scene = new THREE.Scene()
    hall(scene, { hour: 'HOUR 31' })
    const rand = rng(63)

    // the wall the strands hit, with the counter
    scene.add(at(box(7.2, 5.2, 0.2, '#ecebf3'), 1.6, 2.6, WALL - 0.1))
    const counter = liveTexture(256, 256, counterPainter)
    counter.set({ n: COUNT })
    scene.add(
      at(
        new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1), new THREE.MeshBasicMaterial({ map: counter.texture })),
        4.55,
        4.45,
        WALL + 0.01,
      ),
    )

    // the team: the developer tips the pot, two teammates cheer
    const dev = developer()
    dev.root.rotation.y = Math.PI / 2.4
    scene.add(at(dev.root, -3.6, 0, 1.7))
    pose(dev, { armL: [-1.45, 0, -0.1], armR: [-1.45, 0, 0.1], torso: [0.12, 0, 0] })
    const pot = mesh(
      new THREE.CylinderGeometry(0.42, 0.34, 0.6, 12, 1, true),
      mat('#aab2bc', { side: THREE.DoubleSide }),
    )
    pot.rotation.z = -1.0
    scene.add(at(pot, POT[0] - 0.25, POT[1] - 0.15, POT[2]))
    const mates = []
    for (const [x, z, shirt] of [
      [-4.9, 0.5, '#2b7de9'],
      [-5.1, 2.9, '#6a4c93'],
    ]) {
      const mate = developer({ shirt })
      mate.root.rotation.y = Math.PI / 2.6
      scene.add(at(mate.root, x, 0, z))
      mates.push(mate)
    }

    // 63 strands, in three shapes; the named ones carry a tag
    const shapes = [strandGeometry(1), strandGeometry(2), strandGeometry(3)]
    const noodle = mat('#f3d27a')
    const instanced = shapes.map((g) => {
      const m = new THREE.InstancedMesh(g, noodle, Math.ceil(COUNT / 3))
      m.frustumCulled = false
      m.castShadow = true
      scene.add(m)
      return m
    })
    const named = [...segment.tags, segment.winner]
    const strands = []
    for (let i = 0; i < COUNT; i++) {
      const winner = i === COUNT - 1
      const target = winner ? [WINNER[0], WINNER[1]] : [rand.range(-1.6, 4.9), rand.range(0.7, 4.7)]
      strands.push({
        target,
        launch: THROWN + rand() * 0.25,
        hit: HIT + rand() * 0.18,
        spin: [rand.range(-6, 6), rand.range(-6, 6), rand.range(-6, 6)],
        turn: rand() * Math.PI,
        arc: rand.range(0.8, 1.6),
        slide: winner ? Infinity : 0, // set below: the order they slide off in
        drop: rand.range(5, 9),
        winner,
      })
    }
    // the named losers slide off while the camera is close, the others before and after them
    const order = strands.map((_, i) => i).filter((i) => !strands[i].winner)
    const namedLosers = order.slice(0, segment.tags.length)
    for (const [k, i] of namedLosers.entries()) strands[i].target = [0.1 + k * 1.15, 2.2 + (k % 2) * 1.1]
    const others = order.slice(segment.tags.length)
    others.forEach((i, rank) => {
      strands[i].slide = SLIDE_FROM + rank * ((3.0 - SLIDE_FROM) / (others.length - 1))
    })
    namedLosers.forEach((i, k) => {
      strands[i].slide = 2.0 + k * 0.2
    })
    const tags = []
    named.forEach((text, k) => {
      const i = k < segment.tags.length ? namedLosers[k] : COUNT - 1
      const winner = k === segment.tags.length
      const tag = sign(text, {
        w: winner ? 1.3 : 1.05,
        h: winner ? 0.36 : 0.28,
        bg: winner ? '#13a35a' : '#ffffff',
        fg: winner ? '#ffffff' : '#1d1f24',
      })
      scene.add(tag)
      tags.push({ tag, i, winner, text })
    })

    const camera = new THREE.PerspectiveCamera(40, 16 / 10, 0.05, 120)
    const screen = (v) => toScreen(v, camera, 1920, 1200)
    const dummy = new THREE.Object3D()
    const where = (s, t) => {
      // in the air from launch to hit, flat on the wall, then sliding down to the floor
      if (t < s.hit) {
        const u = clamp((t - s.launch) / (s.hit - s.launch))
        const x = lerp(POT[0], s.target[0], u)
        const y = lerp(POT[1], s.target[1], u) + Math.sin(Math.PI * u) * s.arc
        const z = lerp(POT[2], WALL + 0.05, u)
        return { p: [x, y, z], r: [s.spin[0] * u, s.spin[1] * u, s.spin[2] * u + s.turn * u] }
      }
      const fall = Math.max(0, t - s.slide)
      const y = Math.max(0.05, s.target[1] - 0.5 * s.drop * fall * fall)
      const lying = y <= 0.05
      return {
        p: [s.target[0], y, lying ? WALL + 0.35 : WALL + 0.05],
        r: lying ? [Math.PI / 2, 0, s.turn] : [0, 0, s.turn],
      }
    }
    const screenTags = []

    return {
      scene,
      camera,
      update(t) {
        const counts = [0, 0, 0]
        let stuck = 0
        strands.forEach((s, i) => {
          const { p, r } = where(s, t)
          if (t >= s.hit && t < s.slide) stuck++
          dummy.position.set(...p)
          dummy.rotation.set(...r)
          dummy.scale.setScalar(1)
          dummy.updateMatrix()
          const shape = i % 3
          instanced[shape].setMatrixAt(counts[shape]++, dummy.matrix)
        })
        for (const m of instanced) m.instanceMatrix.needsUpdate = true
        counter.set({ n: t < HIT ? COUNT : Math.max(1, stuck) })

        screenTags.length = 0
        for (const { tag, i, winner } of tags) {
          const { p, r } = where(strands[i], t)
          tag.position.set(p[0] + 0.15, p[1] + 0.26, p[2] + 0.04)
          tag.rotation.set(0, 0, t < strands[i].hit ? r[2] * 0.3 : 0)
          tag.visible = p[1] > 0.06
          screenTags.push({ i, winner, p })
        }

        pose(dev, {
          armL: [-1.45 + 0.15 * Math.sin(t * 2), 0, -0.1],
          armR: [-1.45 + 0.15 * Math.sin(t * 2), 0, 0.1],
          torso: [0.12, 0, 0],
        })
        mates.forEach((mate, k) => {
          pose(mate, { ...POSES.armsUp, lift: Math.abs(Math.sin(t * 5 + k)) * 0.12 })
        })

        // the camera: wide, then in on the wall, then on the strand that sticks
        const eye = track(t, [
          [0, [0.2, 2.8, 10.8]],
          [1.3, [0.3, 2.7, 9.6], 'outQuad'],
          [2.2, [1.5, 2.8, 4.4], 'inOutQuad'],
          [3.0, [1.5, 2.8, 4.0]],
          [4.2, [WINNER[0] + 0.1, WINNER[1] + 0.2, WALL + 2.5], 'inOutCubic'],
        ])
        const look = track(t, [
          [0, [0.4, 2.3, -2]],
          [2.2, [1.6, 2.7, WALL], 'inOutQuad'],
          [3.0, [1.6, 2.7, WALL]],
          [4.2, [WINNER[0] + 0.1, WINNER[1] + 0.1, WALL], 'inOutCubic'],
        ])
        camera.position.set(...eye)
        camera.lookAt(...look)
      },
      overlay(g, t) {
        // ELIMINATED on each named strand as it starts to slide
        for (const { i, winner, p } of screenTags) {
          const s = strands[i]
          if (winner || t < s.slide) continue
          const k = pop(t, s.slide, 0.2)
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
        if (t > 3.0) {
          const [x, y] = screen(new THREE.Vector3(WINNER[0], WINNER[1] + 0.2, WALL + 0.1))
          const a = ease.outQuad(progress(t, 3.0, 3.3))
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
