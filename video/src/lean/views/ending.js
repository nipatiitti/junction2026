import * as THREE from 'three'
import { ease, lerp, progress, track } from '../../kit/anim.js'
import { mix, POSES, pose } from '../../kit/character.js'
import { burst, flash } from '../../kit/fx.js'
import { at, box, mat, mesh } from '../../kit/materials.js'
import { rng } from '../../kit/rng.js'
import { sign } from '../../kit/sign.js'
import { captions, voiceCues } from '../lines.js'
import { developer, hall, lanyard } from '../sets.js'
import { lowerThird } from '../ui.js'
import { splatGeometry, strandGeometry } from './spaghetti.js'

// The end: back at the spaghetti wall, where ts:lean still sticks, the four developers jump for a four-way high five
// ("Ship it!"), hang in the air in slow motion while confetti and spaghetti fly, land and celebrate while the camera
// circles them; the end title comes up as a lower third. The texts are in timeline.js. Beats (local seconds):
//   0–1.1 they stand round, the camera comes in · 1.1–1.45 wind up · 1.45–1.7 jump, the hands meet at 1.7 ·
//   1.7–3.2 slow motion in the air · 3.2–3.7 land · 3.0 the end title · 3.7–9.0 celebrate, the camera circles ·
//   8.4–9.0 fade out

const WALL = -3
const CENTRE = [1.2, 0.5]
const RADIUS = 0.78
const MEET = 1.7
const SHIRTS = ['#d6262c', '#2563eb', '#16a34a', '#7c3aed']

/** How high the four are off the ground at time t: a jump that hangs at the top in slow motion, then lands. */
function height(t) {
  if (t < 1.45) return 0
  if (t < MEET) return 0.55 * ease.outCubic(progress(t, 1.45, MEET))
  if (t < 3.2) return 0.55 + 0.04 * Math.sin((t - MEET) * 2)
  return 0.55 * (1 - ease.inQuad(progress(t, 3.2, 3.6)))
}

export default {
  sounds(segment) {
    const cues = [
      ...voiceCues(segment),
      { at: 1.4, sound: 'whoosh', length: 0.4, from: 300, to: 2400, gain: 0.3 },
      { at: MEET, sound: 'clap', gain: 1.0, wet: 0.4 },
      { at: MEET, sound: 'boom', gain: 0.45, length: 0.8 },
      { at: MEET + 0.05, sound: 'twinkle', gain: 0.3 },
      { at: 3.55, sound: 'tap', gain: 0.2 },
    ]
    for (let i = 0; i < 6; i++) cues.push({ at: 4.2 + i * 0.7, sound: 'clap', gain: 0.25, wet: 0.2 })
    return cues
  },

  build(segment) {
    const scene = new THREE.Scene()
    hall(scene, { hour: 'HOUR 48', banner: 'SHIPPED' })
    const rand = rng(48)

    // the spaghetti wall as the opening left it: sauce, fallen strands, and ts:lean still stuck with its tag
    scene.add(at(box(7.6, 5.4, 0.2, '#ecebf3'), 1.6, 2.7, WALL - 0.1))
    const sauce = new THREE.MeshStandardMaterial({ color: '#d8462a', roughness: 0.25, metalness: 0 })
    for (let i = 0; i < 40; i++) {
      const splat = mesh(splatGeometry(i + 7), sauce, { shadow: false })
      splat.scale.setScalar(rand.range(0.12, 0.22))
      splat.rotation.z = rand() * Math.PI
      splat.position.set(rand.range(-1.8, 5), rand.range(0.7, 5), WALL + 0.012 + i * 0.0002)
      scene.add(splat)
    }
    const noodle = new THREE.MeshStandardMaterial({ color: '#f0cf7a', roughness: 0.38, metalness: 0 })
    const shapes = [1, 2, 3, 4, 5, 6].map(strandGeometry)
    // the single strand that stuck
    const stuck = new THREE.Mesh(shapes[0], noodle)
    stuck.position.set(1.7, 2.75, WALL + 0.04)
    stuck.rotation.z = 0.7
    scene.add(stuck)
    const winner = sign(segment.texts.winner, { w: 1.3, h: 0.36, bg: '#13a35a', fg: '#ffffff' })
    scene.add(at(winner, 1.85, 3.05, WALL + 0.06))
    for (let i = 0; i < 90; i++) {
      const strand = new THREE.Mesh(shapes[i % shapes.length], noodle)
      strand.position.set(rand.range(-1.6, 4.8), 0.03, WALL + rand.range(0.2, 0.9))
      strand.rotation.set(Math.PI / 2, 0, rand() * Math.PI)
      scene.add(strand)
    }

    // the four developers round a point in front of the wall, facing each other, with their team's lanyards; they
    // stand on the four axes, so the camera at 45° to either side looks between two of them at the hands
    const devs = SHIRTS.map((shirt, i) => {
      const angle = (i * Math.PI) / 2
      const x = CENTRE[0] + Math.cos(angle) * RADIUS
      const z = CENTRE[1] + Math.sin(angle) * RADIUS
      const person = developer({ shirt })
      person.root.position.set(x, 0, z)
      person.root.rotation.y = Math.atan2(CENTRE[0] - x, CENTRE[1] - z)
      lanyard(person, 'BLIB BLIB')
      scene.add(person.root)
      return person
    })

    // confetti and a few strands of spaghetti burst from where the hands meet
    const confetti = burst(rng(5), {
      count: 260,
      origin: [CENTRE[0], 3.0, CENTRE[1]],
      start: MEET,
      spread: 0.15,
      speed: [1.2, 4.2],
      up: [2, 6],
      gravity: 3.2,
      floor: 0.02,
      geometry: new THREE.BoxGeometry(0.09, 0.012, 0.06),
      material: mat('#ffffff'),
      colors: ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#a855f7', '#f8fafc'],
      flat: true,
    })
    scene.add(confetti.object)
    const pasta = burst(rng(6), {
      count: 40,
      origin: [CENTRE[0], 3.0, CENTRE[1]],
      start: MEET,
      spread: 0.1,
      speed: [1, 3],
      up: [2.5, 5],
      gravity: 3.2,
      floor: 0.03,
      geometry: new THREE.CylinderGeometry(0.012, 0.012, 0.5, 5).rotateZ(Math.PI / 2),
      material: noodle,
      flat: true,
    })
    scene.add(pasta.object)

    const camera = new THREE.PerspectiveCamera(42, 16 / 10, 0.05, 100)
    return {
      scene,
      camera,
      update(t) {
        const lift = height(t)
        devs.forEach((person, i) => {
          const bob = 0.03 * Math.abs(Math.sin(t * 5 + i))
          const wind = ease.inOutQuad(progress(t, 1.1, 1.45)) * (1 - progress(t, 1.45, 1.6))
          const reach = ease.outCubic(progress(t, 1.4, MEET)) * (1 - ease.inOutQuad(progress(t, 3.3, 3.9)))
          const party = ease.inOutQuad(progress(t, 3.7, 4.2))
          const rest = { armL: [0.15, 0, 0.1], armR: [0.15, 0, -0.1], lift: bob * (1 - reach) }
          const windUp = { armR: [0.7, 0, -0.1], armL: [0.3, 0, 0.1], torso: [-0.15, 0, 0] }
          const highFive = { armR: [-2.55, 0, 0.32], armL: [0.2, 0, 0.25], head: [-0.35, 0, 0] }
          const cheer = { ...POSES.armsUp, lift: 0.08 * Math.abs(Math.sin(t * 6 + i * 1.3)) }
          let angles = mix(rest, windUp, wind)
          angles = mix(angles, highFive, reach)
          angles = mix(angles, cheer, party)
          pose(person, angles)
          person.root.position.y = lift
        })
        confetti.update(t)
        pasta.update(t)

        // the camera: in on the four from high above, between two of them, then a quarter turn round them; the circle
        // starts where the way in ends, and the point it looks at slides over, so there is no cut
        if (t < 3.2) {
          const eye = track(t, [
            [0, [6.4, 5.9, 5.7]],
            [3.2, [4.9, 5.0, 4.2], 'outQuad'],
          ])
          camera.position.set(...eye)
        } else {
          const angle = lerp(0.79, -0.79, ease.inOutQuad(progress(t, 3.2, 9)))
          const r = lerp(5.23, 6.0, progress(t, 3.2, 9))
          camera.position.set(
            CENTRE[0] + Math.sin(angle) * r,
            lerp(5.0, 3.4, ease.inOutQuad(progress(t, 3.2, 9))),
            CENTRE[1] + Math.cos(angle) * r,
          )
        }
        const settle = ease.inOutQuad(progress(t, 3.2, 4.4))
        camera.lookAt(CENTRE[0] + 0.3 * settle, lerp(2.1 + lift * 0.5, 2.0, settle), CENTRE[1] - lerp(0.2, 1.0, settle))
      },
      overlay(g, t) {
        flash(g, 0.5 * (1 - progress(t, MEET, MEET + 0.25)) * (t >= MEET ? 1 : 0))
        lowerThird(g, t, segment.texts.title, segment.texts.team, { t0: 3.0 })
        captions(g, t, segment)
        flash(g, progress(t, 8.4, 9.0), '0,0,0')
      },
    }
  },
}
